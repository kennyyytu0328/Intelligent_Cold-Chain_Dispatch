"""
Depot Pydantic schemas for warehouse/depot location management.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import Field, field_validator

from app.schemas.base import BaseSchema


class DepotBase(BaseSchema):
    """Base depot schema with common fields."""
    name: str = Field(..., min_length=1, max_length=100, description="Depot name")
    code: Optional[str] = Field(None, max_length=50, description="Optional depot code")
    address: Optional[str] = Field(None, description="Full street address")
    latitude: Decimal = Field(..., ge=-90, le=90, description="Latitude in decimal degrees")
    longitude: Decimal = Field(..., ge=-180, le=180, description="Longitude in decimal degrees")
    is_active: bool = Field(default=True, description="Whether depot is active")
    contact_person: Optional[str] = Field(None, max_length=100)
    contact_phone: Optional[str] = Field(None, max_length=20)

    @field_validator("latitude", "longitude")
    @classmethod
    def validate_coordinates(cls, v: Decimal) -> Decimal:
        """Validate coordinate precision (max 8 decimal places)."""
        if v is not None:
            # Round to 8 decimal places for consistency
            return Decimal(str(round(float(v), 8)))
        return v


class DepotCreate(DepotBase):
    """Schema for creating a new depot."""
    pass


class DepotUpdate(BaseSchema):
    """Schema for updating a depot (all fields optional)."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    code: Optional[str] = Field(None, max_length=50)
    address: Optional[str] = None
    latitude: Optional[Decimal] = Field(None, ge=-90, le=90)
    longitude: Optional[Decimal] = Field(None, ge=-180, le=180)
    is_active: Optional[bool] = None
    contact_person: Optional[str] = Field(None, max_length=100)
    contact_phone: Optional[str] = Field(None, max_length=20)


class DepotResponse(DepotBase):
    """Schema for depot responses (includes ID and timestamps)."""
    id: UUID
    created_at: datetime
    updated_at: datetime


class DepotListResponse(BaseSchema):
    """Schema for paginated depot list responses."""
    total: int
    depots: list[DepotResponse]
