"""
Base Pydantic schemas and common types.
"""
from datetime import datetime
from typing import Generic, TypeVar, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class BaseSchema(BaseModel):
    """Base schema with common configuration."""

    model_config = ConfigDict(
        from_attributes=True,  # Enable ORM mode
        populate_by_name=True,
        use_enum_values=True,
        json_encoders={
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v),
        },
    )


class TimestampSchema(BaseSchema):
    """Schema mixin for timestamp fields."""
    created_at: datetime
    updated_at: datetime


class IDSchema(BaseSchema):
    """Schema mixin for ID field."""
    id: UUID


# Generic type for paginated responses
T = TypeVar("T")


class PaginatedResponse(BaseSchema, Generic[T]):
    """Generic paginated response wrapper."""
    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int

    @classmethod
    def create(
        cls,
        items: list[T],
        total: int,
        page: int,
        page_size: int,
    ) -> "PaginatedResponse[T]":
        """Factory method to create paginated response."""
        total_pages = (total + page_size - 1) // page_size
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )


class GeoLocation(BaseSchema):
    """Geographic location schema."""
    latitude: float
    longitude: float

    def to_wkt(self) -> str:
        """Convert to Well-Known Text format for PostGIS."""
        return f"POINT({self.longitude} {self.latitude})"
