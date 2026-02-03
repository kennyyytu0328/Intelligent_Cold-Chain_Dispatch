"""
Vehicle model for ICCDDS.

This is not just a transport unit, but a mobile warehouse with specific
thermodynamic properties that affect temperature during transit.
"""
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from geoalchemy2 import Geometry
from sqlalchemy import String, Boolean, Numeric, Enum, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel
from app.models.enums import InsulationGrade, DoorType, VehicleStatus

if TYPE_CHECKING:
    from app.models.driver import Driver
    from app.models.route import Route
    from app.models.telemetry import TemperatureLog


class Vehicle(BaseModel):
    """
    Vehicle fleet with thermodynamic properties for cold-chain optimization.

    This model captures all physical characteristics that affect temperature
    during transport, enabling accurate thermodynamic simulation.

    Thermodynamic Properties:
    -------------------------
    - insulation_grade / k_value: Heat transfer coefficient
      Used in: ΔT_drive = Time_travel × (T_ambient - T_current) × K_insulation

    - door_type / door_coefficient: Heat loss during door-open operations
      Used in: ΔT_door = Time_service × C_door_type × (1 - 0.5 × IsCurtain)

    - has_strip_curtains: If True, reduces door heat loss by 50%

    - cooling_rate: Active refrigeration cooling rate (°C/min)
      Used in: ΔT_cooling = Time_drive × Rate_cooling
    """
    __tablename__ = "vehicles"

    # =========================================================================
    # Basic Identification
    # =========================================================================
    license_plate: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        nullable=False,
        index=True,
    )

    # Driver Assignment (current shift driver)
    driver_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("drivers.id"),
        nullable=True,
    )

    # Denormalized for display (avoid frequent JOINs)
    driver_name: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )

    # =========================================================================
    # Capacity Constraints
    # =========================================================================
    capacity_weight: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        comment="Maximum weight capacity in kg",
    )

    capacity_volume: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        comment="Maximum volume capacity in m³",
    )

    # Internal Dimensions (for 3D Bin Packing simulation)
    internal_length: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(6, 2),
        nullable=True,
        comment="Internal length in meters",
    )

    internal_width: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(6, 2),
        nullable=True,
        comment="Internal width in meters",
    )

    internal_height: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(6, 2),
        nullable=True,
        comment="Internal height in meters",
    )

    # =========================================================================
    # THERMODYNAMIC PROPERTIES (Critical for cold-chain)
    # =========================================================================

    # Insulation grade affects K-value (heat transfer coefficient)
    insulation_grade: Mapped[InsulationGrade] = mapped_column(
        Enum(InsulationGrade, name="insulation_grade", create_type=False),
        nullable=False,
        default=InsulationGrade.STANDARD,
        comment="Insulation quality grade",
    )

    # K-value mapping (derived from insulation_grade, stored for efficiency)
    # PREMIUM=0.02, STANDARD=0.05, BASIC=0.10
    k_value: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
        default=Decimal("0.05"),
        comment="Heat transfer coefficient (derived from insulation_grade)",
    )

    # Door type affects C_door_type coefficient
    door_type: Mapped[DoorType] = mapped_column(
        Enum(DoorType, name="door_type", create_type=False),
        nullable=False,
        default=DoorType.ROLL,
        comment="Door mechanism type",
    )

    # Door coefficient (derived from door_type)
    # ROLL=0.8, SWING=1.2
    door_coefficient: Mapped[Decimal] = mapped_column(
        Numeric(4, 2),
        nullable=False,
        default=Decimal("0.8"),
        comment="Door heat loss coefficient (derived from door_type)",
    )

    # Strip curtains reduce heat loss by 50% during door-open operations
    has_strip_curtains: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="If True, door heat loss is reduced by 50%",
    )

    # Cooling rate: refrigeration unit cooling speed
    # Typical value: -2.0 to -5.0 (negative means cooling)
    cooling_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        default=Decimal("-2.5"),
        comment="Temperature change per minute when refrigeration active (°C/min)",
    )

    # Minimum achievable temperature
    min_temp_capability: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        default=Decimal("-25.0"),
        comment="Minimum achievable compartment temperature (°C)",
    )

    # =========================================================================
    # Status & Real-time Tracking
    # =========================================================================
    status: Mapped[VehicleStatus] = mapped_column(
        Enum(VehicleStatus, name="vehicle_status", create_type=False),
        nullable=False,
        default=VehicleStatus.AVAILABLE,
    )

    # Current location (real-time GPS update from IoT)
    # PostGIS POINT with SRID 4326 (WGS84)
    current_location: Mapped[Optional[str]] = mapped_column(
        Geometry("POINT", srid=4326),
        nullable=True,
    )

    # Current compartment temperature (real-time IoT update)
    current_temperature: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2),
        nullable=True,
        comment="Current compartment temperature from IoT sensor (°C)",
    )

    # Last IoT data timestamp
    last_telemetry_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # =========================================================================
    # Relationships
    # =========================================================================
    driver: Mapped[Optional["Driver"]] = relationship(
        "Driver",
        back_populates="vehicles",
        lazy="joined",
    )

    routes: Mapped[list["Route"]] = relationship(
        "Route",
        back_populates="vehicle",
        lazy="selectin",
    )

    temperature_logs: Mapped[list["TemperatureLog"]] = relationship(
        "TemperatureLog",
        back_populates="vehicle",
        lazy="selectin",
    )

    # =========================================================================
    # Thermodynamic Calculation Methods
    # =========================================================================

    def calculate_transit_temp_rise(
        self,
        travel_time_minutes: float,
        ambient_temp: float,
        current_temp: float,
    ) -> float:
        """
        Calculate temperature rise during transit.

        Formula: ΔT_drive = Time_travel × (T_ambient - T_current) × K_insulation

        Args:
            travel_time_minutes: Travel duration in minutes
            ambient_temp: Outside ambient temperature (°C)
            current_temp: Current compartment temperature (°C)

        Returns:
            Temperature rise in °C (positive value means warming)
        """
        k = float(self.k_value)
        delta_t = travel_time_minutes * (ambient_temp - current_temp) * k
        return delta_t

    def calculate_door_temp_rise(
        self,
        service_time_minutes: float,
    ) -> float:
        """
        Calculate temperature rise during door-open operations.

        Formula: ΔT_door = Time_service × C_door_type × (1 - 0.5 × IsCurtain)

        The strip curtain factor reduces heat loss by 50% when present.

        Args:
            service_time_minutes: Duration of door-open service (minutes)

        Returns:
            Temperature rise in °C (positive value)
        """
        c_door = float(self.door_coefficient)
        curtain_factor = 0.5 if self.has_strip_curtains else 1.0
        delta_t = service_time_minutes * c_door * curtain_factor
        return delta_t

    def calculate_cooling_effect(
        self,
        cooling_time_minutes: float,
    ) -> float:
        """
        Calculate temperature reduction from active refrigeration.

        Formula: ΔT_cooling = Time_drive × Rate_cooling

        Args:
            cooling_time_minutes: Duration of active cooling (minutes)

        Returns:
            Temperature change in °C (negative value means cooling)
        """
        rate = float(self.cooling_rate)
        delta_t = cooling_time_minutes * rate
        return delta_t

    def predict_temperature_at_stop(
        self,
        initial_temp: float,
        travel_time_minutes: float,
        service_time_minutes: float,
        ambient_temp: float,
        cooling_active: bool = True,
    ) -> dict[str, float]:
        """
        Predict temperatures for a delivery stop.

        Args:
            initial_temp: Starting temperature (°C)
            travel_time_minutes: Travel time to stop (minutes)
            service_time_minutes: Service duration at stop (minutes)
            ambient_temp: Outside ambient temperature (°C)
            cooling_active: Whether refrigeration is running during transit

        Returns:
            Dictionary with:
            - transit_rise: Temperature rise during transit
            - door_rise: Temperature rise during service
            - cooling_effect: Cooling applied (negative)
            - arrival_temp: Predicted temperature upon arrival
            - departure_temp: Predicted temperature after service
        """
        # Transit phase
        transit_rise = self.calculate_transit_temp_rise(
            travel_time_minutes, ambient_temp, initial_temp
        )

        # Cooling during transit (if active)
        cooling_effect = 0.0
        if cooling_active:
            cooling_effect = self.calculate_cooling_effect(travel_time_minutes)

        # Arrival temperature
        arrival_temp = initial_temp + transit_rise + cooling_effect

        # Service phase (door open)
        door_rise = self.calculate_door_temp_rise(service_time_minutes)

        # Departure temperature
        departure_temp = arrival_temp + door_rise

        return {
            "transit_rise": transit_rise,
            "door_rise": door_rise,
            "cooling_effect": cooling_effect,
            "arrival_temp": arrival_temp,
            "departure_temp": departure_temp,
        }

    @property
    def internal_volume(self) -> Optional[Decimal]:
        """Calculate internal volume from dimensions."""
        if all([self.internal_length, self.internal_width, self.internal_height]):
            return self.internal_length * self.internal_width * self.internal_height
        return None

    def __repr__(self) -> str:
        return (
            f"<Vehicle(id={self.id}, plate={self.license_plate!r}, "
            f"insulation={self.insulation_grade.value}, "
            f"curtains={self.has_strip_curtains})>"
        )
