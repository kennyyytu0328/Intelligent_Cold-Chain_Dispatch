"""
AffinityUpdateService -- processes completed routes to update
VehicleHexAffinity and RouteHexStat records via running averages.
"""
import asyncio
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import List
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.geo import RouteHexStat, VehicleHexAffinity


class AffinityUpdateService:
    """Computes delivery success metrics and upserts affinity data."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ── Public API ───────────────────────────────────────────────────────

    async def process_completed_route(self, route) -> None:
        """Process a completed route: compute score, upsert affinities."""
        stops: list = list(route.stops) if route.stops else []
        score = self._compute_success_score(stops)
        route.actual_success_score = score

        signature = route.route_signature
        if not signature or not stops:
            return

        on_time_rate = self._compute_on_time_rate(stops)
        temp_compliance_rate = self._compute_temp_compliance_rate(stops)

        cells = self._extract_cells(signature)
        for cell in cells:
            await self._upsert_vehicle_affinity(
                vehicle_id=route.vehicle_id,
                h3_index=cell,
                success_score=score,
                on_time_rate=on_time_rate,
                temp_compliance=temp_compliance_rate,
            )
            await self._upsert_route_hex_stat(h3_index=cell, stops=stops)

    # ── Score Computation ────────────────────────────────────────────────

    def _compute_success_score(self, stops: list) -> Decimal:
        """(on_time_count + temp_ok_count) / (2 * total_stops)."""
        if not stops:
            return Decimal("0.000")

        on_time_count = sum(1 for s in stops if self._is_on_time(s))
        temp_ok_count = sum(1 for s in stops if s.is_temp_feasible is True)
        total = 2 * len(stops)

        raw = Decimal(on_time_count + temp_ok_count) / Decimal(total)
        return raw.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

    def _compute_on_time_rate(self, stops: list) -> Decimal:
        """Fraction of stops that arrived on time."""
        if not stops:
            return Decimal("0.000")
        count = sum(1 for s in stops if self._is_on_time(s))
        raw = Decimal(count) / Decimal(len(stops))
        return raw.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

    def _compute_temp_compliance_rate(self, stops: list) -> Decimal:
        """Fraction of stops with acceptable temperature."""
        if not stops:
            return Decimal("0.000")
        count = sum(1 for s in stops if s.is_temp_feasible is True)
        raw = Decimal(count) / Decimal(len(stops))
        return raw.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

    @staticmethod
    def _is_on_time(stop) -> bool:
        """A stop is on-time if actual_arrival <= expected_departure."""
        return (
            stop.actual_arrival_at is not None
            and stop.actual_arrival_at <= stop.expected_departure_at
        )

    # ── Running Average ──────────────────────────────────────────────────

    @staticmethod
    def _running_average(
        old_score: Decimal,
        old_sample_size: int,
        new_value: Decimal,
    ) -> Decimal:
        """Incremental mean: (old * n + new) / (n + 1)."""
        if old_sample_size == 0:
            return Decimal(new_value).quantize(
                Decimal("0.001"), rounding=ROUND_HALF_UP
            )
        result = (old_score * old_sample_size + new_value) / (old_sample_size + 1)
        return result.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

    # ── Upsert Helpers ───────────────────────────────────────────────────

    @staticmethod
    async def _resolve(value):
        """Await a value if it is awaitable, otherwise return it directly.

        This handles the difference between real SQLAlchemy Result
        (sync scalar_one_or_none) and AsyncMock in tests.
        """
        if asyncio.iscoroutine(value) or asyncio.isfuture(value):
            return await value
        return value

    async def _upsert_vehicle_affinity(
        self,
        vehicle_id,
        h3_index: str,
        success_score: Decimal,
        on_time_rate: Decimal,
        temp_compliance: Decimal,
    ) -> None:
        """Insert or update a VehicleHexAffinity row."""
        stmt = select(VehicleHexAffinity).where(
            VehicleHexAffinity.vehicle_id == vehicle_id,
            VehicleHexAffinity.h3_index == h3_index,
        )
        result = await self.session.execute(stmt)
        existing = await self._resolve(result.scalar_one_or_none())

        now = datetime.now(timezone.utc)

        if existing is not None:
            existing.affinity_score = self._running_average(
                existing.affinity_score, existing.sample_size, success_score
            )
            existing.avg_on_time_rate = self._running_average(
                existing.avg_on_time_rate or Decimal("0.000"),
                existing.sample_size,
                on_time_rate,
            )
            existing.avg_temp_compliance_rate = self._running_average(
                existing.avg_temp_compliance_rate or Decimal("0.000"),
                existing.sample_size,
                temp_compliance,
            )
            existing.sample_size += 1
            existing.last_delivery_at = now
            existing.updated_at = now
        else:
            affinity = VehicleHexAffinity(
                vehicle_id=vehicle_id,
                h3_index=h3_index,
                affinity_score=success_score,
                sample_size=1,
                avg_on_time_rate=on_time_rate,
                avg_temp_compliance_rate=temp_compliance,
                last_delivery_at=now,
                updated_at=now,
            )
            self.session.add(affinity)

    async def _upsert_route_hex_stat(
        self, h3_index: str, stops: list
    ) -> None:
        """Insert or update a RouteHexStat row."""
        stmt = select(RouteHexStat).where(RouteHexStat.h3_index == h3_index)
        result = await self.session.execute(stmt)
        existing = await self._resolve(result.scalar_one_or_none())

        now = datetime.now(timezone.utc)

        if existing is not None:
            existing.total_deliveries += len(stops)
            existing.updated_at = now
        else:
            stat = RouteHexStat(
                h3_index=h3_index,
                total_deliveries=len(stops),
                updated_at=now,
            )
            self.session.add(stat)

    # ── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _extract_cells(route_signature) -> List[str]:
        """Extract H3 cells from route_signature (JSON list or string)."""
        if not route_signature:
            return []
        if isinstance(route_signature, list):
            return [str(c).strip() for c in route_signature if c]
        return [c.strip() for c in str(route_signature).split(",") if c.strip()]
