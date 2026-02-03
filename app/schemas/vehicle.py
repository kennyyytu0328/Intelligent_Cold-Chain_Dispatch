"""
Vehicle Pydantic schemas with thermodynamic parameters.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.models.enums import InsulationGrade, DoorType, VehicleStatus
from app.schemas.base import BaseSchema, GeoLocation


class VehicleThermoParams(BaseSchema):
    """
    Thermodynamic parameters for vehicle.

    These parameters are used in temperature calculations:
    - ΔT_drive = Time_travel × (T_ambient - T_current) × K_insulation
    - ΔT_door = Time_service × C_door_type × (1 - 0.5 × IsCurtain)
    - ΔT_cooling = Time_drive × Rate_cooling
    """
    insulation_grade: InsulationGrade = InsulationGrade.STANDARD
    door_type: DoorType = DoorType.ROLL
    has_strip_curtains: bool = False
    cooling_rate: Decimal = Field(
        default=Decimal("-2.5"),
        description="Cooling rate in °C/min (negative = cooling)",
    )
    min_temp_capability: Decimal = Field(
        default=Decimal("-25.0"),
        description="Minimum achievable temperature in °C",
    )

    @property
    def k_value(self) -> Decimal:
        """Get heat transfer coefficient from insulation grade."""
        return Decimal(str(self.insulation_grade.k_value))

    @property
    def door_coefficient(self) -> Decimal:
        """Get door coefficient from door type."""
        return Decimal(str(self.door_type.coefficient))

    @property
    def curtain_factor(self) -> float:
        """Get curtain factor (0.5 if has curtains, 1.0 otherwise)."""
        return 0.5 if self.has_strip_curtains else 1.0


class VehicleDimensions(BaseSchema):
    """Internal dimensions for 3D bin packing."""
    length: Optional[Decimal] = Field(None, gt=0, description="Length in meters")
    width: Optional[Decimal] = Field(None, gt=0, description="Width in meters")
    height: Optional[Decimal] = Field(None, gt=0, description="Height in meters")


class VehicleBase(BaseSchema):
    """Base vehicle schema."""
    license_plate: str = Field(..., min_length=1, max_length=20)
    capacity_weight: Decimal = Field(..., gt=0, description="Max weight in kg")
    capacity_volume: Decimal = Field(..., gt=0, description="Max volume in m³")


class VehicleCreate(VehicleBase):
    """Schema for creating a new vehicle."""
    driver_id: Optional[UUID] = None
    driver_name: Optional[str] = None

    # Dimensions
    internal_length: Optional[Decimal] = Field(None, gt=0)
    internal_width: Optional[Decimal] = Field(None, gt=0)
    internal_height: Optional[Decimal] = Field(None, gt=0)

    # Thermodynamic parameters
    insulation_grade: InsulationGrade = InsulationGrade.STANDARD
    door_type: DoorType = DoorType.ROLL
    has_strip_curtains: bool = False
    cooling_rate: Decimal = Field(default=Decimal("-2.5"))
    min_temp_capability: Decimal = Field(default=Decimal("-25.0"))

    @model_validator(mode="after")
    def set_derived_values(self) -> "VehicleCreate":
        """Automatically set k_value and door_coefficient based on grades."""
        return self


class VehicleUpdate(BaseSchema):
    """Schema for updating a vehicle (all fields optional)."""
    license_plate: Optional[str] = Field(None, min_length=1, max_length=20)
    driver_id: Optional[UUID] = None
    driver_name: Optional[str] = None
    capacity_weight: Optional[Decimal] = Field(None, gt=0)
    capacity_volume: Optional[Decimal] = Field(None, gt=0)

    # Dimensions
    internal_length: Optional[Decimal] = Field(None, gt=0)
    internal_width: Optional[Decimal] = Field(None, gt=0)
    internal_height: Optional[Decimal] = Field(None, gt=0)

    # Thermodynamic parameters
    insulation_grade: Optional[InsulationGrade] = None
    door_type: Optional[DoorType] = None
    has_strip_curtains: Optional[bool] = None
    cooling_rate: Optional[Decimal] = None
    min_temp_capability: Optional[Decimal] = None

    # Status
    status: Optional[VehicleStatus] = None


class VehicleResponse(VehicleBase):
    """Schema for vehicle response."""
    id: UUID
    driver_id: Optional[UUID]
    driver_name: Optional[str]

    # Dimensions
    internal_length: Optional[Decimal]
    internal_width: Optional[Decimal]
    internal_height: Optional[Decimal]

    # Thermodynamic parameters
    insulation_grade: InsulationGrade
    k_value: Decimal
    door_type: DoorType
    door_coefficient: Decimal
    has_strip_curtains: bool
    cooling_rate: Decimal
    min_temp_capability: Decimal

    # Status
    status: VehicleStatus
    current_temperature: Optional[Decimal]
    last_telemetry_at: Optional[datetime]

    # Timestamps
    created_at: datetime
    updated_at: datetime

    @property
    def thermo_params(self) -> VehicleThermoParams:
        """Get thermodynamic parameters as a separate object."""
        return VehicleThermoParams(
            insulation_grade=self.insulation_grade,
            door_type=self.door_type,
            has_strip_curtains=self.has_strip_curtains,
            cooling_rate=self.cooling_rate,
            min_temp_capability=self.min_temp_capability,
        )


class VehicleListResponse(BaseSchema):
    """Schema for list of vehicles."""
    items: list[VehicleResponse]
    total: int


class VehicleLocationUpdate(BaseSchema):
    """Schema for updating vehicle location from IoT."""
    location: GeoLocation
    temperature: Optional[Decimal] = None
    is_cooling_active: Optional[bool] = None
    ambient_temperature: Optional[Decimal] = None
