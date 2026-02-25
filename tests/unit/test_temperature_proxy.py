"""Tests for the Temperature Proxy Model (Dynamic Insertion risk scoring)."""
from decimal import Decimal
from unittest.mock import MagicMock

from app.services.insertion.temperature_proxy import RiskLevel, TemperatureProxy


# ─── Mock helpers ────────────────────────────────────────────────────────────

def _make_route(initial_temp=-5.0, stops=None):
    """Create a mock Route with ordered stops."""
    route = MagicMock()
    route.initial_temperature = Decimal(str(initial_temp))
    route.get_stops_ordered.return_value = stops or []
    return route


def _make_vehicle(k_value=0.05, door_coefficient=0.80, has_strip_curtains=False, cooling_rate=-2.5):
    """Create a mock Vehicle with thermodynamic properties."""
    vehicle = MagicMock()
    vehicle.k_value = Decimal(str(k_value))
    vehicle.door_coefficient = Decimal(str(door_coefficient))
    vehicle.has_strip_curtains = has_strip_curtains
    vehicle.cooling_rate = Decimal(str(cooling_rate))
    return vehicle


def _make_shipment(temp_limit_upper=5.0):
    """Create a mock Shipment with temperature constraint."""
    shipment = MagicMock()
    shipment.temp_limit_upper = Decimal(str(temp_limit_upper))
    return shipment


def _make_stop(sequence_number, travel_time_from_prev=10, service_duration=15):
    """Create a mock RouteStop."""
    stop = MagicMock()
    stop.sequence_number = sequence_number
    stop.travel_time_from_prev = travel_time_from_prev
    stop.shipment = MagicMock()
    stop.shipment.service_duration = service_duration
    return stop


# ─── Tests: Risk Level Thresholds ────────────────────────────────────────────

class TestGetRiskLevel:
    def test_green_below_half(self):
        assert TemperatureProxy.get_risk_level(Decimal("0.0")) == RiskLevel.GREEN
        assert TemperatureProxy.get_risk_level(Decimal("0.49")) == RiskLevel.GREEN

    def test_yellow_at_half(self):
        assert TemperatureProxy.get_risk_level(Decimal("0.5")) == RiskLevel.YELLOW
        assert TemperatureProxy.get_risk_level(Decimal("0.8")) == RiskLevel.YELLOW

    def test_red_above_threshold(self):
        assert TemperatureProxy.get_risk_level(Decimal("0.81")) == RiskLevel.RED
        assert TemperatureProxy.get_risk_level(Decimal("1.5")) == RiskLevel.RED

    def test_boundary_exactly_half(self):
        assert TemperatureProxy.get_risk_level(Decimal("0.5")) == RiskLevel.YELLOW

    def test_boundary_exactly_zero_eight(self):
        assert TemperatureProxy.get_risk_level(Decimal("0.8")) == RiskLevel.YELLOW


# ─── Tests: Risk Score Calculation ───────────────────────────────────────────

class TestCalculateRiskScore:
    """Tests for TemperatureProxy.calculate_risk_score()."""

    def test_risk_score_green_zone(self):
        """Small detour with good insulation should yield low risk (<0.5)."""
        proxy = TemperatureProxy(ambient_temperature=30.0, average_speed_kmh=30.0)
        route = _make_route(initial_temp=-5.0)
        vehicle = _make_vehicle(k_value=0.02)  # PREMIUM insulation
        shipment = _make_shipment(temp_limit_upper=5.0)

        # 500m detour => 0.5km / 30 km/h = 0.0167h
        # temp_rise = 0.0167 * (30 - (-5)) * 0.02 = 0.01167
        # budget = 5 - (-5) = 10
        # score = 0.01167 / 10 = 0.001167 => GREEN
        score = proxy.calculate_risk_score(route, vehicle, shipment, 1, 500)
        assert score < Decimal("0.5")
        assert TemperatureProxy.get_risk_level(score) == RiskLevel.GREEN

    def test_risk_score_yellow_zone(self):
        """Moderate detour with standard insulation should yield medium risk."""
        proxy = TemperatureProxy(ambient_temperature=35.0, average_speed_kmh=30.0)
        route = _make_route(initial_temp=2.0)
        vehicle = _make_vehicle(k_value=0.05)  # STANDARD
        shipment = _make_shipment(temp_limit_upper=5.0)

        # budget = 5 - 2 = 3 (tight)
        # Try 30km detour => 30/30 = 1h
        # temp_rise = 1 * (35 - 2) * 0.05 = 1.65
        # score = 1.65 / 3 = 0.55 => YELLOW
        score = proxy.calculate_risk_score(route, vehicle, shipment, 1, 30000)
        assert Decimal("0.5") <= score <= Decimal("0.8")
        assert TemperatureProxy.get_risk_level(score) == RiskLevel.YELLOW

    def test_risk_score_red_zone(self):
        """Large detour with poor insulation should yield high risk (>0.8)."""
        proxy = TemperatureProxy(ambient_temperature=40.0, average_speed_kmh=30.0)
        route = _make_route(initial_temp=3.0)
        vehicle = _make_vehicle(k_value=0.10)  # BASIC insulation
        shipment = _make_shipment(temp_limit_upper=5.0)

        # budget = 5 - 3 = 2 (very tight)
        # 30km detour => 1h
        # temp_rise = 1 * (40 - 3) * 0.10 = 3.7
        # score = 3.7 / 2 = 1.85 => RED
        score = proxy.calculate_risk_score(route, vehicle, shipment, 1, 30000)
        assert score > Decimal("0.8")
        assert TemperatureProxy.get_risk_level(score) == RiskLevel.RED

    def test_zero_budget_returns_high_score(self):
        """When temp is already at or above limit, score should be 1.5 (capped)."""
        proxy = TemperatureProxy(ambient_temperature=30.0, average_speed_kmh=30.0)
        route = _make_route(initial_temp=5.0)  # already at limit
        vehicle = _make_vehicle(k_value=0.05)
        shipment = _make_shipment(temp_limit_upper=5.0)

        score = proxy.calculate_risk_score(route, vehicle, shipment, 1, 5000)
        assert score == Decimal("1.5")
        assert TemperatureProxy.get_risk_level(score) == RiskLevel.RED

    def test_negative_budget_returns_high_score(self):
        """When temp exceeds limit already, score should be 1.5."""
        proxy = TemperatureProxy(ambient_temperature=30.0, average_speed_kmh=30.0)
        route = _make_route(initial_temp=8.0)  # above limit
        vehicle = _make_vehicle(k_value=0.05)
        shipment = _make_shipment(temp_limit_upper=5.0)

        score = proxy.calculate_risk_score(route, vehicle, shipment, 1, 5000)
        assert score == Decimal("1.5")

    def test_premium_vs_basic_insulation(self):
        """PREMIUM (0.02) should give lower risk than BASIC (0.10) for same detour."""
        proxy = TemperatureProxy(ambient_temperature=30.0, average_speed_kmh=30.0)
        route = _make_route(initial_temp=-5.0)
        shipment = _make_shipment(temp_limit_upper=5.0)

        premium_vehicle = _make_vehicle(k_value=0.02)
        basic_vehicle = _make_vehicle(k_value=0.10)

        score_premium = proxy.calculate_risk_score(route, premium_vehicle, shipment, 1, 10000)
        score_basic = proxy.calculate_risk_score(route, basic_vehicle, shipment, 1, 10000)

        assert score_premium < score_basic

    def test_with_strip_curtains_reduces_door_heat(self):
        """Vehicles with strip curtains should have lower temp at insertion point
        (less door heat gain at preceding stops) and thus more budget remaining."""
        proxy = TemperatureProxy(ambient_temperature=30.0, average_speed_kmh=30.0)
        shipment = _make_shipment(temp_limit_upper=5.0)

        # Route with 2 stops before the insertion point
        stops = [
            _make_stop(1, travel_time_from_prev=20, service_duration=15),
            _make_stop(2, travel_time_from_prev=20, service_duration=15),
        ]
        route = _make_route(initial_temp=-5.0, stops=stops)

        vehicle_no_curtains = _make_vehicle(has_strip_curtains=False)
        vehicle_with_curtains = _make_vehicle(has_strip_curtains=True)

        # Insert at position 3 (after both existing stops)
        score_no = proxy.calculate_risk_score(route, vehicle_no_curtains, shipment, 3, 5000)
        score_yes = proxy.calculate_risk_score(route, vehicle_with_curtains, shipment, 3, 5000)

        # With curtains, less door heat at preceding stops => lower current temp =>
        # more budget => lower risk score
        assert score_yes < score_no


# ─── Tests: Temperature Estimation ───────────────────────────────────────────

class TestEstimateTempAtPosition:
    def test_no_stops_returns_initial_temp(self):
        """With no preceding stops, estimated temp is the initial temperature."""
        proxy = TemperatureProxy(ambient_temperature=30.0, average_speed_kmh=30.0)
        route = _make_route(initial_temp=-5.0)
        vehicle = _make_vehicle()

        temp = proxy._estimate_current_temp_at_position(route, vehicle, position=1)
        assert temp == -5.0

    def test_accumulates_through_stops(self):
        """Temperature should accumulate transit + door heat through stops."""
        proxy = TemperatureProxy(ambient_temperature=30.0, average_speed_kmh=30.0)

        stop1 = _make_stop(1, travel_time_from_prev=60, service_duration=15)
        route = _make_route(initial_temp=-5.0, stops=[stop1])
        vehicle = _make_vehicle(k_value=0.05, door_coefficient=0.80, cooling_rate=-2.5)

        # Position 2 means we walk through stop 1
        temp = proxy._estimate_current_temp_at_position(route, vehicle, position=2)

        # Manual calculation:
        # travel_hours = 60/60 = 1.0
        # transit_rise = 1.0 * (30 - (-5)) * 0.05 = 1.75
        # cooling = 1.0 * (-2.5) = -2.5
        # after transit: -5 + 1.75 + (-2.5) = -5.75
        # service_hours = 15/60 = 0.25
        # door_rise = 0.25 * 0.80 * 1.0 = 0.2
        # final: -5.75 + 0.2 = -5.55
        assert abs(temp - (-5.55)) < 0.01

    def test_stops_beyond_position_ignored(self):
        """Stops at or beyond the insertion position should not be visited."""
        proxy = TemperatureProxy(ambient_temperature=30.0, average_speed_kmh=30.0)

        stop1 = _make_stop(1, travel_time_from_prev=60, service_duration=15)
        stop2 = _make_stop(2, travel_time_from_prev=30, service_duration=10)
        route = _make_route(initial_temp=-5.0, stops=[stop1, stop2])
        vehicle = _make_vehicle(k_value=0.05, door_coefficient=0.80, cooling_rate=-2.5)

        # Position 2: only stop 1 should be walked through
        temp_at_2 = proxy._estimate_current_temp_at_position(route, vehicle, position=2)
        # Same as test_accumulates_through_stops above
        assert abs(temp_at_2 - (-5.55)) < 0.01
