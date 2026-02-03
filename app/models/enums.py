"""
Enum type definitions for ICCDDS.

These enums map directly to PostgreSQL ENUM types defined in schema.sql.
"""
from enum import Enum


class InsulationGrade(str, Enum):
    """
    Vehicle insulation grade affecting heat transfer coefficient (K-value).

    Used in formula: ΔT_drive = Time_travel × (T_ambient - T_current) × K_insulation

    K-value mapping:
    - PREMIUM: K = 0.02 (best insulation)
    - STANDARD: K = 0.05 (normal insulation)
    - BASIC: K = 0.10 (minimal insulation)
    """
    PREMIUM = "PREMIUM"
    STANDARD = "STANDARD"
    BASIC = "BASIC"

    @property
    def k_value(self) -> float:
        """Get the heat transfer coefficient for this grade."""
        return {
            InsulationGrade.PREMIUM: 0.02,
            InsulationGrade.STANDARD: 0.05,
            InsulationGrade.BASIC: 0.10,
        }[self]


class DoorType(str, Enum):
    """
    Vehicle door type affecting heat loss during service.

    Used in formula: ΔT_door = Time_service × C_door_type × (1 - 0.5 × IsCurtain)

    Coefficient mapping:
    - ROLL: C = 0.8 (roll-up door, less heat loss)
    - SWING: C = 1.2 (swing door, more heat loss)
    """
    ROLL = "ROLL"
    SWING = "SWING"

    @property
    def coefficient(self) -> float:
        """Get the door coefficient for this type."""
        return {
            DoorType.ROLL: 0.8,
            DoorType.SWING: 1.2,
        }[self]


class SLATier(str, Enum):
    """
    Service Level Agreement tier determining constraint strictness.

    - STRICT: Hard constraint - must satisfy time window (AllowPenalty = False)
    - STANDARD: Soft constraint - can be late with penalty (AllowPenalty = True)
    """
    STRICT = "STRICT"
    STANDARD = "STANDARD"

    @property
    def is_hard_constraint(self) -> bool:
        """Check if this SLA tier requires hard constraint enforcement."""
        return self == SLATier.STRICT


class ShipmentStatus(str, Enum):
    """Shipment lifecycle status."""
    PENDING = "PENDING"        # Waiting for dispatch
    ASSIGNED = "ASSIGNED"      # Assigned to a route
    IN_TRANSIT = "IN_TRANSIT"  # Currently being delivered
    DELIVERED = "DELIVERED"    # Successfully delivered
    FAILED = "FAILED"          # Delivery failed
    CANCELLED = "CANCELLED"    # Cancelled by customer/system


class RouteStatus(str, Enum):
    """Route lifecycle status."""
    PLANNING = "PLANNING"      # Being optimized
    SCHEDULED = "SCHEDULED"    # Optimization complete, ready to execute
    IN_PROGRESS = "IN_PROGRESS"  # Currently executing
    COMPLETED = "COMPLETED"    # All stops delivered
    ABORTED = "ABORTED"        # Route aborted mid-execution


class VehicleStatus(str, Enum):
    """Vehicle availability status."""
    AVAILABLE = "AVAILABLE"    # Ready for dispatch
    IN_USE = "IN_USE"          # Currently on a route
    MAINTENANCE = "MAINTENANCE"  # Under maintenance
    OFFLINE = "OFFLINE"        # Not available


class OptimizationStatus(str, Enum):
    """Optimization job status (matches Celery task states)."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class AlertType(str, Enum):
    """System alert types."""
    TEMP_EXCEEDED = "TEMP_EXCEEDED"      # Temperature above limit
    TEMP_TOO_LOW = "TEMP_TOO_LOW"        # Temperature below minimum
    ETA_VIOLATION = "ETA_VIOLATION"      # Will miss time window
    SLA_AT_RISK = "SLA_AT_RISK"          # SLA compliance at risk
    VEHICLE_OFFLINE = "VEHICLE_OFFLINE"  # Lost contact with vehicle


class AlertSeverity(str, Enum):
    """Alert severity levels."""
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class DeliveryStatus(str, Enum):
    """Individual stop delivery status."""
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
