"""
Labor Hour Tracking models (v3.1).

DriverLaborLog: Per-route labor records with computed total.
LaborViolation: Violation/override records for labor compliance.
"""
from datetime import datetime, date
from typing import Optional
from uuid import UUID

from sqlalchemy import (
    String, Integer, Text, Boolean, Date, DateTime, ForeignKey,
    Computed, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.base import UUIDPrimaryKeyMixin


class DriverLaborLog(Base, UUIDPrimaryKeyMixin):
    """Granular labor hour tracking per driver/route/day."""

    __tablename__ = "driver_labor_logs"

    __table_args__ = (
        UniqueConstraint(
            "driver_id", "route_id", "log_date",
            name="uq_driver_labor_log",
        ),
    )

    driver_id: Mapped[UUID] = mapped_column(
        ForeignKey("drivers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    route_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("routes.id", ondelete="SET NULL"),
        nullable=True,
    )

    log_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    shift_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    shift_end: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    drive_time_minutes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    service_time_minutes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    break_time_minutes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    total_minutes: Mapped[Optional[int]] = mapped_column(
        Integer,
        Computed("drive_time_minutes + service_time_minutes"),
        nullable=True,
    )

    source: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="SYSTEM",
        server_default="SYSTEM",
    )

    notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="CURRENT_TIMESTAMP",
    )

    def __repr__(self) -> str:
        return (
            f"<DriverLaborLog(driver={self.driver_id}, "
            f"date={self.log_date}, total={self.total_minutes}m)>"
        )


class LaborViolation(Base, UUIDPrimaryKeyMixin):
    """Labor compliance violation and override records."""

    __tablename__ = "labor_violations"

    driver_id: Mapped[UUID] = mapped_column(
        ForeignKey("drivers.id"),
        nullable=False,
        index=True,
    )

    route_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("routes.id"),
        nullable=True,
    )

    violation_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    severity: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="WARNING",
        server_default="WARNING",
    )

    projected_minutes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    limit_minutes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    overage_minutes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    was_overridden: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )

    overridden_by: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    override_reason: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    override_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="CURRENT_TIMESTAMP",
    )

    def __repr__(self) -> str:
        return (
            f"<LaborViolation(driver={self.driver_id}, "
            f"type={self.violation_type!r}, severity={self.severity!r})>"
        )
