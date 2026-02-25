"""
Integration-level tests for the affinity pipeline:
delivery completion -> success score computation -> affinity upsert.
"""
import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.models.geo import VehicleHexAffinity
from app.services.recommendation.affinity_update import AffinityUpdateService


def _make_stop(*, on_time: bool, temp_ok: bool) -> MagicMock:
    """Build a mock RouteStop with delivery outcome flags."""
    stop = MagicMock()
    stop.is_temp_feasible = temp_ok
    stop.delivery_status = "DELIVERED"

    if on_time:
        stop.actual_arrival_at = datetime(2025, 6, 1, 9, 0, tzinfo=timezone.utc)
        stop.expected_departure_at = datetime(2025, 6, 1, 10, 0, tzinfo=timezone.utc)
    else:
        stop.actual_arrival_at = datetime(2025, 6, 1, 11, 0, tzinfo=timezone.utc)
        stop.expected_departure_at = datetime(2025, 6, 1, 10, 0, tzinfo=timezone.utc)

    return stop


def _make_route(*, stops, signature):
    """Build a mock Route with stops and route_signature."""
    route = MagicMock()
    route.stops = stops
    route.route_signature = signature
    route.vehicle_id = uuid4()
    route.actual_success_score = None
    return route


class TestAffinityPipelineIntegration:
    """End-to-end pipeline: completed delivery -> affinity score changes."""

    @pytest.mark.asyncio
    async def test_good_delivery_raises_affinity(self):
        """Perfect delivery (all on-time, all temp-ok) creates affinity=1.000."""
        stops = [
            _make_stop(on_time=True, temp_ok=True),
            _make_stop(on_time=True, temp_ok=True),
        ]
        route = _make_route(stops=stops, signature=["87283472bffffff"])

        session = AsyncMock()

        # Both execute calls (affinity lookup, hex stat lookup) return None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        svc = AffinityUpdateService(session)
        await svc.process_completed_route(route)

        # Score: (2 on_time + 2 temp_ok) / (2 * 2) = 1.000
        assert route.actual_success_score == Decimal("1.000")

        # session.add should have been called with a VehicleHexAffinity
        add_calls = session.add.call_args_list
        affinity_added = None
        for call in add_calls:
            obj = call[0][0]
            if isinstance(obj, VehicleHexAffinity):
                affinity_added = obj
                break

        assert affinity_added is not None
        assert affinity_added.affinity_score == Decimal("1.000")
        assert affinity_added.sample_size == 1

    @pytest.mark.asyncio
    async def test_bad_delivery_lowers_existing_affinity(self):
        """Failed delivery blended via running average lowers existing affinity."""
        stops = [
            _make_stop(on_time=False, temp_ok=False),
        ]
        route = _make_route(stops=stops, signature=["87283472bffffff"])

        session = AsyncMock()

        # Existing affinity row to be updated
        existing = VehicleHexAffinity(
            vehicle_id=route.vehicle_id,
            h3_index="87283472bffffff",
            affinity_score=Decimal("0.900"),
            sample_size=9,
            avg_on_time_rate=Decimal("0.900"),
            avg_temp_compliance_rate=Decimal("0.900"),
        )

        # First execute -> returns existing VehicleHexAffinity
        # Second execute -> returns None (no RouteHexStat)
        call_count = 0

        def execute_side_effect(*_args, **_kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = existing
            else:
                result.scalar_one_or_none.return_value = None
            return result

        session.execute.side_effect = execute_side_effect

        svc = AffinityUpdateService(session)
        await svc.process_completed_route(route)

        # Score: (0 on_time + 0 temp_ok) / (2 * 1) = 0.000
        assert route.actual_success_score == Decimal("0.000")

        # Running average: (0.900 * 9 + 0.000) / 10 = 0.810
        assert existing.affinity_score == Decimal("0.810")
        assert existing.sample_size == 10
