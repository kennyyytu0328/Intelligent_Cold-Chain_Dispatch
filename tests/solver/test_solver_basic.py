"""Tests for ColdChainVRPSolver -- full solve with real OR-Tools."""
import pytest

from app.services.solver.solver import ColdChainVRPSolver, SolverResult
from app.services.solver.data_model import (
    VRPDataModel,
    compute_distance_matrix,
    compute_time_matrix,
)


@pytest.mark.solver
class TestSolverBasic:

    def test_solve_returns_solver_result(self, simple_vrp_data):
        result = ColdChainVRPSolver(simple_vrp_data).solve()
        assert isinstance(result, SolverResult)

    def test_solver_finds_solution(self, simple_vrp_data):
        result = ColdChainVRPSolver(simple_vrp_data).solve()
        assert result.is_success is True
        assert result.status in ("OPTIMAL", "FEASIBLE")

    def test_solver_assigns_all_shipments(self, simple_vrp_data):
        result = ColdChainVRPSolver(simple_vrp_data).solve()
        assert result.shipments_assigned == 2
        assert len(result.unassigned_shipment_ids) == 0

    def test_solver_creates_routes(self, simple_vrp_data):
        result = ColdChainVRPSolver(simple_vrp_data).solve()
        assert result.vehicles_used >= 1
        assert len(result.routes) >= 1

    def test_route_stops_have_shipment_ids(self, simple_vrp_data):
        result = ColdChainVRPSolver(simple_vrp_data).solve()
        for route in result.routes:
            assert route.num_stops > 0
            for stop in route.stops:
                assert stop.shipment_id is not None

    def test_route_stops_have_temperatures(self, simple_vrp_data):
        result = ColdChainVRPSolver(simple_vrp_data).solve()
        for route in result.routes:
            for stop in route.stops:
                assert isinstance(stop.arrival_temp, (int, float))
                assert isinstance(stop.departure_temp, (int, float))

    def test_total_distance_positive(self, simple_vrp_data):
        result = ColdChainVRPSolver(simple_vrp_data).solve()
        assert result.total_distance_meters > 0

    def test_overweight_shipment_dropped(
        self, make_depot_node, make_location_node, make_vehicle_data
    ):
        depot = make_depot_node()
        heavy = make_location_node(
            index=1, latitude=25.04, longitude=121.52,
            demand_weight=5000.0,  # exceeds 1000 kg capacity
            is_strict_sla=False,
        )
        nodes = [depot, heavy]
        vehicle = make_vehicle_data(capacity_weight=1000.0)

        dm = compute_distance_matrix(nodes)
        tm = compute_time_matrix(nodes, dm)
        data = VRPDataModel(
            nodes=nodes, vehicles=[vehicle],
            distance_matrix=dm, time_matrix=tm,
            time_limit_seconds=10, earliest_departure_minutes=360,
        )

        result = ColdChainVRPSolver(data).solve()
        assert len(result.unassigned_shipment_ids) == 1


class TestSolverStatusMapping:

    @pytest.fixture
    def solver_instance(self):
        return ColdChainVRPSolver.__new__(ColdChainVRPSolver)

    def test_code_1_is_optimal(self, solver_instance):
        assert solver_instance._get_status_string(1) == "OPTIMAL"

    def test_code_2_is_feasible(self, solver_instance):
        assert solver_instance._get_status_string(2) == "FEASIBLE"

    def test_code_3_is_infeasible(self, solver_instance):
        assert solver_instance._get_status_string(3) == "INFEASIBLE"

    def test_code_4_is_timeout(self, solver_instance):
        assert solver_instance._get_status_string(4) == "TIMEOUT"

    def test_code_0_is_not_solved(self, solver_instance):
        assert solver_instance._get_status_string(0) == "NOT_SOLVED"

    def test_code_6_is_infeasible(self, solver_instance):
        assert solver_instance._get_status_string(6) == "INFEASIBLE"


class TestSolverResultProperties:

    def test_is_success_optimal(self):
        assert SolverResult(status="OPTIMAL", solver_status_code=1).is_success is True

    def test_is_success_feasible(self):
        assert SolverResult(status="FEASIBLE", solver_status_code=2).is_success is True

    def test_is_success_false_infeasible(self):
        assert SolverResult(status="INFEASIBLE", solver_status_code=6).is_success is False

    def test_is_success_false_timeout(self):
        assert SolverResult(status="TIMEOUT", solver_status_code=4).is_success is False
