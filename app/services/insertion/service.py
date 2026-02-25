"""
Incremental Insertion Service for dynamic route modification.

Implements optimistic locking (CAS) to safely insert new shipments
into active routes with temperature risk assessment.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.models.insertion import InsertionAttempt
from app.models.route import Route, RouteStop
from app.models.shipment import Shipment
from app.models.vehicle import Vehicle
from app.services.insertion.exceptions import (
    InsertionRejectedException,
    StaleRouteException,
)
from app.services.insertion.temperature_proxy import RiskLevel, TemperatureProxy


# Maximum acceptable risk score for automatic insertion
TEMP_RISK_THRESHOLD = Decimal("0.8")


class InsertionCandidate:
    """Evaluated candidate for inserting a shipment at a specific position."""

    __slots__ = (
        "position",
        "extra_distance_meters",
        "delay_impact_minutes",
        "temp_risk_score",
        "temp_risk_level",
    )

    def __init__(
        self,
        position: int,
        extra_distance_meters: int,
        delay_impact_minutes: int,
        temp_risk_score: Decimal,
        temp_risk_level: RiskLevel,
    ):
        self.position = position
        self.extra_distance_meters = extra_distance_meters
        self.delay_impact_minutes = delay_impact_minutes
        self.temp_risk_score = temp_risk_score
        self.temp_risk_level = temp_risk_level


class IncrementalInsertionService:
    """Service for inserting shipments into active routes with CAS locking."""

    def __init__(self, session: AsyncSession):
        self._session = session
        self._temp_proxy = TemperatureProxy()
        self._settings = get_settings()

    async def attempt_insertion(
        self,
        route_id: UUID,
        shipment_id: UUID,
        user_id: UUID,
        preferred_position: Optional[int] = None,
    ) -> dict:
        """
        Insert a shipment into an active route using optimistic locking.

        Args:
            route_id: Target route.
            shipment_id: Shipment to insert.
            user_id: Authenticated user performing the insertion.
            preferred_position: Optional specific position (1-based).
                If None, the best feasible position is chosen automatically.

        Returns:
            Dict with insertion_id, status, position, risk metrics,
            and updated_route_version.

        Raises:
            StaleRouteException: Route was modified concurrently (409).
            InsertionRejectedException: No feasible position (422).
        """
        # Step 1: Load route with stops and vehicle
        route, vehicle, shipment = await self._load_entities(route_id, shipment_id)
        snapshot_version = route.version

        # Step 2: Evaluate candidates
        candidates = self._evaluate_all_positions(route, vehicle, shipment)

        # Step 3: Select best candidate
        best = self._select_best_candidate(candidates, preferred_position)

        # Step 4: CAS update (atomic version bump)
        new_version = await self._cas_update_route(
            route_id, snapshot_version, best.extra_distance_meters
        )

        # Step 5: Resequence FIRST to make room, then insert
        # (Must shift existing stops before inserting to avoid unique constraint violation
        # on uq_route_stop_sequence)
        await self._resequence_stops(route_id, best.position)
        await self._insert_stop_at_position(route, shipment, best.position)

        # Step 6: Create audit record
        attempt = InsertionAttempt(
            route_id=route_id,
            shipment_id=shipment_id,
            target_route_version=snapshot_version,
            proposed_position=best.position,
            temp_risk_score=best.temp_risk_score,
            delay_impact_minutes=best.delay_impact_minutes,
            extra_distance_meters=best.extra_distance_meters,
            status="ACCEPTED",
            attempted_by=user_id,
            resolved_at=datetime.utcnow(),
        )
        self._session.add(attempt)
        await self._session.flush()

        return {
            "insertion_id": attempt.id,
            "status": "ACCEPTED",
            "position": best.position,
            "temp_risk_score": best.temp_risk_score,
            "temp_risk_level": best.temp_risk_level.value,
            "delay_impact_minutes": best.delay_impact_minutes,
            "extra_distance_meters": best.extra_distance_meters,
            "updated_route_version": new_version,
        }

    async def preview_insertion(
        self,
        route_id: UUID,
        shipment_id: UUID,
    ) -> dict:
        """
        Preview all candidate positions without mutating any state.

        Returns:
            Dict with candidates list, recommended_position, route_version.
        """
        route, vehicle, shipment = await self._load_entities(route_id, shipment_id)
        candidates = self._evaluate_all_positions(route, vehicle, shipment)

        # Sort by extra_distance (cheapest first)
        sorted_candidates = sorted(candidates, key=lambda c: c.extra_distance_meters)

        # Recommend first feasible (below threshold)
        recommended = next(
            (c for c in sorted_candidates if c.temp_risk_score < TEMP_RISK_THRESHOLD),
            sorted_candidates[0] if sorted_candidates else None,
        )

        return {
            "candidates": [
                {
                    "position": c.position,
                    "temp_risk_score": c.temp_risk_score,
                    "temp_risk_level": c.temp_risk_level.value,
                    "delay_impact_minutes": c.delay_impact_minutes,
                    "extra_distance_meters": c.extra_distance_meters,
                }
                for c in sorted_candidates
            ],
            "recommended_position": recommended.position if recommended else 1,
            "route_version": route.version,
        }

    async def get_insertion_history(
        self,
        route_id: UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> dict:
        """Retrieve past insertion attempts for a route."""
        query = (
            select(InsertionAttempt)
            .where(InsertionAttempt.route_id == route_id)
            .order_by(InsertionAttempt.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(query)
        attempts = result.scalars().all()

        count_result = await self._session.scalar(
            select(func.count(InsertionAttempt.id)).where(
                InsertionAttempt.route_id == route_id
            )
        )

        return {
            "items": attempts,
            "total": count_result or 0,
        }

    # ─── Private helpers ──────────────────────────────────────────────────

    async def _load_entities(
        self, route_id: UUID, shipment_id: UUID
    ) -> tuple[Route, Vehicle, Shipment]:
        """Load and validate route, vehicle, and shipment."""
        route_result = await self._session.execute(
            select(Route)
            .options(
                selectinload(Route.stops).selectinload(RouteStop.shipment),
                selectinload(Route.vehicle),
            )
            .where(Route.id == route_id)
        )
        route = route_result.scalar_one_or_none()
        if route is None:
            raise ValueError(f"Route {route_id} not found")

        vehicle = route.vehicle
        if vehicle is None:
            raise ValueError(f"Route {route_id} has no assigned vehicle")

        shipment_result = await self._session.execute(
            select(Shipment).where(Shipment.id == shipment_id)
        )
        shipment = shipment_result.scalar_one_or_none()
        if shipment is None:
            raise ValueError(f"Shipment {shipment_id} not found")

        return route, vehicle, shipment

    def _evaluate_all_positions(
        self,
        route: Route,
        vehicle: Vehicle,
        shipment: Shipment,
    ) -> list[InsertionCandidate]:
        """Evaluate every valid insertion position."""
        ordered_stops = route.get_stops_ordered()
        num_stops = len(ordered_stops)
        candidates: list[InsertionCandidate] = []

        for position in range(1, num_stops + 2):
            extra_dist = self._estimate_extra_distance(
                ordered_stops, position, shipment
            )
            delay = self._estimate_delay_impact(extra_dist)
            risk_score = self._temp_proxy.calculate_risk_score(
                route, vehicle, shipment, position, extra_dist
            )
            risk_level = TemperatureProxy.get_risk_level(risk_score)

            candidates.append(
                InsertionCandidate(
                    position=position,
                    extra_distance_meters=extra_dist,
                    delay_impact_minutes=delay,
                    temp_risk_score=risk_score,
                    temp_risk_level=risk_level,
                )
            )

        return candidates

    def _select_best_candidate(
        self,
        candidates: list[InsertionCandidate],
        preferred_position: Optional[int],
    ) -> InsertionCandidate:
        """Select the best candidate, respecting preferred_position if set."""
        if preferred_position is not None:
            match = next(
                (c for c in candidates if c.position == preferred_position), None
            )
            if match is not None:
                if match.temp_risk_score > TEMP_RISK_THRESHOLD:
                    raise InsertionRejectedException(
                        reason=(
                            f"Temperature risk too high at position {preferred_position} "
                            f"(score: {match.temp_risk_score})"
                        ),
                        temp_risk_score=float(match.temp_risk_score),
                    )
                return match

        # Auto-select: filter feasible, sort by distance
        feasible = [c for c in candidates if c.temp_risk_score < TEMP_RISK_THRESHOLD]
        if not feasible:
            worst = max(candidates, key=lambda c: c.temp_risk_score)
            raise InsertionRejectedException(
                reason=f"No feasible insertion position (best score: {worst.temp_risk_score})",
                temp_risk_score=float(worst.temp_risk_score),
            )

        return min(feasible, key=lambda c: c.extra_distance_meters)

    async def _cas_update_route(
        self,
        route_id: UUID,
        expected_version: int,
        extra_distance_meters: int,
    ) -> int:
        """Atomic CAS update: bump version, update metrics."""
        new_version = expected_version + 1
        result = await self._session.execute(
            update(Route)
            .where(Route.id == route_id, Route.version == expected_version)
            .values(
                version=new_version,
                total_stops=Route.total_stops + 1,
                total_distance=Route.total_distance
                + Decimal(str(extra_distance_meters / 1000)),
                updated_at=func.now(),
            )
            .returning(Route.version)
        )

        row = result.first()
        if row is None:
            # Fetch current version for error message
            current = await self._session.scalar(
                select(Route.version).where(Route.id == route_id)
            )
            raise StaleRouteException(
                route_id=route_id,
                expected_version=expected_version,
                current_version=current,
            )

        return new_version

    async def _insert_stop_at_position(
        self,
        route: Route,
        shipment: Shipment,
        position: int,
    ) -> RouteStop:
        """Create a new RouteStop at the given position."""
        ordered_stops = route.get_stops_ordered()

        if position < 1 or position > len(ordered_stops) + 1:
            raise ValueError(
                f"Invalid position {position} for route with {len(ordered_stops)} stops"
            )

        # Estimate arrival time based on adjacent stops
        if position <= len(ordered_stops) and ordered_stops:
            idx = min(position - 1, len(ordered_stops) - 1)
            ref_stop = ordered_stops[idx]
            expected_arrival = ref_stop.expected_arrival_at
            expected_departure = ref_stop.expected_departure_at
        else:
            expected_arrival = route.planned_departure_at or datetime.utcnow()
            expected_departure = expected_arrival

        new_stop = RouteStop(
            route_id=route.id,
            shipment_id=shipment.id,
            sequence_number=position,
            location=shipment.geo_location,
            address=shipment.delivery_address,
            expected_arrival_at=expected_arrival,
            expected_departure_at=expected_departure,
            predicted_arrival_temp=route.initial_temperature,
            is_temp_feasible=True,
        )
        self._session.add(new_stop)
        await self._session.flush()
        return new_stop

    async def _resequence_stops(
        self,
        route_id: UUID,
        from_position: int,
    ) -> None:
        """Increment sequence_number for all stops at or after from_position."""
        await self._session.execute(
            update(RouteStop)
            .where(
                RouteStop.route_id == route_id,
                RouteStop.sequence_number >= from_position,
            )
            .values(sequence_number=RouteStop.sequence_number + 1)
        )

    def _estimate_extra_distance(
        self,
        ordered_stops: list[RouteStop],
        position: int,
        shipment: Shipment,
    ) -> int:
        """
        Estimate detour distance in meters for inserting at a position.

        Uses a simple geometric estimate based on existing stop distances.
        In production, this would call a routing API for precise distances.
        """
        if not ordered_stops:
            return 0

        # Estimate based on average inter-stop distance
        total_dist_km = sum(
            float(s.distance_from_prev or 0) for s in ordered_stops
        )
        num_legs = max(len(ordered_stops), 1)
        avg_leg_km = total_dist_km / num_legs

        # Detour adds roughly 2x an average leg (go to new stop + return)
        # minus the original direct leg that's replaced
        detour_km = avg_leg_km * 1.5
        return int(detour_km * 1000)

    def _estimate_delay_impact(self, extra_distance_meters: int) -> int:
        """Estimate delay in minutes from extra distance."""
        speed_kmh = float(self._settings.average_speed_kmh)
        extra_km = extra_distance_meters / 1000.0
        return int((extra_km / speed_kmh) * 60)
