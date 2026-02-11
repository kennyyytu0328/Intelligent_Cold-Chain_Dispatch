"""
SQLAlchemy ORM Models for ICCDDS.

This module exports all domain models and enums for the
Intelligent Cold-Chain Dynamic Dispatch System.
"""

# Enums
from app.models.enums import (
    InsulationGrade,
    DoorType,
    SLATier,
    ShipmentStatus,
    RouteStatus,
    VehicleStatus,
    OptimizationStatus,
    AlertType,
    AlertSeverity,
    DeliveryStatus,
)

# Base
from app.models.base import BaseModel, TimestampMixin, UUIDPrimaryKeyMixin

# Domain Models
from app.models.user import User
from app.models.driver import Driver
from app.models.depot import Depot
from app.models.vehicle import Vehicle
from app.models.customer import Customer
from app.models.shipment import Shipment, TimeWindow
from app.models.route import Route, RouteStop
from app.models.optimization import OptimizationJob
from app.models.telemetry import TemperatureLog, Alert

# v3.1 Models
from app.models.geo import RouteHexStat, VehicleHexAffinity
from app.models.insertion import InsertionAttempt
from app.models.labor import DriverLaborLog, LaborViolation

__all__ = [
    # Enums
    "InsulationGrade",
    "DoorType",
    "SLATier",
    "ShipmentStatus",
    "RouteStatus",
    "VehicleStatus",
    "OptimizationStatus",
    "AlertType",
    "AlertSeverity",
    "DeliveryStatus",
    # Base
    "BaseModel",
    "TimestampMixin",
    "UUIDPrimaryKeyMixin",
    # Domain Models
    "User",
    "Driver",
    "Depot",
    "Vehicle",
    "Customer",
    "Shipment",
    "TimeWindow",
    "Route",
    "RouteStop",
    "OptimizationJob",
    "TemperatureLog",
    "Alert",
    # v3.1 Models
    "RouteHexStat",
    "VehicleHexAffinity",
    "InsertionAttempt",
    "DriverLaborLog",
    "LaborViolation",
]
