"""Tests for IncrementalInsertionService (Dynamic Insertion with CAS locking)."""
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.insertion.exceptions import (
    InsertionRejectedException,
    StaleRouteException,
)
from app.services.insertion.service import (
    IncrementalInsertionService,
    InsertionCandidate,
    TEMP_RISK_THRESHOLD,
)
from app.services.insertion.temperature_proxy import RiskLevel


# ─── Mock Helpers ────────────────────────────────────────────────────────────

def _make_mock_stop(seq, distance_from_prev=5.0, travel_time=10, service_duration=15):
    stop = MagicMock()
    stop.sequence_number = seq
    stop.distance_from_prev = Decimal(str(distance_from_prev))
    stop.travel_time_from_prev = travel_time
    stop.expected_arrival_at = datetime(2024, 1, 30, 8, 0)
    stop.expected_departure_at = datetime(2024, 1, 30, 8, 15)
    stop.shipment = MagicMock()
    stop.shipment.service_duration = service_duration
    return stop


def _make_mock_route(version=1, num_stops=2, initial_temp=-5.0):
    route = MagicMock()
    route.id = uuid4()
    route.version = version
    route.initial_temperature = Decimal(str(initial_temp))
    route.planned_departure_at = datetime(2024, 1, 30, 6, 0)
    stops = [_make_mock_stop(i + 1) for i in range(num_stops)]
    route.stops = stops
    route.get_stops_ordered.return_value = stops
    route.vehicle = MagicMock()
    route.vehicle.k_value = Decimal("0.05")
    route.vehicle.door_coefficient = Decimal("0.80")
    route.vehicle.has_strip_curtains = False
    route.vehicle.cooling_rate = Decimal("-2.50")
    return route


def _make_mock_shipment(temp_limit_upper=5.0):
    shipment = MagicMock()
    shipment.id = uuid4()
    shipment.temp_limit_upper = Decimal(str(temp_limit_upper))
    shipment.geo_location = "POINT(121.5 25.0)"
    shipment.delivery_address = "Test Address"
    shipment.service_duration = 15
    return shipment


def _make_mock_session():
    session = AsyncMock()
    session.execute = AsyncMock()
    session.scalar = AsyncMock(return_value=None)
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session


# ─── Tests: _select_best_candidate ──────────────────────────────────────────

class TestSelectBestCandidate:
    def _make_svc(self):
        session = _make_mock_session()
        return IncrementalInsertionService(session)

    def test_best_position_selection_picks_lowest_distance(self):
        """Among feasible candidates, pick the one with lowest extra distance."""
        svc = self._make_svc()
        candidates = [
            InsertionCandidate(1, extra_distance_meters=5000, delay_impact_minutes=10,
                               temp_risk_score=Decimal("0.3"), temp_risk_level=RiskLevel.GREEN),
            InsertionCandidate(2, extra_distance_meters=2000, delay_impact_minutes=4,
                               temp_risk_score=Decimal("0.4"), temp_risk_level=RiskLevel.GREEN),
            InsertionCandidate(3, extra_distance_meters=8000, delay_impact_minutes=16,
                               temp_risk_score=Decimal("0.2"), temp_risk_level=RiskLevel.GREEN),
        ]
        best = svc._select_best_candidate(candidates, preferred_position=None)
        assert best.position == 2
        assert best.extra_distance_meters == 2000

    def test_rejection_when_all_positions_risky(self):
        """When all candidates exceed risk threshold, raise InsertionRejectedException."""
        svc = self._make_svc()
        candidates = [
            InsertionCandidate(1, extra_distance_meters=5000, delay_impact_minutes=10,
                               temp_risk_score=Decimal("0.9"), temp_risk_level=RiskLevel.RED),
            InsertionCandidate(2, extra_distance_meters=3000, delay_impact_minutes=6,
                               temp_risk_score=Decimal("0.85"), temp_risk_level=RiskLevel.RED),
        ]
        with pytest.raises(InsertionRejectedException):
            svc._select_best_candidate(candidates, preferred_position=None)

    def test_preferred_position_used(self):
        """When preferred_position is set and feasible, it should be selected."""
        svc = self._make_svc()
        candidates = [
            InsertionCandidate(1, extra_distance_meters=2000, delay_impact_minutes=4,
                               temp_risk_score=Decimal("0.2"), temp_risk_level=RiskLevel.GREEN),
            InsertionCandidate(2, extra_distance_meters=5000, delay_impact_minutes=10,
                               temp_risk_score=Decimal("0.4"), temp_risk_level=RiskLevel.GREEN),
        ]
        best = svc._select_best_candidate(candidates, preferred_position=2)
        assert best.position == 2

    def test_preferred_position_rejected_if_risky(self):
        """When preferred position has risk > threshold, raise InsertionRejectedException."""
        svc = self._make_svc()
        candidates = [
            InsertionCandidate(1, extra_distance_meters=2000, delay_impact_minutes=4,
                               temp_risk_score=Decimal("0.3"), temp_risk_level=RiskLevel.GREEN),
            InsertionCandidate(2, extra_distance_meters=5000, delay_impact_minutes=10,
                               temp_risk_score=Decimal("0.95"), temp_risk_level=RiskLevel.RED),
        ]
        with pytest.raises(InsertionRejectedException) as exc_info:
            svc._select_best_candidate(candidates, preferred_position=2)
        assert "position 2" in str(exc_info.value)


# ─── Tests: attempt_insertion (full flow) ────────────────────────────────────

class TestAttemptInsertion:
    async def test_successful_insertion(self):
        """Full insertion flow: load -> evaluate -> CAS update -> insert stop -> audit."""
        route = _make_mock_route(version=3, num_stops=2)
        vehicle = route.vehicle
        shipment = _make_mock_shipment()
        user_id = uuid4()

        session = _make_mock_session()
        svc = IncrementalInsertionService(session)

        # Mock _load_entities
        with patch.object(svc, "_load_entities", return_value=(route, vehicle, shipment)):
            # Mock _cas_update_route to return new version
            with patch.object(svc, "_cas_update_route", return_value=4):
                # Mock _insert_stop_at_position
                with patch.object(svc, "_insert_stop_at_position", return_value=MagicMock()):
                    # Mock _resequence_stops
                    with patch.object(svc, "_resequence_stops", return_value=None):
                        result = await svc.attempt_insertion(
                            route_id=route.id,
                            shipment_id=shipment.id,
                            user_id=user_id,
                        )

        assert result["status"] == "ACCEPTED"
        assert result["updated_route_version"] == 4
        assert result["position"] >= 1
        # Verify audit record was added
        session.add.assert_called_once()
        session.flush.assert_awaited()

    async def test_cas_conflict_raises_stale(self):
        """When CAS update fails (version mismatch), StaleRouteException is raised."""
        route = _make_mock_route(version=1, num_stops=1)
        vehicle = route.vehicle
        shipment = _make_mock_shipment()
        user_id = uuid4()

        session = _make_mock_session()
        svc = IncrementalInsertionService(session)

        with patch.object(svc, "_load_entities", return_value=(route, vehicle, shipment)):
            with patch.object(
                svc, "_cas_update_route",
                side_effect=StaleRouteException(
                    route_id=route.id, expected_version=1, current_version=2,
                ),
            ):
                with pytest.raises(StaleRouteException) as exc_info:
                    await svc.attempt_insertion(
                        route_id=route.id,
                        shipment_id=shipment.id,
                        user_id=user_id,
                    )
                assert exc_info.value.expected_version == 1
                assert exc_info.value.current_version == 2

    async def test_audit_record_created(self):
        """Verify InsertionAttempt is added to session on successful insertion."""
        route = _make_mock_route(version=1, num_stops=1)
        vehicle = route.vehicle
        shipment = _make_mock_shipment()
        user_id = uuid4()

        session = _make_mock_session()
        svc = IncrementalInsertionService(session)

        with patch.object(svc, "_load_entities", return_value=(route, vehicle, shipment)):
            with patch.object(svc, "_cas_update_route", return_value=2):
                with patch.object(svc, "_insert_stop_at_position", return_value=MagicMock()):
                    with patch.object(svc, "_resequence_stops", return_value=None):
                        await svc.attempt_insertion(
                            route_id=route.id,
                            shipment_id=shipment.id,
                            user_id=user_id,
                        )

        # session.add should have been called with an InsertionAttempt
        added_obj = session.add.call_args[0][0]
        from app.models.insertion import InsertionAttempt
        assert isinstance(added_obj, InsertionAttempt)
        assert added_obj.status == "ACCEPTED"
        assert added_obj.route_id == route.id
        assert added_obj.shipment_id == shipment.id
        assert added_obj.attempted_by == user_id


# ─── Tests: _cas_update_route ────────────────────────────────────────────────

class TestCASUpdateRoute:
    async def test_cas_success(self):
        """CAS update returns new version when expected version matches."""
        session = _make_mock_session()
        route_id = uuid4()

        # Mock execute to return a row with the new version
        mock_result = MagicMock()
        mock_result.first.return_value = (2,)
        session.execute.return_value = mock_result

        svc = IncrementalInsertionService(session)
        new_ver = await svc._cas_update_route(route_id, expected_version=1, extra_distance_meters=5000)
        assert new_ver == 2

    async def test_cas_conflict(self):
        """CAS update raises StaleRouteException when version doesn't match."""
        session = _make_mock_session()
        route_id = uuid4()

        # Mock execute to return no row (version mismatch)
        mock_result = MagicMock()
        mock_result.first.return_value = None
        session.execute.return_value = mock_result

        # scalar returns the current version
        session.scalar.return_value = 5

        svc = IncrementalInsertionService(session)
        with pytest.raises(StaleRouteException) as exc_info:
            await svc._cas_update_route(route_id, expected_version=1, extra_distance_meters=5000)
        assert exc_info.value.expected_version == 1
        assert exc_info.value.current_version == 5


# ─── Tests: _resequence_stops ────────────────────────────────────────────────

class TestResequenceStops:
    async def test_resequence_executes_update(self):
        """Resequence should execute an UPDATE query to bump sequence numbers."""
        session = _make_mock_session()
        svc = IncrementalInsertionService(session)
        route_id = uuid4()

        await svc._resequence_stops(route_id, from_position=3)
        session.execute.assert_awaited_once()


# ─── Tests: preview_insertion ────────────────────────────────────────────────

class TestPreviewInsertion:
    async def test_preview_returns_candidates(self):
        """Preview should return sorted candidates and a recommended position."""
        route = _make_mock_route(version=5, num_stops=2)
        vehicle = route.vehicle
        shipment = _make_mock_shipment()

        session = _make_mock_session()
        svc = IncrementalInsertionService(session)

        with patch.object(svc, "_load_entities", return_value=(route, vehicle, shipment)):
            result = await svc.preview_insertion(
                route_id=route.id,
                shipment_id=shipment.id,
            )

        assert "candidates" in result
        assert "recommended_position" in result
        assert result["route_version"] == 5
        # Should have num_stops + 1 candidate positions (1 through 3)
        assert len(result["candidates"]) == 3
