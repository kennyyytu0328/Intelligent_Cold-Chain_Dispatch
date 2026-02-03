"""
Customer Pydantic schemas.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import Field

from app.models.enums import SLATier
from app.schemas.base import BaseSchema


class CustomerBase(BaseSchema):
    """Base customer schema."""
    name: str = Field(..., min_length=1, max_length=200)
    contact_name: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=100)


class CustomerCreate(CustomerBase):
    """Schema for creating a new customer."""
    customer_code: str = Field(..., min_length=1, max_length=50)
    default_sla_tier: SLATier = SLATier.STANDARD
    default_temp_limit: Optional[Decimal] = Field(
        default=Decimal("5.0"),
        description="Default max temperature in °C",
    )


class CustomerUpdate(BaseSchema):
    """Schema for updating a customer (all fields optional)."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    contact_name: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=100)
    default_sla_tier: Optional[SLATier] = None
    default_temp_limit: Optional[Decimal] = None


class CustomerResponse(CustomerBase):
    """Schema for customer response."""
    id: UUID
    customer_code: str
    default_sla_tier: SLATier
    default_temp_limit: Optional[Decimal]
    created_at: datetime
    updated_at: datetime
