"""
Route and RouteStop models for ICCDDS.

Stores optimized delivery routes with temperature predictions at each stop.
"""
from datetime import datetime, date
from decimal import Decimal
from typing import TYPE_CHECKING, Optional, Any
from uuid import UUID

from geoalchemy2 import Geometry
from sqlalchemy import String, Text, Integer, Boolean, Numeric, Enum, ForeignKey, DateTime, Date, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel
from app.models.enums import RouteStatus, DeliveryStatus

if TYPE_CHECKING:
    from app.models.vehicle import Vehicle
    from app.models.driver import Driver
    from app.models.shipment import Shipment
    from app.models.telemetry import TemperatureLog


class Route(BaseModel):
    """
    Optimized delivery route with temperature predictions.

    Stores the complete route plan including:
    - Vehicle and driver assignment
    - Total metrics (distance, duration, weight, volume)
    - Temperature predictions (initial, final, max)
    - Timing information
    """
    __tablename__ = "routes"

    # =========================================================================
    # Route Identification
    # =========================================================================
    route_code: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
    )

    plan_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )

    # =========================================================================
    # Optimistic Locking & Smart Assignment (v3.1)
    # =========================================================================
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
        comment="Optimistic locking version counter",
    )

    route_signature: Mapped[Optional[list]] = mapped_column(
        JSON,
        nullable=True,
        default=list,
        server_default="[]",
        comment="H3 cell indices representing route footprint",
    )

    actual_success_score: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(4, 3),
        nullable=True,
        comment="Actual delivery success rate (0.000–1.000)",
    )

    # =========================================================================
    # Vehicle & Driver Assignment
    # =========================================================================
    vehicle_id: Mapped[UUID] = mapped_column(
        ForeignKey("vehicles.id"),
        nullable=False,
    )

    driver_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("drivers.id"),
        nullable=True,
    )

    # Snapshot at planning time (denormalized)
    driver_name: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )

    # =========================================================================
    # Route Status
    # =========================================================================
    status: Mapped[RouteStatus] = mapped_column(
        Enum(RouteStatus, name="route_status", create_type=False),
        nullable=False,
        default=RouteStatus.PLANNING,
    )

    # =========================================================================
    # Optimization Results (Summary)
    # =========================================================================
    total_stops: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    total_distance: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2),
        nullable=True,
        comment="Total route distance in km",
    )

    total_duration: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Total estimated duration in minutes",
    )

    total_weight: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2),
        nullable=True,
        comment="Total cargo weight in kg",
    )

    total_volume: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2),
        nullable=True,
        comment="Total cargo volume in m³",
    )

    # =========================================================================
    # Temperature Predictions
    # =========================================================================
    initial_temperature: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        comment="Starting compartment temperature (°C)",
    )

    predicted_final_temp: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2),
        nullable=True,
        comment="Predicted temperature after all stops (°C)",
    )

    predicted_max_temp: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2),
        nullable=True,
        comment="Highest predicted temperature during route (°C)",
    )

    # =========================================================================
    # Timing
    # =========================================================================
    planned_departure_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    planned_return_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    actual_departure_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    actual_return_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # =========================================================================
    # Depot Information
    # =========================================================================
    depot_address: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    depot_location: Mapped[Optional[str]] = mapped_column(
        Geometry("POINT", srid=4326),
        nullable=True,
    )

    # =========================================================================
    # Optimization Metadata
    # =========================================================================
    optimization_job_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("optimization_jobs.id"),
        nullable=True,
    )

    optimization_cost: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(15, 4),
        nullable=True,
        comment="Optimization objective function value",
    )

    algorithm_version: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
    )

    # =========================================================================
    # Relationships
    # =========================================================================
    vehicle: Mapped["Vehicle"] = relationship(
        "Vehicle",
        back_populates="routes",
        lazy="joined",
    )

    driver: Mapped[Optional["Driver"]] = relationship(
        "Driver",
        back_populates="routes",
        lazy="joined",
    )

    shipments: Mapped[list["Shipment"]] = relationship(
        "Shipment",
        back_populates="route",
        lazy="selectin",
    )

    stops: Mapped[list["RouteStop"]] = relationship(
        "RouteStop",
        back_populates="route",
        order_by="RouteStop.sequence_number",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    temperature_logs: Mapped[list["TemperatureLog"]] = relationship(
        "TemperatureLog",
        back_populates="route",
        lazy="selectin",
    )

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def get_stops_ordered(self) -> list["RouteStop"]:
        """Get stops in sequence order."""
        return sorted(self.stops, key=lambda s: s.sequence_number)

    def get_max_predicted_temp(self) -> Optional[Decimal]:
        """Calculate maximum predicted temperature across all stops."""
        if not self.stops:
            return None
        temps = [s.predicted_arrival_temp for s in self.stops if s.predicted_arrival_temp]
        return max(temps) if temps else None

    def is_temperature_feasible(self) -> bool:
        """Check if all stops have feasible temperature predictions."""
        return all(stop.is_temp_feasible for stop in self.stops)

    def __repr__(self) -> str:
        return (
            f"<Route(id={self.id}, code={self.route_code!r}, "
            f"stops={self.total_stops}, status={self.status.value})>"
        )


class RouteStop(BaseModel):
    """
    Individual stop in a route with predicted and actual temperature data.

    This is where the thermodynamic predictions are stored for each delivery:
    - transit_temp_rise: ΔT_drive during travel to this stop
    - service_temp_rise: ΔT_door during service at this stop
    - cooling_applied: ΔT_cooling from refrigeration
    - predicted_arrival_temp: Critical constraint check point
    """
    __tablename__ = "route_stops"

    __table_args__ = (
        UniqueConstraint("route_id", "sequence_number", name="uq_route_stop_sequence"),
    )

    # =========================================================================
    # Parent Route
    # =========================================================================
    route_id: Mapped[UUID] = mapped_column(
        ForeignKey("routes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Associated Shipment
    shipment_id: Mapped[UUID] = mapped_column(
        ForeignKey("shipments.id"),
        nullable=False,
        index=True,
    )

    # =========================================================================
    # Sequence & Location
    # =========================================================================
    sequence_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Stop sequence (1-based)",
    )

    location: Mapped[str] = mapped_column(
        Geometry("POINT", srid=4326),
        nullable=False,
    )

    address: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # =========================================================================
    # Timing Predictions
    # =========================================================================
    expected_arrival_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    expected_departure_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    # Index into shipment.time_windows array (0-based)
    target_time_window_index: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Which time window this stop is targeting",
    )

    # Buffer time before window closes
    slack_minutes: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Minutes of slack before time window closes",
    )

    # =========================================================================
    # THERMODYNAMIC PREDICTIONS (Critical!)
    # =========================================================================

    # Predicted temperature UPON ARRIVAL at this stop
    # This is the key constraint check point: must be <= shipment.temp_limit_upper
    predicted_arrival_temp: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        comment="Predicted temperature upon arrival (°C) - critical constraint",
    )

    # Temperature rise during transit to this stop
    # ΔT_drive = Time_travel × (T_ambient - T_current) × K_insulation
    transit_temp_rise: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2),
        nullable=True,
        comment="ΔT_drive: temperature rise during transit (°C)",
    )

    # Temperature rise during service at this stop
    # ΔT_door = Time_service × C_door_type × (1 - 0.5 × IsCurtain)
    service_temp_rise: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2),
        nullable=True,
        comment="ΔT_door: temperature rise during service (°C)",
    )

    # Cooling applied during transit
    # ΔT_cooling = Time_drive × Rate_cooling
    cooling_applied: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2),
        nullable=True,
        comment="ΔT_cooling: cooling effect during transit (°C, negative)",
    )

    # Predicted temperature AFTER service (departure temp)
    predicted_departure_temp: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2),
        nullable=True,
        comment="Predicted temperature after service (°C)",
    )

    # Is this stop's predicted temp within limit?
    is_temp_feasible: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="True if predicted_arrival_temp <= temp_limit",
    )

    # =========================================================================
    # Travel Metrics (to this stop from previous)
    # =========================================================================
    distance_from_prev: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2),
        nullable=True,
        comment="Distance from previous stop in km",
    )

    travel_time_from_prev: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Travel time from previous stop in minutes",
    )

    # =========================================================================
    # Actual Results (filled during execution)
    # =========================================================================
    actual_arrival_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    actual_temperature: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2),
        nullable=True,
        comment="Actual recorded temperature (°C)",
    )

    delivery_status: Mapped[Optional[DeliveryStatus]] = mapped_column(
        Enum(DeliveryStatus, name="delivery_status", create_type=False),
        nullable=True,
    )

    notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    # =========================================================================
    # Relationships
    # =========================================================================
    route: Mapped["Route"] = relationship(
        "Route",
        back_populates="stops",
        lazy="joined",
    )

    shipment: Mapped["Shipment"] = relationship(
        "Shipment",
        back_populates="route_stop",
        lazy="joined",
    )

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def calculate_net_temp_change(self) -> Decimal:
        """
        Calculate net temperature change at this stop.

        Net = transit_rise + service_rise + cooling (cooling is negative)
        """
        transit = self.transit_temp_rise or Decimal("0")
        service = self.service_temp_rise or Decimal("0")
        cooling = self.cooling_applied or Decimal("0")
        return transit + service + cooling

    def check_temperature_compliance(self, temp_limit: Decimal) -> bool:
        """
        Check if predicted arrival temperature is compliant.

        Args:
            temp_limit: Maximum allowed temperature

        Returns:
            True if compliant
        """
        return self.predicted_arrival_temp <= temp_limit

    def __repr__(self) -> str:
        return (
            f"<RouteStop(route={self.route_id}, seq={self.sequence_number}, "
            f"arrival_temp={self.predicted_arrival_temp}°C, feasible={self.is_temp_feasible})>"
        )
