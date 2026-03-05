"""
Chaos and load tests for concurrent insertion scenarios.

Covers:
  1. Load test: 50 concurrent insertions on the same route -- only one succeeds,
     the rest raise StaleRouteException.
  2. Chaos test: concurrent insertion + affinity recalculation running simultaneously
     via asyncio.gather without interference.
  3. Exception integrity and temperature-rejection edge cases.
"""
import asyncio
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
    TEMP_RISK_THRESHOLD,
    IncrementalInsertionService,
    InsertionCandidate,
)
from app.services.insertion.temperature_proxy import RiskLevel


# ─── Mock Helpers ─────────────────────────────────────────────────────────────

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


# ─── Load Tests ───────────────────────────────────────────────────────────────

class TestConcurrentInsertions:
    """Load tests for concurrent insertion attempts on the same route."""

    async def test_50_concurrent_insertions_only_one_succeeds(self):
        """50 concurrent attempt_insertion calls on the same route (version=1).

        Exactly one call should win the CAS race and return status='ACCEPTED'.
        The remaining 49 should surface as StaleRouteException.
        """
        route = _make_mock_route(version=1, num_stops=2)
        vehicle = route.vehicle
        shipment = _make_mock_shipment()
        user_id = uuid4()

        # Only the first CAS call wins
        cas_call_count = [0]

        def _fake_cas(route_id, expected_version, extra_distance_meters):
            cas_call_count[0] += 1
            if cas_call_count[0] == 1:
                return 2
            raise StaleRouteException(
                route_id=route_id,
                expected_version=expected_version,
                current_version=2,
            )

        session = _make_mock_session()
        svc = IncrementalInsertionService(session)

        with patch.object(svc, "_load_entities", return_value=(route, vehicle, shipment)):
            with patch.object(svc, "_cas_update_route", side_effect=_fake_cas):
                with patch.object(svc, "_insert_stop_at_position", return_value=MagicMock()):
                    with patch.object(svc, "_resequence_stops", return_value=None):
                        results = await asyncio.gather(
                            *[
                                svc.attempt_insertion(
                                    route_id=route.id,
                                    shipment_id=shipment.id,
                                    user_id=user_id,
                                )
                                for _ in range(50)
                            ],
                            return_exceptions=True,
                        )

        accepted = [r for r in results if isinstance(r, dict) and r.get("status") == "ACCEPTED"]
        stale = [r for r in results if isinstance(r, StaleRouteException)]

        assert len(accepted) == 1, f"Expected 1 ACCEPTED, got {len(accepted)}"
        assert len(stale) == 49, f"Expected 49 StaleRouteException, got {len(stale)}"
        assert accepted[0]["updated_route_version"] == 2

    async def test_concurrent_insertions_no_data_corruption(self):
        """10 insertions each seeing a higher version — all succeed cleanly.

        Verifies version counters increment without corruption when each
        coroutine is logically independent.
        """
        route = _make_mock_route(version=1, num_stops=2)
        vehicle = route.vehicle
        user_id = uuid4()
        shipments = [_make_mock_shipment() for _ in range(10)]

        next_version = [2]

        def _incrementing_cas(route_id, expected_version, extra_distance_meters):
            v = next_version[0]
            next_version[0] += 1
            return v

        session = _make_mock_session()
        svc = IncrementalInsertionService(session)

        with patch.object(svc, "_load_entities", side_effect=[
            (route, vehicle, s) for s in shipments
        ]):
            with patch.object(svc, "_cas_update_route", side_effect=_incrementing_cas):
                with patch.object(svc, "_insert_stop_at_position", return_value=MagicMock()):
                    with patch.object(svc, "_resequence_stops", return_value=None):
                        results = await asyncio.gather(
                            *[
                                svc.attempt_insertion(
                                    route_id=route.id,
                                    shipment_id=s.id,
                                    user_id=user_id,
                                )
                                for s in shipments
                            ],
                            return_exceptions=True,
                        )

        exceptions = [r for r in results if isinstance(r, Exception)]
        assert not exceptions, f"Unexpected exceptions: {exceptions}"

        returned_versions = sorted(r["updated_route_version"] for r in results)
        assert returned_versions == list(range(2, 12))
        assert all(r["status"] == "ACCEPTED" for r in results)


# ─── Chaos Tests ──────────────────────────────────────────────────────────────

class TestChaosScenario:
    """Chaos tests: insertion + affinity recalculation running concurrently."""

    async def test_concurrent_insert_and_affinity_update(self):
        """Insertion and PatternAnalysisService run in the same event loop.

        Both tasks should complete independently without interfering.
        """
        route = _make_mock_route(version=1, num_stops=2)
        vehicle = route.vehicle
        shipment = _make_mock_shipment()
        user_id = uuid4()
        vehicle_id = uuid4()

        affinity_payload = {
            "affinity_score": Decimal("0.750"),
            "confidence": "HIGH",
            "cell_details": [{"h3_index": "8928308280fffff", "affinity": Decimal("0.750")}],
        }

        async def _fake_affinity(vehicle_id, route_cells):
            await asyncio.sleep(0)  # yield to event loop
            return affinity_payload

        insertion_session = _make_mock_session()
        svc = IncrementalInsertionService(insertion_session)

        with patch.object(svc, "_load_entities", return_value=(route, vehicle, shipment)):
            with patch.object(svc, "_cas_update_route", return_value=2):
                with patch.object(svc, "_insert_stop_at_position", return_value=MagicMock()):
                    with patch.object(svc, "_resequence_stops", return_value=None):
                        from app.services.recommendation.pattern_analysis import (
                            PatternAnalysisService,
                        )
                        with patch.object(
                            PatternAnalysisService,
                            "calculate_vehicle_affinity",
                            side_effect=_fake_affinity,
                        ):
                            affinity_session = _make_mock_session()
                            pattern_svc = PatternAnalysisService(affinity_session)

                            insertion_result, affinity_out = await asyncio.gather(
                                svc.attempt_insertion(
                                    route_id=route.id,
                                    shipment_id=shipment.id,
                                    user_id=user_id,
                                ),
                                pattern_svc.calculate_vehicle_affinity(
                                    vehicle_id=vehicle_id,
                                    route_cells=["8928308280fffff"],
                                ),
                            )

        assert insertion_result["status"] == "ACCEPTED"
        assert insertion_result["updated_route_version"] == 2
        assert affinity_out["affinity_score"] == Decimal("0.750")
        assert affinity_out["confidence"] == "HIGH"

    async def test_stale_route_exception_contains_correct_versions(self):
        """StaleRouteException raised on CAS failure carries correct version info."""
        route = _make_mock_route(version=3, num_stops=1)
        vehicle = route.vehicle
        shipment = _make_mock_shipment()
        user_id = uuid4()

        session = _make_mock_session()
        svc = IncrementalInsertionService(session)

        with patch.object(svc, "_load_entities", return_value=(route, vehicle, shipment)):
            with patch.object(
                svc,
                "_cas_update_route",
                side_effect=StaleRouteException(
                    route_id=route.id,
                    expected_version=3,
                    current_version=7,
                ),
            ):
                with pytest.raises(StaleRouteException) as exc_info:
                    await svc.attempt_insertion(
                        route_id=route.id,
                        shipment_id=shipment.id,
                        user_id=user_id,
                    )

        exc = exc_info.value
        assert exc.expected_version == 3
        assert exc.current_version == 7
        assert exc.route_id == route.id

    async def test_insertion_rejected_if_temperature_risk_too_high(self):
        """When every candidate position exceeds TEMP_RISK_THRESHOLD, raise InsertionRejectedException.

        Exercises the 'hot-chain chaos' path where all positions are unsafe.
        """
        route = _make_mock_route(version=1, num_stops=2)
        vehicle = route.vehicle
        shipment = _make_mock_shipment(temp_limit_upper=0.0)
        user_id = uuid4()

        high_risk = TEMP_RISK_THRESHOLD + Decimal("0.05")
        risky_candidates = [
            InsertionCandidate(
                position=i + 1,
                extra_distance_meters=5000 * (i + 1),
                delay_impact_minutes=10 * (i + 1),
                temp_risk_score=high_risk,
                temp_risk_level=RiskLevel.RED,
            )
            for i in range(3)
        ]

        session = _make_mock_session()
        svc = IncrementalInsertionService(session)

        with patch.object(svc, "_load_entities", return_value=(route, vehicle, shipment)):
            with patch.object(svc, "_evaluate_all_positions", return_value=risky_candidates):
                with pytest.raises(InsertionRejectedException) as exc_info:
                    await svc.attempt_insertion(
                        route_id=route.id,
                        shipment_id=shipment.id,
                        user_id=user_id,
                    )

        exc = exc_info.value
        assert exc.temp_risk_score is not None
        assert exc.temp_risk_score > float(TEMP_RISK_THRESHOLD)
