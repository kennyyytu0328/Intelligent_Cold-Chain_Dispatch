"""
"Impossible Day" scenario tests for ColdChainVRPSolver.

Scenarios:
  - All drivers at/over weekly labor limit (enable_labor=True)
  - Tight capacity + STRICT SLA windows that cannot all be served
  - Combined scenario -- solver must not crash; graceful degradation expected
"""
from datetime import date
from uuid import uuid4

import pytest

from app.services.solver.data_model import (
    VRPDataModel,
    VehicleData,
    LocationNode,
    compute_distance_matrix,
    compute_time_matrix,
)
from app.services.solver.solver import ColdChainVRPSolver


PLAN_DATE = date(2024, 1, 30)
DEPOT_LAT = 25.0330
DEPOT_LON = 121.5654


def _depot() -> LocationNode:
    return LocationNode(
        index=0,
        latitude=DEPOT_LAT,
        longitude=DEPOT_LON,
        address="Depot",
        time_windows=[(0, 1440)],
        service_duration=0,
    )


def _delivery(
    index: int,
    lat: float,
    lon: float,
    time_windows=None,
    is_strict_sla: bool = True,
    demand_weight: float = 50.0,
) -> LocationNode:
    if time_windows is None:
        time_windows = [(480, 720)]
    return LocationNode(
        index=index,
        latitude=lat,
        longitude=lon,
        address=f"Stop {index}",
        shipment_id=str(uuid4()),
        time_windows=time_windows,
        service_duration=15,
        demand_weight=demand_weight,
        demand_volume=0.5,
        temp_limit_upper=5.0,
        is_strict_sla=is_strict_sla,
    )


def _vehicle(
    index: int,
    driver_id: str = None,
    capacity_weight: float = 1000.0,
) -> VehicleData:
    return VehicleData(
        index=index,
        vehicle_id=str(uuid4()),
        license_plate=f"ABC-{index:03d}",
        capacity_weight=capacity_weight,
        capacity_volume=10.0,
        k_value=0.05,
        door_coefficient=0.8,
        has_strip_curtains=False,
        cooling_rate=-2.5,
        initial_temp=-5.0,
        driver_id=driver_id or str(uuid4()),
        driver_name=f"Driver {index}",
    )


def _build_model(nodes, vehicles, time_limit=30) -> VRPDataModel:
    dist = compute_distance_matrix(nodes)
    time_m = compute_time_matrix(nodes, dist)
    return VRPDataModel(
        nodes=nodes,
        vehicles=vehicles,
        distance_matrix=dist,
        time_matrix=time_m,
        ambient_temperature=30.0,
        time_limit_seconds=time_limit,
        earliest_departure_minutes=360,
    )


@pytest.mark.solver
class TestImpossibleDay:

    def test_all_drivers_at_weekly_limit_labor_enabled(self):
        """All drivers have accumulated_weekly_minutes == weekly limit (2880).

        With labor enabled as soft constraints, the solver should still return a
        result (may drop or assign with high penalty). Must not crash.
        """
        depot = _depot()
        v1 = _vehicle(index=0)
        v2 = _vehicle(index=1)
        nodes = [
            depot,
            _delivery(1, 25.048, 121.517),
            _delivery(2, 25.020, 121.540),
            _delivery(3, 25.035, 121.560),
        ]
        model = _build_model(nodes, [v1, v2])

        # Both drivers are at their weekly limit
        weekly_limit = 2880
        model.driver_weekly_cache = {
            v1.driver_id: weekly_limit,
            v2.driver_id: weekly_limit,
        }
        model.driver_daily_cache = {
            v1.driver_id: weekly_limit,
            v2.driver_id: weekly_limit,
        }

        solver = ColdChainVRPSolver(model, PLAN_DATE, enable_labor=True)
        result = solver.solve()

        # Must not raise; result must be a valid SolverResult
        assert result is not None
        total = sum(r.num_stops for r in result.routes) + len(result.unassigned_shipment_ids)
        assert total == 3  # all 3 shipments accounted for

    def test_tight_capacity_strict_sla_no_feasible_window(self):
        """10 STRICT shipments all want a 5-minute window (6:00–6:05 = [360,365]).

        A single vehicle cannot serve all 10 within such a narrow window.
        Some must be unassigned.
        """
        depot = _depot()
        v = _vehicle(index=0, capacity_weight=10000.0)  # plenty of capacity
        nodes = [depot] + [
            _delivery(
                index=i + 1,
                lat=25.04 + i * 0.002,
                lon=121.52 + i * 0.002,
                time_windows=[(360, 365)],  # 6:00–6:05 — impossible for many
                is_strict_sla=True,
            )
            for i in range(10)
        ]
        model = _build_model(nodes, [v])

        solver = ColdChainVRPSolver(model, PLAN_DATE)
        result = solver.solve()

        assert result is not None
        # With a 5-minute window for 10 shipments, most must be dropped
        assert len(result.unassigned_shipment_ids) > 0

    def test_impossible_day_does_not_crash(self):
        """Combined: overworked drivers + near-capacity vehicles + STRICT SLA.

        Solver must return a valid result (not raise) in both labor modes.
        """
        depot = _depot()
        # Two vehicles nearly at weight capacity per stop
        v1 = _vehicle(index=0, capacity_weight=100.0)  # tight: each stop = 50kg
        v2 = _vehicle(index=1, capacity_weight=100.0)
        nodes = [depot] + [
            _delivery(
                index=i + 1,
                lat=25.04 + i * 0.003,
                lon=121.52 + i * 0.003,
                time_windows=[(360, 370)],  # very tight STRICT window
                is_strict_sla=True,
                demand_weight=55.0,  # exceeds single-vehicle capacity per two stops
            )
            for i in range(6)
        ]
        model = _build_model(nodes, [v1, v2])

        # Overwork drivers
        limit = 2880
        model.driver_weekly_cache = {v1.driver_id: limit, v2.driver_id: limit}
        model.driver_daily_cache = {v1.driver_id: limit, v2.driver_id: limit}

        for enable_labor in (False, True):
            solver = ColdChainVRPSolver(model, PLAN_DATE, enable_labor=enable_labor)
            result = solver.solve()
            assert result is not None, f"Solver crashed with enable_labor={enable_labor}"

    def test_result_structure_valid_under_partial_assignment(self):
        """Routes that DO get assigned in a constrained scenario have valid structure."""
        depot = _depot()
        v = _vehicle(index=0, capacity_weight=200.0)
        # 4 shipments in normal window + 4 in impossible narrow window
        nodes = [depot]
        for i in range(4):
            nodes.append(_delivery(
                index=i + 1,
                lat=25.040 + i * 0.002,
                lon=121.520 + i * 0.002,
                time_windows=[(480, 720)],  # normal 8am-12pm
                is_strict_sla=False,
            ))
        for i in range(4):
            nodes.append(_delivery(
                index=i + 5,
                lat=25.048 + i * 0.002,
                lon=121.528 + i * 0.002,
                time_windows=[(360, 362)],  # impossible 2-minute STRICT window
                is_strict_sla=True,
            ))

        model = _build_model(nodes, [v])
        solver = ColdChainVRPSolver(model, PLAN_DATE)
        result = solver.solve()

        assert result is not None
        for route in result.routes:
            assert route.num_stops >= 0
            for stop in route.stops:
                assert stop.shipment_id is not None
                assert isinstance(stop.arrival_temp, (int, float))
                assert isinstance(stop.departure_temp, (int, float))

    def test_unassigned_ids_are_strings(self):
        """Regression: unassigned_shipment_ids must be string UUIDs, not UUID objects."""
        depot = _depot()
        v = _vehicle(index=0, capacity_weight=50.0)  # only fits 1 stop
        nodes = [depot] + [
            _delivery(index=i + 1, lat=25.04 + i * 0.002, lon=121.52 + i * 0.002)
            for i in range(3)  # 3 × 50kg > 50kg capacity → some dropped
        ]
        model = _build_model(nodes, [v])
        solver = ColdChainVRPSolver(model, PLAN_DATE)
        result = solver.solve()

        for sid in result.unassigned_shipment_ids:
            assert isinstance(sid, str), f"Expected str, got {type(sid)}: {sid}"
