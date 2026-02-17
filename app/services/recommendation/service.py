"""
Recommendation Service for Smart Assignment (v3.1).

Orchestrates vehicle ranking for route assignment using hex-cell affinity analysis.
"""
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import VehicleStatus
from app.models.route import Route
from app.models.vehicle import Vehicle
from app.services.recommendation.exceptions import (
    InsufficientDataException,
    InvalidRouteSignatureException,
)
from app.services.recommendation.pattern_analysis import PatternAnalysisService


class RecommendationService:
    """Orchestrates vehicle-route recommendation."""

    def __init__(self, session: AsyncSession):
        self._session = session
        self._pattern = PatternAnalysisService(session)

    async def recommend_for_route(
        self, route_id: UUID, top_k: int = 5
    ) -> dict:
        """Rank vehicles for a given route based on hex-cell affinity.

        Args:
            route_id: Route to find vehicles for.
            top_k: Maximum number of recommendations.

        Returns:
            Dict with route_id, route_signature, recommendations list.

        Raises:
            ValueError: Route not found.
            InvalidRouteSignatureException: Route has no signature.
            InsufficientDataException: No available vehicles.
        """
        result = await self._session.execute(
            select(Route).where(Route.id == route_id)
        )
        route = result.scalar_one_or_none()
        if route is None:
            raise ValueError(f"Route {route_id} not found")

        if not route.route_signature:
            raise InvalidRouteSignatureException(
                f"Route {route_id} has empty route_signature"
            )
        cells = list(route.route_signature)

        vehicles = await self._get_available_vehicles()
        if not vehicles:
            raise InsufficientDataException("No available vehicles found")

        recommendations = await self._rank_vehicles(vehicles, cells, top_k)

        return {
            "route_id": str(route_id),
            "route_signature": cells,
            "recommendations": recommendations,
        }

    async def recommend_for_coordinates(
        self,
        coords: list[tuple[float, float]],
        vehicle_ids: Optional[list[UUID]] = None,
        top_k: int = 5,
    ) -> dict:
        """Preview vehicle ranking for ad-hoc coordinates.

        Args:
            coords: List of (lat, lng) tuples.
            vehicle_ids: Optional filter for specific vehicles.
            top_k: Maximum recommendations.

        Returns:
            Dict with route_signature and recommendations.
        """
        cells = self._pattern.decompose_coordinates_to_cells(coords)

        vehicles = await self._get_available_vehicles(vehicle_ids)
        if not vehicles:
            raise InsufficientDataException("No available vehicles found")

        recommendations = await self._rank_vehicles(vehicles, cells, top_k)

        return {
            "route_id": None,
            "route_signature": cells,
            "recommendations": recommendations,
        }

    async def accept_recommendation(
        self, route_id: UUID, vehicle_id: UUID, user_id: UUID
    ) -> dict:
        """Assign a recommended vehicle to a route.

        Args:
            route_id: Route to assign vehicle to.
            vehicle_id: Vehicle to assign.
            user_id: User making the assignment.

        Returns:
            Dict with route_id, vehicle_id, status.

        Raises:
            ValueError: Route or vehicle not found.
        """
        route_result = await self._session.execute(
            select(Route).where(Route.id == route_id)
        )
        route = route_result.scalar_one_or_none()
        if route is None:
            raise ValueError(f"Route {route_id} not found")

        vehicle_result = await self._session.execute(
            select(Vehicle).where(Vehicle.id == vehicle_id)
        )
        vehicle = vehicle_result.scalar_one_or_none()
        if vehicle is None:
            raise ValueError(f"Vehicle {vehicle_id} not found")

        await self._session.execute(
            update(Route)
            .where(Route.id == route_id)
            .values(
                vehicle_id=vehicle_id,
                driver_id=vehicle.driver_id,
                driver_name=vehicle.driver_name,
            )
        )
        await self._session.flush()

        return {
            "route_id": str(route_id),
            "vehicle_id": str(vehicle_id),
            "status": "ASSIGNED",
        }

    async def _get_available_vehicles(
        self, vehicle_ids: Optional[list[UUID]] = None
    ) -> list[Vehicle]:
        """Get vehicles filtered by status and optional ID list."""
        query = select(Vehicle).where(Vehicle.status == VehicleStatus.AVAILABLE)

        if vehicle_ids:
            query = query.where(Vehicle.id.in_(vehicle_ids))

        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def _rank_vehicles(
        self, vehicles: list[Vehicle], cells: list[str], top_k: int
    ) -> list[dict]:
        """Calculate affinity for each vehicle and sort descending."""
        scored = []
        for vehicle in vehicles:
            analysis = await self._pattern.calculate_vehicle_affinity(
                vehicle.id, cells
            )
            scored.append({
                "vehicle_id": str(vehicle.id),
                "license_plate": vehicle.license_plate,
                "driver_name": vehicle.driver_name,
                "affinity_score": analysis["affinity_score"],
                "confidence": analysis["confidence"],
                "cell_details": analysis["cell_details"],
            })

        scored.sort(key=lambda x: x["affinity_score"], reverse=True)
        return scored[:top_k]
