"""
Shipment model for ICCDDS.

Supports complex receiving rules including multiple time windows and SLA tiers.
"""
from datetime import datetime, time
from decimal import Decimal
from typing import TYPE_CHECKING, Optional, Any
from uuid import UUID

from geoalchemy2 import Geometry
from sqlalchemy import String, Text, Integer, Boolean, Numeric, Enum, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel
from app.models.enums import SLATier, ShipmentStatus

if TYPE_CHECKING:
    from app.models.customer import Customer
    from app.models.route import Route, RouteStop


class TimeWindow:
    """
    Helper class representing a delivery time window.

    This is a value object for working with time window data stored in JSONB.
    """
    def __init__(self, start: str, end: str):
        """
        Initialize time window.

        Args:
            start: Start time in "HH:MM" format
            end: End time in "HH:MM" format
        """
        self.start = start
        self.end = end

    @property
    def start_time(self) -> time:
        """Parse start as time object."""
        parts = self.start.split(":")
        return time(int(parts[0]), int(parts[1]))

    @property
    def end_time(self) -> time:
        """Parse end as time object."""
        parts = self.end.split(":")
        return time(int(parts[0]), int(parts[1]))

    @property
    def duration_minutes(self) -> int:
        """Calculate window duration in minutes."""
        start_mins = self.start_time.hour * 60 + self.start_time.minute
        end_mins = self.end_time.hour * 60 + self.end_time.minute
        return end_mins - start_mins

    def contains(self, t: time) -> bool:
        """Check if a time falls within this window."""
        return self.start_time <= t <= self.end_time

    def to_dict(self) -> dict[str, str]:
        """Convert to dictionary for JSON storage."""
        return {"start": self.start, "end": self.end}

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> "TimeWindow":
        """Create TimeWindow from dictionary."""
        return cls(start=data["start"], end=data["end"])

    def __repr__(self) -> str:
        return f"TimeWindow({self.start}-{self.end})"


class Shipment(BaseModel):
    """
    Delivery order with multi-time-windows and temperature constraints.

    Key Features:
    - Multiple Time Windows: JSONB array supporting OR (disjunction) logic
    - SLA Tiers: STRICT (hard constraint) vs STANDARD (soft constraint)
    - Temperature Limits: Hard constraint for cold-chain compliance

    Time Windows Format:
    ```json
    [
        {"start": "08:00", "end": "10:00"},
        {"start": "14:00", "end": "16:00"}
    ]
    ```
    Algorithm treats these as OR: satisfy ANY one window.
    """
    __tablename__ = "shipments"

    # =========================================================================
    # Order Reference
    # =========================================================================
    order_number: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
    )

    customer_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("customers.id"),
        nullable=True,
    )

    # =========================================================================
    # Delivery Location
    # =========================================================================
    delivery_address: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # PostGIS geometry for lat/lon coordinates (SRID 4326 = WGS84)
    geo_location: Mapped[str] = mapped_column(
        Geometry("POINT", srid=4326),
        nullable=False,
    )

    # Denormalized for quick access
    latitude: Mapped[Decimal] = mapped_column(
        Numeric(10, 7),
        nullable=False,
    )

    longitude: Mapped[Decimal] = mapped_column(
        Numeric(10, 7),
        nullable=False,
    )

    # =========================================================================
    # Time Windows (Multiple Time Windows Support)
    # =========================================================================
    # JSONB array: [{"start": "08:00", "end": "10:00"}, ...]
    time_windows: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        comment="Array of valid delivery time windows (OR relationship)",
    )

    # =========================================================================
    # SLA & Temperature Constraints
    # =========================================================================
    sla_tier: Mapped[SLATier] = mapped_column(
        Enum(SLATier, name="sla_tier", create_type=False),
        nullable=False,
        default=SLATier.STANDARD,
        comment="STRICT=hard constraint, STANDARD=soft constraint with penalty",
    )

    # Maximum acceptable temperature at delivery (HARD CONSTRAINT)
    temp_limit_upper: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        default=Decimal("5.0"),
        comment="Maximum acceptable temperature - exceeding causes rejection (°C)",
    )

    # Optional: minimum temperature (for freeze-sensitive goods)
    temp_limit_lower: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2),
        nullable=True,
        comment="Minimum acceptable temperature (°C)",
    )

    # =========================================================================
    # Service Parameters
    # =========================================================================
    # Time required for unloading (affects door-open heat loss calculation)
    service_duration: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=15,
        comment="Unloading time in minutes (affects ΔT_door calculation)",
    )

    # =========================================================================
    # Cargo Specifications
    # =========================================================================
    weight: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        comment="Total weight in kg",
    )

    volume: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2),
        nullable=True,
        comment="Total volume in m³",
    )

    # Detailed dimensions for 3D bin packing: {"l": 100, "w": 80, "h": 60} (cm)
    dimensions: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Cargo dimensions for bin packing (L/W/H in cm)",
    )

    package_count: Mapped[int] = mapped_column(
        Integer,
        default=1,
        comment="Number of packages/pallets",
    )

    # =========================================================================
    # Status & Assignment
    # =========================================================================
    status: Mapped[ShipmentStatus] = mapped_column(
        Enum(ShipmentStatus, name="shipment_status", create_type=False),
        nullable=False,
        default=ShipmentStatus.PENDING,
    )

    # Which route this shipment is assigned to
    route_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("routes.id"),
        nullable=True,
    )

    # Sequence position in route
    route_sequence: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )

    # =========================================================================
    # Delivery Results
    # =========================================================================
    actual_arrival_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    actual_temperature: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2),
        nullable=True,
        comment="Actual temperature at delivery from IoT sensor (°C)",
    )

    was_on_time: Mapped[Optional[bool]] = mapped_column(
        Boolean,
        nullable=True,
    )

    was_temp_compliant: Mapped[Optional[bool]] = mapped_column(
        Boolean,
        nullable=True,
    )

    delivery_notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    # =========================================================================
    # Metadata
    # =========================================================================
    priority: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Higher value = more important",
    )

    special_instructions: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    # =========================================================================
    # Relationships
    # =========================================================================
    customer: Mapped[Optional["Customer"]] = relationship(
        "Customer",
        back_populates="shipments",
        lazy="joined",
    )

    route: Mapped[Optional["Route"]] = relationship(
        "Route",
        back_populates="shipments",
        lazy="joined",
    )

    route_stop: Mapped[Optional["RouteStop"]] = relationship(
        "RouteStop",
        back_populates="shipment",
        uselist=False,
        lazy="select",  # Changed from "joined" to avoid duplicate rows
    )

    # =========================================================================
    # Time Window Helper Methods
    # =========================================================================

    def get_time_windows(self) -> list[TimeWindow]:
        """
        Get list of TimeWindow objects from JSONB data.

        Returns:
            List of TimeWindow instances
        """
        return [TimeWindow.from_dict(tw) for tw in self.time_windows]

    def set_time_windows(self, windows: list[TimeWindow]) -> None:
        """
        Set time windows from TimeWindow objects.

        Args:
            windows: List of TimeWindow instances
        """
        self.time_windows = [tw.to_dict() for tw in windows]

    def is_time_valid(self, delivery_time: time) -> bool:
        """
        Check if a delivery time satisfies any time window (OR logic).

        Args:
            delivery_time: Proposed delivery time

        Returns:
            True if time falls within any window
        """
        for tw in self.get_time_windows():
            if tw.contains(delivery_time):
                return True
        return False

    def get_earliest_start(self) -> time:
        """Get the earliest start time across all windows."""
        windows = self.get_time_windows()
        return min(tw.start_time for tw in windows)

    def get_latest_end(self) -> time:
        """Get the latest end time across all windows."""
        windows = self.get_time_windows()
        return max(tw.end_time for tw in windows)

    # =========================================================================
    # Constraint Checking
    # =========================================================================

    def is_temperature_compliant(self, temperature: float) -> bool:
        """
        Check if a temperature is within acceptable limits.

        Args:
            temperature: Temperature to check (°C)

        Returns:
            True if temperature is compliant
        """
        if temperature > float(self.temp_limit_upper):
            return False
        if self.temp_limit_lower is not None:
            if temperature < float(self.temp_limit_lower):
                return False
        return True

    @property
    def is_strict_sla(self) -> bool:
        """Check if this shipment has strict SLA (hard constraint)."""
        return self.sla_tier == SLATier.STRICT

    def __repr__(self) -> str:
        return (
            f"<Shipment(id={self.id}, order={self.order_number!r}, "
            f"sla={self.sla_tier.value}, temp_limit={self.temp_limit_upper}°C)>"
        )
