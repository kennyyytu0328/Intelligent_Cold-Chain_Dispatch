"""Tests for route_signature computation in _save_routes (tasks.py)."""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional
from unittest.mock import MagicMock, patch, call

import pytest

from app.services.solver.solver import RouteResult, RouteStopResult, SolverResult


def _make_stop(seq, lat, lng, shipment_id="10000000-0000-0000-0000-000000000001"):
    """Create a minimal RouteStopResult for testing."""
    return RouteStopResult(
        sequence=seq,
        node_index=seq,
        shipment_id=shipment_id,
        address=f"Stop {seq}",
        latitude=lat,
        longitude=lng,
        arrival_time_minutes=480 + seq * 30,
        departure_time_minutes=495 + seq * 30,
        service_duration=15,
        slack_minutes=0,
        target_time_window_index=0,
        distance_from_prev_meters=5000,
        travel_time_from_prev_minutes=10,
        arrival_temp=-3.0,
        departure_temp=-2.5,
        transit_temp_rise=0.5,
        door_temp_rise=0.3,
        cooling_applied=-0.2,
        is_temp_feasible=True,
        temp_limit_upper=5.0,
        is_strict_sla=False,
    )


def _make_route_result(stops):
    """Create a minimal RouteResult."""
    return RouteResult(
        vehicle_index=0,
        vehicle_id="00000000-0000-0000-0000-000000000001",
        license_plate="TEST-001",
        driver_id=None,
        driver_name="Test Driver",
        stops=stops,
        total_distance_meters=15000,
        total_duration_minutes=90,
        total_weight_kg=500.0,
        total_volume_m3=2.0,
        initial_temp=-5.0,
        final_temp=-2.0,
        max_temp=-1.0,
        departure_time_minutes=360,
        return_time_minutes=540,
    )


def _make_solver_result(route_results):
    """Create a minimal SolverResult."""
    return SolverResult(
        status="OPTIMAL",
        solver_status_code=1,
        routes=route_results,
        total_cost=100000,
        total_distance_meters=15000,
        total_duration_minutes=90,
        vehicles_used=len(route_results),
        shipments_assigned=sum(len(r.stops) for r in route_results),
    )


def _make_data_model():
    """Create a minimal data_model with depot node."""
    depot = MagicMock()
    depot.latitude = 25.0
    depot.longitude = 121.5
    depot.address = "Depot"

    model = MagicMock()
    model.nodes = [depot]
    return model


class TestRouteSignature:
    """Tests that _save_routes computes route_signature via H3."""

    @patch("app.services.tasks.get_geo_provider")
    def test_signature_populated_with_unique_cells(self, mock_get_geo):
        """4 stops where 2 share the same H3 cell -> 3 unique cells in order."""
        from app.services.tasks import _save_routes

        # Mock geo provider: stops at different coords map to specific cells
        # Stop 1 (25.0, 121.5) -> cell_A
        # Stop 2 (25.1, 121.6) -> cell_B
        # Stop 3 (25.0, 121.5) -> cell_A  (duplicate!)
        # Stop 4 (25.2, 121.7) -> cell_C
        mock_geo = MagicMock()
        cell_map = {
            (25.0, 121.5): "8a28cb4f0c7ffff",
            (25.1, 121.6): "8a28cc0004fffff",
            (25.2, 121.7): "8a28cd0008fffff",
        }
        mock_geo.lat_lng_to_cell.side_effect = lambda lat, lng, res: cell_map[(lat, lng)]
        mock_get_geo.return_value = mock_geo

        stops = [
            _make_stop(1, 25.0, 121.5, "10000000-0000-0000-0000-000000000001"),
            _make_stop(2, 25.1, 121.6, "10000000-0000-0000-0000-000000000002"),
            _make_stop(3, 25.0, 121.5, "10000000-0000-0000-0000-000000000003"),  # Same cell as stop 1
            _make_stop(4, 25.2, 121.7, "10000000-0000-0000-0000-000000000004"),
        ]
        route_result = _make_route_result(stops)
        solver_result = _make_solver_result([route_result])
        data_model = _make_data_model()

        # Mock the DB session to capture route objects
        mock_session = MagicMock()
        added_objects = []
        mock_session.add.side_effect = lambda obj: added_objects.append(obj)

        job_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        plan = date(2024, 1, 30)

        _save_routes(mock_session, job_id, plan, solver_result, data_model)

        # Find the Route object (not RouteStop)
        from app.models import Route
        routes = [obj for obj in added_objects if isinstance(obj, Route)]
        assert len(routes) == 1

        sig = routes[0].route_signature
        assert sig == [
            "8a28cb4f0c7ffff",
            "8a28cc0004fffff",
            "8a28cd0008fffff",
        ]
        # 3 unique cells, not 4 (deduplication worked)
        assert len(sig) == 3

    @patch("app.services.tasks.get_geo_provider")
    def test_signature_preserves_order(self, mock_get_geo):
        """Route signature preserves stop visit order (not sorted)."""
        from app.services.tasks import _save_routes

        mock_geo = MagicMock()
        # Each stop maps to a unique cell, in specific order
        mock_geo.lat_lng_to_cell.side_effect = [
            "cell_Z",
            "cell_A",
            "cell_M",
        ]
        mock_get_geo.return_value = mock_geo

        stops = [
            _make_stop(1, 25.0, 121.5, "10000000-0000-0000-0000-000000000001"),
            _make_stop(2, 25.1, 121.6, "10000000-0000-0000-0000-000000000002"),
            _make_stop(3, 25.2, 121.7, "10000000-0000-0000-0000-000000000003"),
        ]
        route_result = _make_route_result(stops)
        solver_result = _make_solver_result([route_result])
        data_model = _make_data_model()

        mock_session = MagicMock()
        added_objects = []
        mock_session.add.side_effect = lambda obj: added_objects.append(obj)

        job_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

        _save_routes(mock_session, job_id, date(2024, 1, 30), solver_result, data_model)

        from app.models import Route
        routes = [obj for obj in added_objects if isinstance(obj, Route)]
        assert routes[0].route_signature == ["cell_Z", "cell_A", "cell_M"]

    @patch("app.services.tasks.get_geo_provider")
    def test_single_stop_route(self, mock_get_geo):
        """Single stop produces a single-element signature."""
        from app.services.tasks import _save_routes

        mock_geo = MagicMock()
        mock_geo.lat_lng_to_cell.return_value = "cell_only"
        mock_get_geo.return_value = mock_geo

        stops = [_make_stop(1, 25.0, 121.5)]
        route_result = _make_route_result(stops)
        solver_result = _make_solver_result([route_result])
        data_model = _make_data_model()

        mock_session = MagicMock()
        added_objects = []
        mock_session.add.side_effect = lambda obj: added_objects.append(obj)

        job_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

        _save_routes(mock_session, job_id, date(2024, 1, 30), solver_result, data_model)

        from app.models import Route
        routes = [obj for obj in added_objects if isinstance(obj, Route)]
        assert routes[0].route_signature == ["cell_only"]

    @patch("app.services.tasks.get_geo_provider")
    def test_multiple_routes_each_get_signature(self, mock_get_geo):
        """When solver produces multiple routes, each gets its own signature."""
        from app.services.tasks import _save_routes

        mock_geo = MagicMock()
        mock_geo.lat_lng_to_cell.side_effect = [
            "cell_r1_a", "cell_r1_b",  # Route 1 stops
            "cell_r2_x",               # Route 2 stop
        ]
        mock_get_geo.return_value = mock_geo

        route1 = _make_route_result([
            _make_stop(1, 25.0, 121.5, "10000000-0000-0000-0000-000000000001"),
            _make_stop(2, 25.1, 121.6, "10000000-0000-0000-0000-000000000002"),
        ])
        route2_result = RouteResult(
            vehicle_index=1,
            vehicle_id="00000000-0000-0000-0000-000000000002",
            license_plate="TEST-002",
            driver_id=None,
            driver_name="Driver B",
            stops=[_make_stop(1, 25.2, 121.7, "10000000-0000-0000-0000-000000000003")],
            total_distance_meters=8000,
            total_duration_minutes=45,
            departure_time_minutes=360,
            return_time_minutes=480,
        )
        solver_result = _make_solver_result([route1, route2_result])
        data_model = _make_data_model()

        mock_session = MagicMock()
        added_objects = []
        mock_session.add.side_effect = lambda obj: added_objects.append(obj)

        job_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

        _save_routes(mock_session, job_id, date(2024, 1, 30), solver_result, data_model)

        from app.models import Route
        routes = [obj for obj in added_objects if isinstance(obj, Route)]
        assert len(routes) == 2
        assert routes[0].route_signature == ["cell_r1_a", "cell_r1_b"]
        assert routes[1].route_signature == ["cell_r2_x"]
