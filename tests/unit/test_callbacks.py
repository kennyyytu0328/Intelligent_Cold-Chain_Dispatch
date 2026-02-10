"""Tests for app.services.solver.callbacks."""
import pytest
from unittest.mock import MagicMock

from app.services.solver.callbacks import (
    create_distance_callback,
    create_time_callback,
    create_weight_demand_callback,
    create_volume_demand_callback,
)


@pytest.fixture
def identity_manager():
    """Manager where IndexToNode is identity (index == node)."""
    manager = MagicMock()
    manager.IndexToNode = lambda x: x
    return manager


class TestDistanceCallback:

    def test_returns_correct_distance(self, simple_vrp_data, identity_manager):
        callback = create_distance_callback(simple_vrp_data, identity_manager)
        assert callback(0, 1) == simple_vrp_data.distance_matrix[0][1]

    def test_same_node_returns_zero(self, simple_vrp_data, identity_manager):
        callback = create_distance_callback(simple_vrp_data, identity_manager)
        assert callback(0, 0) == 0


class TestTimeCallback:

    def test_includes_service_time_for_non_depot(self, simple_vrp_data, identity_manager):
        callback = create_time_callback(simple_vrp_data, identity_manager)
        travel = simple_vrp_data.time_matrix[1][2]
        service = simple_vrp_data.nodes[1].service_duration
        assert callback(1, 2) == travel + service

    def test_no_service_time_at_depot(self, simple_vrp_data, identity_manager):
        callback = create_time_callback(simple_vrp_data, identity_manager)
        assert callback(0, 1) == simple_vrp_data.time_matrix[0][1]


class TestWeightDemandCallback:

    def test_depot_zero_demand(self, simple_vrp_data, identity_manager):
        callback = create_weight_demand_callback(simple_vrp_data, identity_manager)
        assert callback(0) == 0

    def test_shipment_node_demand_in_grams(self, simple_vrp_data, identity_manager):
        callback = create_weight_demand_callback(simple_vrp_data, identity_manager)
        expected = int(simple_vrp_data.nodes[1].demand_weight * 1000)
        assert callback(1) == expected


class TestVolumeDemandCallback:

    def test_depot_zero_demand(self, simple_vrp_data, identity_manager):
        callback = create_volume_demand_callback(simple_vrp_data, identity_manager)
        assert callback(0) == 0

    def test_shipment_node_demand_in_liters(self, simple_vrp_data, identity_manager):
        callback = create_volume_demand_callback(simple_vrp_data, identity_manager)
        expected = int(simple_vrp_data.nodes[1].demand_volume * 1000)
        assert callback(1) == expected
