"""
Customer model for ICCDDS.
"""
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import String, Numeric, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel
from app.models.enums import SLATier

if TYPE_CHECKING:
    from app.models.shipment import Shipment


class Customer(BaseModel):
    """
    Customer master data with default SLA settings.

    Attributes:
        customer_code: Unique customer identifier
        name: Customer/company name
        contact_name: Primary contact person
        phone: Contact phone number
        email: Contact email
        default_sla_tier: Default SLA tier for new shipments
        default_temp_limit: Default temperature limit for new shipments
    """
    __tablename__ = "customers"

    # Basic Information
    customer_code: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    contact_name: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )

    phone: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
    )

    email: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )

    # Default SLA Settings
    default_sla_tier: Mapped[SLATier] = mapped_column(
        Enum(SLATier, name="sla_tier", create_type=False),
        nullable=False,
        default=SLATier.STANDARD,
        comment="Default SLA tier for new shipments",
    )

    default_temp_limit: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2),
        default=Decimal("5.0"),
        nullable=True,
        comment="Default maximum receiving temperature (°C)",
    )

    # Relationships
    shipments: Mapped[list["Shipment"]] = relationship(
        "Shipment",
        back_populates="customer",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Customer(id={self.id}, code={self.customer_code!r}, name={self.name!r})>"
