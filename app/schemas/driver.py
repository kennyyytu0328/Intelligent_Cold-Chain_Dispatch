"""
Driver Pydantic schemas.
"""
from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import Field, field_validator

from app.schemas.base import BaseSchema


class DriverBase(BaseSchema):
    """Base driver schema with common fields."""
    name: str = Field(..., min_length=1, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=100)
    license_number: str = Field(..., min_length=1, max_length=50)
    license_expiry: date


class DriverCreate(DriverBase):
    """Schema for creating a new driver."""
    employee_id: str = Field(..., min_length=1, max_length=50)

    @field_validator("license_expiry")
    @classmethod
    def license_must_be_valid(cls, v: date) -> date:
        if v < date.today():
            raise ValueError("License expiry date must be in the future")
        return v


class DriverUpdate(BaseSchema):
    """Schema for updating a driver (all fields optional)."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=100)
    license_number: Optional[str] = Field(None, min_length=1, max_length=50)
    license_expiry: Optional[date] = None
    is_active: Optional[bool] = None


class DriverResponse(DriverBase):
    """Schema for driver response."""
    id: UUID
    employee_id: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class DriverListResponse(BaseSchema):
    """Schema for list of drivers."""
    items: list[DriverResponse]
    total: int
