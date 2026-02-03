"""
Shipment Pydantic schemas with time window validation.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional, Any
from uuid import UUID
import re

from pydantic import Field, field_validator, model_validator

from app.models.enums import SLATier, ShipmentStatus
from app.schemas.base import BaseSchema, GeoLocation


class TimeWindowSchema(BaseSchema):
    """
    Schema for a delivery time window.

    Time format: "HH:MM" (24-hour format)
    Example: {"start": "08:00", "end": "10:00"}
    """
    start: str = Field(..., pattern=r"^\d{2}:\d{2}$", description="Start time (HH:MM)")
    end: str = Field(..., pattern=r"^\d{2}:\d{2}$", description="End time (HH:MM)")

    @field_validator("start", "end")
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        """Validate time is in HH:MM format and valid."""
        if not re.match(r"^\d{2}:\d{2}$", v):
            raise ValueError("Time must be in HH:MM format")
        hours, minutes = map(int, v.split(":"))
        if not (0 <= hours <= 23 and 0 <= minutes <= 59):
            raise ValueError("Invalid time value")
        return v

    @model_validator(mode="after")
    def validate_window(self) -> "TimeWindowSchema":
        """Ensure start is before end."""
        start_mins = int(self.start.split(":")[0]) * 60 + int(self.start.split(":")[1])
        end_mins = int(self.end.split(":")[0]) * 60 + int(self.end.split(":")[1])
        if start_mins >= end_mins:
            raise ValueError("Start time must be before end time")
        return self


class DimensionsSchema(BaseSchema):
    """Cargo dimensions for 3D bin packing (in centimeters)."""
    l: int = Field(..., gt=0, description="Length in cm")
    w: int = Field(..., gt=0, description="Width in cm")
    h: int = Field(..., gt=0, description="Height in cm")

    @property
    def volume_cm3(self) -> int:
        """Calculate volume in cubic centimeters."""
        return self.l * self.w * self.h

    @property
    def volume_m3(self) -> float:
        """Calculate volume in cubic meters."""
        return self.volume_cm3 / 1_000_000


class ShipmentBase(BaseSchema):
    """Base shipment schema."""
    delivery_address: str = Field(..., min_length=1)
    latitude: Decimal = Field(..., ge=-90, le=90)
    longitude: Decimal = Field(..., ge=-180, le=180)
    weight: Decimal = Field(..., gt=0, description="Weight in kg")


class ShipmentCreate(ShipmentBase):
    """Schema for creating a new shipment."""
    order_number: str = Field(..., min_length=1, max_length=50)
    customer_id: Optional[UUID] = None

    # Time windows (at least one required)
    time_windows: list[TimeWindowSchema] = Field(
        ...,
        min_length=1,
        max_length=10,
        description="Valid delivery time windows (OR relationship)",
    )

    # SLA & Temperature
    sla_tier: SLATier = SLATier.STANDARD
    temp_limit_upper: Decimal = Field(
        default=Decimal("5.0"),
        description="Max acceptable temperature (°C)",
    )
    temp_limit_lower: Optional[Decimal] = Field(
        None,
        description="Min acceptable temperature (°C)",
    )

    # Service parameters
    service_duration: int = Field(
        default=15,
        ge=1,
        le=120,
        description="Unloading time in minutes",
    )

    # Cargo specifications
    volume: Optional[Decimal] = Field(None, gt=0, description="Volume in m³")
    dimensions: Optional[DimensionsSchema] = None
    package_count: int = Field(default=1, ge=1)

    # Metadata
    priority: int = Field(default=0, ge=0, le=100)
    special_instructions: Optional[str] = None

    @field_validator("time_windows")
    @classmethod
    def validate_time_windows_overlap(
        cls, v: list[TimeWindowSchema]
    ) -> list[TimeWindowSchema]:
        """Warn if time windows overlap (not an error, just unusual)."""
        # Sort by start time for easier checking
        sorted_windows = sorted(v, key=lambda tw: tw.start)
        # Could add overlap detection here if needed
        return v

    @model_validator(mode="after")
    def validate_temp_limits(self) -> "ShipmentCreate":
        """Ensure temp_limit_lower < temp_limit_upper if both specified."""
        if self.temp_limit_lower is not None:
            if self.temp_limit_lower >= self.temp_limit_upper:
                raise ValueError(
                    "temp_limit_lower must be less than temp_limit_upper"
                )
        return self


class ShipmentUpdate(BaseSchema):
    """Schema for updating a shipment (all fields optional)."""
    delivery_address: Optional[str] = Field(None, min_length=1)
    latitude: Optional[Decimal] = Field(None, ge=-90, le=90)
    longitude: Optional[Decimal] = Field(None, ge=-180, le=180)

    time_windows: Optional[list[TimeWindowSchema]] = Field(None, min_length=1)

    sla_tier: Optional[SLATier] = None
    temp_limit_upper: Optional[Decimal] = None
    temp_limit_lower: Optional[Decimal] = None

    service_duration: Optional[int] = Field(None, ge=1, le=120)

    weight: Optional[Decimal] = Field(None, gt=0)
    volume: Optional[Decimal] = Field(None, gt=0)
    dimensions: Optional[DimensionsSchema] = None
    package_count: Optional[int] = Field(None, ge=1)

    priority: Optional[int] = Field(None, ge=0, le=100)
    special_instructions: Optional[str] = None
    status: Optional[ShipmentStatus] = None


class ShipmentResponse(ShipmentBase):
    """Schema for shipment response."""
    id: UUID
    order_number: str
    customer_id: Optional[UUID]

    # Location (geo_location is handled separately)
    geo_location: Optional[Any] = Field(None, exclude=True)  # Exclude raw geometry

    # Time windows
    time_windows: list[TimeWindowSchema]

    # SLA & Temperature
    sla_tier: SLATier
    temp_limit_upper: Decimal
    temp_limit_lower: Optional[Decimal]

    # Service parameters
    service_duration: int

    # Cargo specifications
    volume: Optional[Decimal]
    dimensions: Optional[dict[str, Any]]
    package_count: int

    # Status & Assignment
    status: ShipmentStatus
    route_id: Optional[UUID]
    route_sequence: Optional[int]

    # Delivery results
    actual_arrival_at: Optional[datetime]
    actual_temperature: Optional[Decimal]
    was_on_time: Optional[bool]
    was_temp_compliant: Optional[bool]

    # Metadata
    priority: int
    special_instructions: Optional[str]

    # Timestamps
    created_at: datetime
    updated_at: datetime

    @property
    def location(self) -> GeoLocation:
        """Get location as GeoLocation object."""
        return GeoLocation(
            latitude=float(self.latitude),
            longitude=float(self.longitude),
        )

    @property
    def is_strict_sla(self) -> bool:
        """Check if shipment has strict SLA."""
        return self.sla_tier == SLATier.STRICT


class ShipmentListResponse(BaseSchema):
    """Schema for list of shipments."""
    items: list[ShipmentResponse]
    total: int


class ShipmentBatchCreate(BaseSchema):
    """Schema for batch creation of shipments."""
    shipments: list[ShipmentCreate] = Field(..., min_length=1, max_length=1000)
