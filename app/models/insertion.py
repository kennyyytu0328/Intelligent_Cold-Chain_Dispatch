"""
Dynamic Insertion model (v3.1).

Tracks insertion attempts for real-time order insertion into active routes.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import (
    String, Integer, Text, Numeric, DateTime, ForeignKey,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.base import UUIDPrimaryKeyMixin


class InsertionAttempt(Base, UUIDPrimaryKeyMixin):
    """Audit trail for dynamic route insertion attempts."""

    __tablename__ = "insertion_attempts"

    route_id: Mapped[UUID] = mapped_column(
        ForeignKey("routes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    shipment_id: Mapped[UUID] = mapped_column(
        ForeignKey("shipments.id"),
        nullable=False,
    )

    target_route_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    proposed_position: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    temp_risk_score: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 3),
        nullable=True,
    )

    delay_impact_minutes: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )

    extra_distance_meters: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="PENDING",
        server_default="PENDING",
    )

    rejection_reason: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    attempted_by: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="CURRENT_TIMESTAMP",
    )

    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<InsertionAttempt(route={self.route_id}, "
            f"shipment={self.shipment_id}, status={self.status!r})>"
        )
