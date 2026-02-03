"""
Driver model for ICCDDS.
"""
from datetime import date
from typing import TYPE_CHECKING, Optional

from sqlalchemy import String, Date, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.vehicle import Vehicle
    from app.models.route import Route


class Driver(BaseModel):
    """
    Driver master data with license information.

    Attributes:
        employee_id: Unique employee identifier
        name: Driver's full name
        phone: Contact phone number
        email: Contact email
        license_number: Driving license number
        license_expiry: License expiration date
        is_active: Whether driver is currently active
    """
    __tablename__ = "drivers"

    # Basic Information
    employee_id: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    phone: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
    )

    email: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )

    # License Information
    license_number: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    license_expiry: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    # Status
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # Relationships
    vehicles: Mapped[list["Vehicle"]] = relationship(
        "Vehicle",
        back_populates="driver",
        lazy="selectin",
    )

    routes: Mapped[list["Route"]] = relationship(
        "Route",
        back_populates="driver",
        lazy="selectin",
    )

    @property
    def is_license_valid(self) -> bool:
        """Check if driver's license is still valid."""
        return self.license_expiry >= date.today()

    def __repr__(self) -> str:
        return f"<Driver(id={self.id}, name={self.name!r}, employee_id={self.employee_id!r})>"
