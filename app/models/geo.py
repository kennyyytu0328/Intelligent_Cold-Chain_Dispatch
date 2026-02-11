"""
Geospatial models for Smart Assignment (v3.1).

RouteHexStat: H3 cell performance metrics.
VehicleHexAffinity: Vehicle/driver zone affinity scores.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import (
    String, Integer, Numeric, DateTime, ForeignKey, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.base import UUIDPrimaryKeyMixin


class RouteHexStat(Base, UUIDPrimaryKeyMixin):
    """H3 cell-level delivery statistics for difficulty estimation."""

    __tablename__ = "route_hex_stats"

    __table_args__ = (
        UniqueConstraint("h3_index", name="uq_route_hex_stats_h3"),
    )

    h3_index: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
    )

    total_deliveries: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    avg_service_time_minutes: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )

    avg_delay_minutes: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(6, 2),
        nullable=True,
        default=Decimal("0"),
        server_default="0",
    )

    difficulty_factor: Mapped[Decimal] = mapped_column(
        Numeric(4, 3),
        nullable=False,
        default=Decimal("0.5"),
        server_default="0.5",
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="CURRENT_TIMESTAMP",
    )

    def __repr__(self) -> str:
        return (
            f"<RouteHexStat(h3={self.h3_index!r}, "
            f"deliveries={self.total_deliveries}, "
            f"difficulty={self.difficulty_factor})>"
        )


class VehicleHexAffinity(Base, UUIDPrimaryKeyMixin):
    """Vehicle/driver affinity scores per H3 cell."""

    __tablename__ = "vehicle_hex_affinities"

    __table_args__ = (
        UniqueConstraint("vehicle_id", "h3_index", name="uq_vehicle_hex_affinity"),
    )

    vehicle_id: Mapped[UUID] = mapped_column(
        ForeignKey("vehicles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    driver_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("drivers.id", ondelete="SET NULL"),
        nullable=True,
    )

    h3_index: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
    )

    affinity_score: Mapped[Decimal] = mapped_column(
        Numeric(4, 3),
        nullable=False,
        default=Decimal("0.5"),
        server_default="0.5",
    )

    sample_size: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    avg_on_time_rate: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(4, 3),
        nullable=True,
    )

    avg_temp_compliance_rate: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(4, 3),
        nullable=True,
    )

    last_delivery_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="CURRENT_TIMESTAMP",
    )

    def __repr__(self) -> str:
        return (
            f"<VehicleHexAffinity(vehicle={self.vehicle_id}, "
            f"h3={self.h3_index!r}, score={self.affinity_score})>"
        )
