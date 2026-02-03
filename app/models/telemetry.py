"""
Telemetry and Alert models for ICCDDS.

Handles IoT sensor data and system alerts.
"""
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional, Any
from uuid import UUID

from geoalchemy2 import Geometry
from sqlalchemy import String, Text, Boolean, Numeric, Enum, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel
from app.models.enums import AlertType, AlertSeverity

if TYPE_CHECKING:
    from app.models.vehicle import Vehicle
    from app.models.route import Route
    from app.models.shipment import Shipment


class TemperatureLog(BaseModel):
    """
    High-frequency IoT temperature telemetry data.

    This table receives frequent inserts from vehicle IoT sensors.
    Uses BRIN index on recorded_at for efficient time-series queries.

    Attributes:
        vehicle_id: Source vehicle
        route_id: Active route (if any)
        temperature: Compartment temperature reading
        location: GPS coordinates at time of reading
        recorded_at: Timestamp of the reading
        is_cooling_active: Whether refrigeration unit is running
        ambient_temperature: Outside temperature (if sensor available)
    """
    __tablename__ = "temperature_logs"

    # =========================================================================
    # References
    # =========================================================================
    vehicle_id: Mapped[UUID] = mapped_column(
        ForeignKey("vehicles.id"),
        nullable=False,
        index=True,
    )

    route_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("routes.id"),
        nullable=True,
    )

    # =========================================================================
    # Temperature Reading
    # =========================================================================
    temperature: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        comment="Compartment temperature (°C)",
    )

    # Location at time of reading
    location: Mapped[Optional[str]] = mapped_column(
        Geometry("POINT", srid=4326),
        nullable=True,
    )

    # Timestamp of reading (indexed with BRIN for time-series efficiency)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        index=True,  # Note: In production, use BRIN index via raw SQL
    )

    # =========================================================================
    # Additional Sensor Data
    # =========================================================================
    is_cooling_active: Mapped[Optional[bool]] = mapped_column(
        Boolean,
        nullable=True,
        comment="True if refrigeration unit is running",
    )

    ambient_temperature: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2),
        nullable=True,
        comment="Outside ambient temperature (°C)",
    )

    # =========================================================================
    # Relationships
    # =========================================================================
    vehicle: Mapped["Vehicle"] = relationship(
        "Vehicle",
        back_populates="temperature_logs",
        lazy="joined",
    )

    route: Mapped[Optional["Route"]] = relationship(
        "Route",
        back_populates="temperature_logs",
        lazy="joined",
    )

    def __repr__(self) -> str:
        return (
            f"<TemperatureLog(vehicle={self.vehicle_id}, "
            f"temp={self.temperature}°C, at={self.recorded_at})>"
        )


class Alert(BaseModel):
    """
    System alerts for temperature and SLA violations.

    Alert Types:
    - TEMP_EXCEEDED: Temperature above limit
    - TEMP_TOO_LOW: Temperature below minimum
    - ETA_VIOLATION: Will miss time window
    - SLA_AT_RISK: SLA compliance at risk
    - VEHICLE_OFFLINE: Lost contact with vehicle

    Severity Levels:
    - INFO: Informational only
    - WARNING: Requires attention
    - CRITICAL: Immediate action required
    """
    __tablename__ = "alerts"

    # =========================================================================
    # Related Entities
    # =========================================================================
    vehicle_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("vehicles.id"),
        nullable=True,
    )

    route_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("routes.id"),
        nullable=True,
    )

    shipment_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("shipments.id"),
        nullable=True,
    )

    # =========================================================================
    # Alert Classification
    # =========================================================================
    alert_type: Mapped[AlertType] = mapped_column(
        Enum(AlertType, name="alert_type", create_type=False),
        nullable=False,
        index=True,
    )

    severity: Mapped[AlertSeverity] = mapped_column(
        Enum(AlertSeverity, name="alert_severity", create_type=False),
        nullable=False,
        default=AlertSeverity.WARNING,
    )

    # =========================================================================
    # Alert Content
    # =========================================================================
    message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # Additional structured details
    details: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Additional alert details in structured format",
    )

    # =========================================================================
    # Temperature Context (for temperature alerts)
    # =========================================================================
    current_temperature: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2),
        nullable=True,
        comment="Temperature at time of alert (°C)",
    )

    threshold_temperature: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2),
        nullable=True,
        comment="Temperature threshold that was violated (°C)",
    )

    # =========================================================================
    # Acknowledgement
    # =========================================================================
    is_acknowledged: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        index=True,
    )

    acknowledged_by: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("drivers.id"),
        nullable=True,
    )

    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # =========================================================================
    # Resolution
    # =========================================================================
    is_resolved: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        index=True,
    )

    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    resolution_notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    # =========================================================================
    # Relationships
    # =========================================================================
    vehicle: Mapped[Optional["Vehicle"]] = relationship(
        "Vehicle",
        lazy="joined",
    )

    route: Mapped[Optional["Route"]] = relationship(
        "Route",
        lazy="joined",
    )

    shipment: Mapped[Optional["Shipment"]] = relationship(
        "Shipment",
        lazy="joined",
    )

    # =========================================================================
    # Helper Methods
    # =========================================================================

    @property
    def is_critical(self) -> bool:
        """Check if this is a critical alert."""
        return self.severity == AlertSeverity.CRITICAL

    @property
    def is_active(self) -> bool:
        """Check if alert is still active (not resolved)."""
        return not self.is_resolved

    def acknowledge(self, user_id: UUID) -> None:
        """Mark alert as acknowledged."""
        self.is_acknowledged = True
        self.acknowledged_by = user_id
        self.acknowledged_at = datetime.now()

    def resolve(self, notes: Optional[str] = None) -> None:
        """Mark alert as resolved."""
        self.is_resolved = True
        self.resolved_at = datetime.now()
        if notes:
            self.resolution_notes = notes

    @classmethod
    def create_temp_alert(
        cls,
        vehicle_id: UUID,
        current_temp: Decimal,
        threshold: Decimal,
        route_id: Optional[UUID] = None,
        shipment_id: Optional[UUID] = None,
    ) -> "Alert":
        """
        Factory method to create a temperature exceedance alert.

        Args:
            vehicle_id: Vehicle with temperature issue
            current_temp: Current temperature reading
            threshold: Temperature limit that was exceeded
            route_id: Active route (if any)
            shipment_id: Affected shipment (if any)

        Returns:
            New Alert instance
        """
        severity = AlertSeverity.CRITICAL if current_temp > threshold + 3 else AlertSeverity.WARNING

        return cls(
            vehicle_id=vehicle_id,
            route_id=route_id,
            shipment_id=shipment_id,
            alert_type=AlertType.TEMP_EXCEEDED,
            severity=severity,
            message=f"Temperature {current_temp}°C exceeds limit {threshold}°C",
            current_temperature=current_temp,
            threshold_temperature=threshold,
            details={
                "temp_diff": float(current_temp - threshold),
                "auto_generated": True,
            },
        )

    @classmethod
    def create_eta_alert(
        cls,
        route_id: UUID,
        shipment_id: UUID,
        vehicle_id: UUID,
        expected_arrival: datetime,
        time_window_end: str,
        delay_minutes: int,
    ) -> "Alert":
        """
        Factory method to create an ETA violation alert.

        Args:
            route_id: Affected route
            shipment_id: Shipment that will be late
            vehicle_id: Assigned vehicle
            expected_arrival: New expected arrival time
            time_window_end: Time window end time (HH:MM)
            delay_minutes: Minutes past window end

        Returns:
            New Alert instance
        """
        severity = AlertSeverity.CRITICAL if delay_minutes > 30 else AlertSeverity.WARNING

        return cls(
            vehicle_id=vehicle_id,
            route_id=route_id,
            shipment_id=shipment_id,
            alert_type=AlertType.ETA_VIOLATION,
            severity=severity,
            message=f"Expected arrival {delay_minutes} min after time window closes at {time_window_end}",
            details={
                "expected_arrival": expected_arrival.isoformat(),
                "time_window_end": time_window_end,
                "delay_minutes": delay_minutes,
                "auto_generated": True,
            },
        )

    def __repr__(self) -> str:
        return (
            f"<Alert(id={self.id}, type={self.alert_type.value}, "
            f"severity={self.severity.value}, resolved={self.is_resolved})>"
        )
