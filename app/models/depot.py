"""
Depot model for ICCDDS.

Represents warehouse/depot locations where vehicles start and end their routes.
"""
from decimal import Decimal
from typing import Optional

from geoalchemy2 import Geography
from sqlalchemy import String, Boolean, Numeric, Text, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class Depot(BaseModel):
    """
    Warehouse/depot location model.

    Stores depot information including geospatial data for route optimization.
    PostGIS geography type is used for efficient distance calculations.
    """
    __tablename__ = "depots"

    # =========================================================================
    # Basic Information
    # =========================================================================
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Depot name",
    )

    code: Mapped[Optional[str]] = mapped_column(
        String(50),
        unique=True,
        nullable=True,
        index=True,
        comment="Optional depot code (e.g., TP-001)",
    )

    address: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Full street address",
    )

    # =========================================================================
    # Geospatial Data
    # =========================================================================
    latitude: Mapped[Decimal] = mapped_column(
        Numeric(10, 8),
        nullable=False,
        comment="Latitude in decimal degrees",
    )

    longitude: Mapped[Decimal] = mapped_column(
        Numeric(11, 8),
        nullable=False,
        comment="Longitude in decimal degrees",
    )

    # PostGIS geography type for distance calculations
    location: Mapped[Optional[str]] = mapped_column(
        Geography("POINT", srid=4326),
        nullable=True,
        comment="PostGIS geography point",
    )

    # =========================================================================
    # Operational Status
    # =========================================================================
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
        comment="Whether this depot is currently active",
    )

    # =========================================================================
    # Contact Information
    # =========================================================================
    contact_person: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Contact person name",
    )

    contact_phone: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="Contact phone number",
    )

    # =========================================================================
    # Constraints
    # =========================================================================
    __table_args__ = (
        CheckConstraint(
            "latitude BETWEEN -90 AND 90",
            name="valid_latitude",
        ),
        CheckConstraint(
            "longitude BETWEEN -180 AND 180",
            name="valid_longitude",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<Depot(id={self.id}, name={self.name!r}, "
            f"lat={self.latitude}, lon={self.longitude}, "
            f"active={self.is_active})>"
        )
