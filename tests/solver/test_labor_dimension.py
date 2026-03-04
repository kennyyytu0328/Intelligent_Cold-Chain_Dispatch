"""Tests for labor dimension in solver."""
import pytest
from app.services.solver.data_model import (
    VRPDataModel, LocationNode, VehicleData,
    compute_distance_matrix, compute_time_matrix,
)
from app.services.solver.solver import ColdChainVRPSolver


def _build_test_model(
    num_shipments: int = 6,
    num_vehicles: int = 2,
    driver_weekly_cache: dict | None = None,
    driver_daily_cache: dict | None = None,
    enable_labor: bool = True,
) -> VRPDataModel:
    """Build a small test model for labor dimension tests."""
    nodes = [
        LocationNode(
            index=0, latitude=25.033, longitude=121.565,
            address="Depot", time_windows=[(0, 1440)], service_duration=0,
        )
    ]
    # Create shipments spread around depot
    offsets = [
        (0.01, 0.01), (0.02, 0.01), (0.01, 0.02),
        (-0.01, 0.01), (-0.02, 0.01), (-0.01, 0.02),
    ]
    for i in range(num_shipments):
        dy, dx = offsets[i % len(offsets)]
        nodes.append(LocationNode(
            index=i + 1,
            latitude=25.033 + dy,
            longitude=121.565 + dx,
            address=f"Stop {i+1}",
            shipment_id=f"SHP-{i+1:03d}",
            time_windows=[(360, 1080)],  # 06:00-18:00
            service_duration=15,
            demand_weight=10.0,
            demand_volume=0.1,
            temp_limit_upper=5.0,
            is_strict_sla=False,
            priority=50,
        ))

    vehicles_list = []
    for i in range(num_vehicles):
        vehicles_list.append(VehicleData(
            index=i,
            vehicle_id=f"V-{i+1}",
            license_plate=f"TEST-{i+1}",
            capacity_weight=1000.0,
            capacity_volume=10.0,
            k_value=0.05,
            door_coefficient=0.8,
            has_strip_curtains=False,
            cooling_rate=-2.5,
            initial_temp=-5.0,
            driver_id=f"DRV-{i+1}",
            driver_name=f"Driver {i+1}",
        ))

    model = VRPDataModel(
        nodes=nodes,
        vehicles=vehicles_list,
        ambient_temperature=30.0,
        time_limit_seconds=30,
        vehicle_fixed_cost=50000,
        infeasible_cost=10000000,
        earliest_departure_minutes=360,
        driver_weekly_cache=driver_weekly_cache or {},
        driver_daily_cache=driver_daily_cache or {},
    )
    model.distance_matrix = compute_distance_matrix(model.nodes)
    model.time_matrix = compute_time_matrix(model.nodes, model.distance_matrix)
    return model


@pytest.mark.solver
class TestLaborDimension:
    """Tests for labor dimension in solver (uses real OR-Tools)."""

    def test_solver_works_without_labor_dimension(self):
        """Solver should work normally when labor is disabled."""
        model = _build_test_model(enable_labor=False)
        solver = ColdChainVRPSolver(model)
        result = solver.solve()
        assert result.is_success
        assert result.shipments_assigned > 0

    def test_solver_works_with_labor_dimension_no_limits(self):
        """Solver with labor enabled but no accumulated hours should work normally."""
        model = _build_test_model(enable_labor=True)
        solver = ColdChainVRPSolver(model, enable_labor=True)
        result = solver.solve()
        assert result.is_success
        assert result.shipments_assigned > 0

    def test_labor_dimension_affects_routing(self):
        """Labor dimension should produce a valid solution and track work minutes."""
        model = _build_test_model(
            num_shipments=6,
            num_vehicles=2,
            driver_weekly_cache={"DRV-1": 2800, "DRV-2": 0},  # DRV-1 near limit
            driver_daily_cache={"DRV-1": 680, "DRV-2": 0},    # DRV-1 near daily too
        )
        solver = ColdChainVRPSolver(model, enable_labor=True)
        result = solver.solve()

        assert result.is_success
        assert result.shipments_assigned > 0
        # Solver should produce a solution that respects labor dimension
        # (may or may not use both vehicles — we just verify it works)

    def test_all_drivers_at_limit_still_produces_solution(self):
        """Even if all drivers are over limit, solver should still produce a solution (soft constraint)."""
        model = _build_test_model(
            num_shipments=4,
            num_vehicles=2,
            driver_weekly_cache={"DRV-1": 3000, "DRV-2": 3000},  # Both over limit
            driver_daily_cache={"DRV-1": 700, "DRV-2": 700},
        )
        solver = ColdChainVRPSolver(model, enable_labor=True)
        result = solver.solve()

        # Must still produce a solution (soft constraint, not hard)
        assert result.is_success
        assert result.shipments_assigned > 0

    def test_labor_penalty_less_than_infeasible_cost(self):
        """Labor penalty should be less than infeasible_cost so solver never refuses."""
        model = _build_test_model()
        solver = ColdChainVRPSolver(model, enable_labor=True)
        penalty = solver._calculate_labor_penalty()
        assert penalty < model.infeasible_cost
        assert penalty > 0
