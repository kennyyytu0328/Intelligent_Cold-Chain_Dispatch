"""Tests for TemperatureTracker -- post-solution temperature analysis."""
import pytest
from unittest.mock import MagicMock

from app.services.solver.callbacks import TemperatureTracker
from app.services.solver.data_model import (
    VRPDataModel,
    compute_distance_matrix,
    compute_time_matrix,
)


@pytest.fixture
def tracker_setup(make_depot_node, make_location_node, make_vehicle_data):
    """Data model + tracker for temperature testing."""
    depot = make_depot_node()
    node1 = make_location_node(
        index=1, latitude=25.04, longitude=121.52,
        temp_limit_upper=5.0, is_strict_sla=True,
    )
    node2 = make_location_node(
        index=2, latitude=25.05, longitude=121.53,
        temp_limit_upper=8.0, is_strict_sla=False,
    )
    nodes = [depot, node1, node2]
    vehicle = make_vehicle_data(k_value=0.05, initial_temp=-5.0, cooling_rate=-2.5)

    dm = compute_distance_matrix(nodes)
    tm = compute_time_matrix(nodes, dm)

    data = VRPDataModel(
        nodes=nodes, vehicles=[vehicle],
        distance_matrix=dm, time_matrix=tm,
        ambient_temperature=30.0,
    )

    manager = MagicMock()
    manager.IndexToNode = lambda x: x

    tracker = TemperatureTracker(data, manager)
    return data, tracker


class TestCalculateRouteTemperatures:

    def test_returns_result_for_each_stop(self, tracker_setup):
        data, tracker = tracker_setup
        results = tracker.calculate_route_temperatures(0, [1, 2])
        assert len(results) == 2

    def test_result_has_required_keys(self, tracker_setup):
        _, tracker = tracker_setup
        results = tracker.calculate_route_temperatures(0, [1])
        r = results[0]
        for key in ("arrival_temp", "departure_temp", "transit_rise",
                     "door_rise", "cooling_effect", "is_feasible", "violation_amount"):
            assert key in r

    def test_departure_equals_arrival_plus_door_rise(self, tracker_setup):
        _, tracker = tracker_setup
        results = tracker.calculate_route_temperatures(0, [1])
        r = results[0]
        assert abs(r["departure_temp"] - (r["arrival_temp"] + r["door_rise"])) < 0.001

    def test_first_stop_starts_from_initial_temp(self, tracker_setup):
        data, tracker = tracker_setup
        results = tracker.calculate_route_temperatures(0, [1])
        vehicle = data.vehicles[0]
        travel_time = data.time_matrix[0][1]
        expected_rise = vehicle.calculate_transit_temp_rise(travel_time, 30.0, -5.0)
        expected_cooling = vehicle.calculate_cooling_effect(travel_time)
        expected_arrival = -5.0 + expected_rise + expected_cooling
        assert abs(results[0]["arrival_temp"] - expected_arrival) < 0.001


class TestTemperaturePenalty:

    def test_no_penalty_when_feasible(self, tracker_setup):
        _, tracker = tracker_setup
        penalty = tracker.get_temperature_penalty(0, [1])
        assert penalty == 0

    def test_infeasible_cost_for_strict_violation(
        self, make_depot_node, make_location_node, make_vehicle_data
    ):
        depot = make_depot_node()
        node = make_location_node(
            index=1, latitude=25.5, longitude=121.0,
            temp_limit_upper=-10.0,  # impossible to maintain
            is_strict_sla=True,
        )
        nodes = [depot, node]
        vehicle = make_vehicle_data(k_value=0.10, initial_temp=-5.0, cooling_rate=-0.1)

        dm = compute_distance_matrix(nodes)
        tm = compute_time_matrix(nodes, dm)
        data = VRPDataModel(
            nodes=nodes, vehicles=[vehicle],
            distance_matrix=dm, time_matrix=tm,
            ambient_temperature=35.0,
        )
        manager = MagicMock()
        manager.IndexToNode = lambda x: x
        tracker = TemperatureTracker(data, manager, infeasible_cost=10_000_000)

        assert tracker.get_temperature_penalty(0, [1]) == 10_000_000


class TestIsRouteFeasible:

    def test_feasible_route(self, tracker_setup):
        _, tracker = tracker_setup
        assert tracker.is_route_feasible(0, [1]) is True

    def test_infeasible_when_strict_violated(
        self, make_depot_node, make_location_node, make_vehicle_data
    ):
        depot = make_depot_node()
        node = make_location_node(
            index=1, latitude=25.5, longitude=121.0,
            temp_limit_upper=-10.0,
            is_strict_sla=True,
        )
        nodes = [depot, node]
        vehicle = make_vehicle_data(k_value=0.10, initial_temp=-5.0, cooling_rate=-0.1)

        dm = compute_distance_matrix(nodes)
        tm = compute_time_matrix(nodes, dm)
        data = VRPDataModel(
            nodes=nodes, vehicles=[vehicle],
            distance_matrix=dm, time_matrix=tm,
            ambient_temperature=35.0,
        )
        manager = MagicMock()
        manager.IndexToNode = lambda x: x
        tracker = TemperatureTracker(data, manager)

        assert tracker.is_route_feasible(0, [1]) is False
