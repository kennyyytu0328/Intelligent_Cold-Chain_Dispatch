"""
Temperature proxy model for dynamic insertion risk scoring.

Provides a fast, lightweight temperature risk assessment for evaluating
whether inserting a new shipment into an active route is thermally safe.
Uses the same thermodynamic formulas as the full solver but operates on
ORM Route/Vehicle/Shipment objects rather than VRPDataModel.
"""
from decimal import Decimal
from enum import Enum

from app.core.config import get_settings
from app.models.route import Route, RouteStop
from app.models.shipment import Shipment
from app.models.vehicle import Vehicle


class RiskLevel(str, Enum):
    """Temperature risk classification for insertion decisions."""
    GREEN = "GREEN"    # < 0.5: safe to insert
    YELLOW = "YELLOW"  # 0.5 - 0.8: warn, allow with confirmation
    RED = "RED"        # > 0.8: reject, recommend full re-optimization


class TemperatureProxy:
    """
    Lightweight temperature risk scorer for dynamic insertion.

    Estimates the thermal impact of inserting a new shipment into an
    existing route by calculating how much of the remaining temperature
    budget would be consumed by the detour.

    Risk formula:
        TempRiskScore = (ExtraDistance_km / AverageSpeed_kmh)
                        * (T_ambient - T_current_estimate)
                        * K_value
                        / delta_T_budget

    Where delta_T_budget = shipment.temp_limit_upper - T_current_estimate.
    """

    def __init__(
        self,
        ambient_temperature: float | None = None,
        average_speed_kmh: float | None = None,
    ):
        settings = get_settings()
        self._ambient = (
            ambient_temperature
            if ambient_temperature is not None
            else float(settings.default_ambient_temperature)
        )
        self._speed_kmh = (
            average_speed_kmh
            if average_speed_kmh is not None
            else float(settings.average_speed_kmh)
        )

    def calculate_risk_score(
        self,
        route: Route,
        vehicle: Vehicle,
        shipment: Shipment,
        insertion_position: int,
        extra_distance_meters: float,
    ) -> Decimal:
        """
        Calculate the temperature risk score for inserting a shipment.

        Args:
            route: The active route to insert into.
            vehicle: The vehicle assigned to the route.
            shipment: The new shipment to insert.
            insertion_position: 1-based stop position where the shipment
                would be inserted (e.g. 3 means between current stops 2 and 3).
            extra_distance_meters: Additional detour distance in meters
                caused by the insertion.

        Returns:
            Risk score as Decimal. Lower is safer.
            Values > 1.0 indicate the insertion would likely cause
            a temperature violation.
        """
        extra_distance_km = extra_distance_meters / 1000.0

        current_temp = self._estimate_current_temp_at_position(
            route, vehicle, insertion_position
        )

        temp_limit = float(shipment.temp_limit_upper)
        delta_t_budget = temp_limit - current_temp

        if delta_t_budget <= 0:
            return Decimal("1.5")

        k_value = float(vehicle.k_value)
        extra_hours = extra_distance_km / self._speed_kmh

        temp_rise_from_detour = (
            extra_hours * (self._ambient - current_temp) * k_value
        )

        score = temp_rise_from_detour / delta_t_budget

        return Decimal(str(round(score, 4)))

    @staticmethod
    def get_risk_level(score: Decimal) -> RiskLevel:
        """
        Classify a risk score into GREEN / YELLOW / RED.

        Args:
            score: Temperature risk score from calculate_risk_score().

        Returns:
            RiskLevel enum value.
        """
        if score < Decimal("0.5"):
            return RiskLevel.GREEN
        if score <= Decimal("0.8"):
            return RiskLevel.YELLOW
        return RiskLevel.RED

    def _estimate_current_temp_at_position(
        self,
        route: Route,
        vehicle: Vehicle,
        position: int,
    ) -> float:
        """
        Walk through route stops up to the insertion point, accumulating
        temperature changes to estimate current compartment temperature.

        RouteStop stores travel_time and service_duration in MINUTES,
        but thermodynamic formulas require HOURS, so we convert accordingly.

        Args:
            route: Route with loaded stops relationship.
            vehicle: Vehicle with thermodynamic properties.
            position: 1-based insertion position.

        Returns:
            Estimated compartment temperature at the insertion point.
        """
        current_temp = float(route.initial_temperature)
        ordered_stops = route.get_stops_ordered()

        for stop in ordered_stops:
            if stop.sequence_number >= position:
                break

            travel_minutes = float(stop.travel_time_from_prev or 0)
            travel_hours = travel_minutes / 60.0

            transit_rise = (
                travel_hours
                * (self._ambient - current_temp)
                * float(vehicle.k_value)
            )

            cooling_effect = travel_hours * float(vehicle.cooling_rate)

            current_temp += transit_rise + cooling_effect

            service_minutes = float(stop.shipment.service_duration if stop.shipment else 0)
            service_hours = service_minutes / 60.0

            door_rise = (
                service_hours
                * float(vehicle.door_coefficient)
                * (1.0 - 0.5 * (1.0 if vehicle.has_strip_curtains else 0.0))
            )

            current_temp += door_rise

        # One more transit leg: from the last visited stop to the insertion point.
        # We don't know exact travel time for this partial leg, so we skip it.
        # The risk score formula already accounts for the extra detour distance.

        return current_temp
