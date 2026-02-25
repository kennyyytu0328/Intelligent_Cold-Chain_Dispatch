"""Unit tests for AffinityUpdateService (RED phase -- service does not exist yet)."""
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.recommendation.affinity_update import AffinityUpdateService


# ─── Mock Helpers ────────────────────────────────────────────────────────────


def _make_mock_stop(on_time: bool = True, temp_ok: bool = True):
    """Create a mock RouteStop with controllable on_time / temp_ok flags."""
    stop = MagicMock()
    stop.is_temp_feasible = temp_ok
    stop.delivery_status = "DELIVERED"

    if on_time:
        stop.actual_arrival_at = datetime(2024, 1, 30, 8, 0)
        stop.expected_departure_at = datetime(2024, 1, 30, 8, 30)
    else:
        # Arrived after the expected departure window
        stop.actual_arrival_at = datetime(2024, 1, 30, 9, 0)
        stop.expected_departure_at = datetime(2024, 1, 30, 8, 30)

    return stop


def _make_mock_route(
    stops=None,
    route_signature="abc123",
    vehicle_id=None,
):
    """Create a mock Route object."""
    route = MagicMock()
    route.id = uuid4()
    route.vehicle_id = vehicle_id or uuid4()
    route.route_signature = route_signature
    route.actual_success_score = None
    route.stops = stops if stops is not None else []
    return route


def _build_service():
    """Build AffinityUpdateService without calling __init__ (pure method tests)."""
    svc = AffinityUpdateService.__new__(AffinityUpdateService)
    return svc


# =========================================================================
# TestComputeSuccessScore
# =========================================================================
class TestComputeSuccessScore:
    """Tests for _compute_success_score: (on_time + temp_ok) / (2 * total)."""

    def test_all_perfect(self):
        svc = _build_service()
        stops = [_make_mock_stop(on_time=True, temp_ok=True) for _ in range(3)]
        result = svc._compute_success_score(stops)
        assert result == Decimal("1.000")

    def test_all_failed(self):
        svc = _build_service()
        stops = [_make_mock_stop(on_time=False, temp_ok=False) for _ in range(3)]
        result = svc._compute_success_score(stops)
        assert result == Decimal("0.000")

    def test_mixed_results(self):
        """Two stops: one perfect (2/2), one half-failed on_time=False temp_ok=True (1/2).
        Total = 3 / 4 = 0.750."""
        svc = _build_service()
        stops = [
            _make_mock_stop(on_time=True, temp_ok=True),
            _make_mock_stop(on_time=False, temp_ok=True),
        ]
        result = svc._compute_success_score(stops)
        assert result == Decimal("0.750")

    def test_empty_stops(self):
        svc = _build_service()
        result = svc._compute_success_score([])
        assert result == Decimal("0.000")


# =========================================================================
# TestRunningAverage
# =========================================================================
class TestRunningAverage:
    """Tests for _running_average(old_score, old_sample_size, new_value)."""

    def test_first_delivery(self):
        """sample_size=0 means first observation, result should equal new_value."""
        svc = _build_service()
        result = svc._running_average(
            old_score=Decimal("0.000"),
            old_sample_size=0,
            new_value=Decimal("0.850"),
        )
        assert result == Decimal("0.850")

    def test_second_delivery(self):
        """Two observations: average of 0.800 and 0.600 = 0.700."""
        svc = _build_service()
        result = svc._running_average(
            old_score=Decimal("0.800"),
            old_sample_size=1,
            new_value=Decimal("0.600"),
        )
        assert result == Decimal("0.700")

    def test_large_sample_small_effect(self):
        """With n=99, a new value should barely change the running average."""
        svc = _build_service()
        result = svc._running_average(
            old_score=Decimal("0.900"),
            old_sample_size=99,
            new_value=Decimal("0.000"),
        )
        # (99 * 0.900 + 0.000) / 100 = 0.891
        assert result == Decimal("0.891")


# =========================================================================
# TestProcessCompletedRoute
# =========================================================================
class TestProcessCompletedRoute:
    """Tests for process_completed_route (async, needs mocked session)."""

    @pytest.fixture
    def session(self):
        return AsyncMock()

    @pytest.fixture
    def service(self, session):
        svc = AffinityUpdateService.__new__(AffinityUpdateService)
        svc.session = session
        return svc

    @pytest.mark.asyncio
    async def test_updates_actual_success_score(self, service, session):
        """Route's actual_success_score should be set after processing."""
        stops = [_make_mock_stop(on_time=True, temp_ok=True)]
        route = _make_mock_route(stops=stops, route_signature="sig_abc")

        await service.process_completed_route(route)

        assert route.actual_success_score == Decimal("1.000")

    @pytest.mark.asyncio
    async def test_skips_affinity_when_no_signature(self, service, session):
        """Should not upsert affinity when route_signature is empty/None."""
        stops = [_make_mock_stop(on_time=True, temp_ok=True)]
        route = _make_mock_route(stops=stops, route_signature="")

        await service.process_completed_route(route)

        # Score should still be computed
        assert route.actual_success_score == Decimal("1.000")
        # But session.execute should NOT be called for affinity upsert
        session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_route_with_no_stops(self, service, session):
        """Route with empty stops should get 0.000 and not crash."""
        route = _make_mock_route(stops=[], route_signature="sig_xyz")

        await service.process_completed_route(route)

        assert route.actual_success_score == Decimal("0.000")
