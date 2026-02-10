"""Tests for app.services.solver.data_model."""
import pytest

from app.services.solver.data_model import (
    haversine_distance,
    time_str_to_minutes,
    compute_distance_matrix,
    compute_time_matrix,
    build_vrp_data_model,
    LocationNode,
    VehicleData,
    VRPDataModel,
)


class TestHaversineDistance:

    def test_same_point_is_zero(self):
        assert haversine_distance(25.033, 121.565, 25.033, 121.565) == 0.0

    def test_known_distance_taipei_taichung(self):
        dist = haversine_distance(25.033, 121.565, 24.148, 120.674)
        assert 120 < dist < 160  # ~130-140 km

    def test_symmetry(self):
        d1 = haversine_distance(25.0, 121.0, 24.0, 120.0)
        d2 = haversine_distance(24.0, 120.0, 25.0, 121.0)
        assert abs(d1 - d2) < 0.001

    def test_short_distance_within_city(self):
        dist = haversine_distance(25.033, 121.565, 25.048, 121.517)
        assert 3 < dist < 8  # ~5 km


class TestTimeStrToMinutes:

    def test_midnight(self):
        assert time_str_to_minutes("00:00") == 0

    def test_noon(self):
        assert time_str_to_minutes("12:00") == 720

    def test_eight_am(self):
        assert time_str_to_minutes("08:00") == 480

    def test_end_of_day(self):
        assert time_str_to_minutes("23:59") == 1439

    def test_with_minutes(self):
        assert time_str_to_minutes("14:30") == 870


class TestVehicleDataThermodynamics:

    @pytest.fixture
    def vehicle(self, make_vehicle_data):
        return make_vehicle_data(
            k_value=0.05, door_coefficient=0.8,
            has_strip_curtains=False, cooling_rate=-2.5,
        )

    def test_transit_rise_positive_when_ambient_hotter(self, vehicle):
        rise = vehicle.calculate_transit_temp_rise(60, 30.0, -5.0)
        assert rise > 0

    def test_transit_rise_exact_formula(self, vehicle):
        # (60/60) * (30 - (-5)) * 0.05 = 1 * 35 * 0.05 = 1.75
        rise = vehicle.calculate_transit_temp_rise(60, 30.0, -5.0)
        assert abs(rise - 1.75) < 0.001

    def test_transit_rise_zero_when_same_temp(self, vehicle):
        rise = vehicle.calculate_transit_temp_rise(60, -5.0, -5.0)
        assert rise == 0.0

    def test_door_rise_without_curtains(self, vehicle):
        # (15/60) * 0.8 * 1.0 = 0.2
        rise = vehicle.calculate_door_temp_rise(15)
        assert abs(rise - 0.2) < 0.001

    def test_door_rise_with_curtains(self, make_vehicle_data):
        vehicle = make_vehicle_data(has_strip_curtains=True, door_coefficient=0.8)
        # (15/60) * 0.8 * 0.5 = 0.1
        rise = vehicle.calculate_door_temp_rise(15)
        assert abs(rise - 0.1) < 0.001

    def test_cooling_effect_is_negative(self, vehicle):
        assert vehicle.calculate_cooling_effect(60) < 0

    def test_cooling_effect_exact_formula(self, vehicle):
        # (60/60) * -2.5 = -2.5
        effect = vehicle.calculate_cooling_effect(60)
        assert abs(effect - (-2.5)) < 0.001

    def test_zero_time_produces_zero(self, vehicle):
        assert vehicle.calculate_transit_temp_rise(0, 30, -5) == 0.0
        assert vehicle.calculate_door_temp_rise(0) == 0.0
        assert vehicle.calculate_cooling_effect(0) == 0.0


class TestLocationNode:

    def test_depot_is_depot(self, make_depot_node):
        depot = make_depot_node()
        assert depot.is_depot is True

    def test_shipment_node_is_not_depot(self, make_location_node):
        node = make_location_node(shipment_id="SHIP-001")
        assert node.is_depot is False


class TestVRPDataModel:

    def test_num_locations(self, simple_vrp_data):
        assert simple_vrp_data.num_locations == 3

    def test_num_vehicles(self, simple_vrp_data):
        assert simple_vrp_data.num_vehicles == 1

    def test_depot_index_is_zero(self, simple_vrp_data):
        assert simple_vrp_data.depot_index == 0

    def test_get_shipment_nodes_excludes_depot(self, simple_vrp_data):
        nodes = simple_vrp_data.get_shipment_nodes()
        assert len(nodes) == 2
        assert all(not n.is_depot for n in nodes)

    def test_distance_matrix_is_square(self, simple_vrp_data):
        n = simple_vrp_data.num_locations
        assert len(simple_vrp_data.distance_matrix) == n
        assert all(len(row) == n for row in simple_vrp_data.distance_matrix)

    def test_distance_matrix_diagonal_zero(self, simple_vrp_data):
        for i in range(simple_vrp_data.num_locations):
            assert simple_vrp_data.distance_matrix[i][i] == 0

    def test_time_matrix_is_square(self, simple_vrp_data):
        n = simple_vrp_data.num_locations
        assert len(simple_vrp_data.time_matrix) == n
        assert all(len(row) == n for row in simple_vrp_data.time_matrix)

    def test_get_node_by_shipment_id(self, simple_vrp_data):
        node = simple_vrp_data.nodes[1]
        found = simple_vrp_data.get_node_by_shipment_id(node.shipment_id)
        assert found is node

    def test_get_node_by_shipment_id_not_found(self, simple_vrp_data):
        assert simple_vrp_data.get_node_by_shipment_id("nonexistent") is None


class TestBuildVRPDataModel:

    def test_builds_correct_structure(self):
        vehicles = [{
            "id": "v1", "license_plate": "TEST-001",
            "capacity_weight": 1000, "capacity_volume": 10,
            "k_value": 0.05, "door_coefficient": 0.8,
            "has_strip_curtains": False, "cooling_rate": -2.5,
            "driver_id": None, "driver_name": "Driver A",
        }]
        shipments = [{
            "id": "s1", "delivery_address": "123 Test St",
            "latitude": 25.0478, "longitude": 121.5170,
            "time_windows": [{"start": "08:00", "end": "12:00"}],
            "sla_tier": "STANDARD", "temp_limit_upper": 5.0,
            "temp_limit_lower": None, "service_duration": 15,
            "weight": 50, "volume": 0.5, "priority": 50,
        }]

        model = build_vrp_data_model(
            vehicles=vehicles, shipments=shipments,
            depot_lat=25.033, depot_lon=121.565, depot_address="Depot",
        )

        assert model.num_locations == 2  # depot + 1 shipment
        assert model.num_vehicles == 1
        assert model.nodes[0].is_depot is True
        assert model.nodes[1].shipment_id == "s1"

    def test_custom_departure_time(self):
        model = build_vrp_data_model(
            vehicles=[{
                "id": "v1", "license_plate": "T-1",
                "capacity_weight": 1000, "capacity_volume": 10,
            }],
            shipments=[],
            depot_lat=25.0, depot_lon=121.0, depot_address="Depot",
            planned_departure_time="08:00",
        )
        assert model.earliest_departure_minutes == 480
