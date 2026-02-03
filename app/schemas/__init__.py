"""
Pydantic schemas for API request/response validation.
"""

from app.schemas.base import BaseSchema, PaginatedResponse
from app.schemas.driver import (
    DriverCreate,
    DriverUpdate,
    DriverResponse,
    DriverListResponse,
)
from app.schemas.depot import (
    DepotCreate,
    DepotUpdate,
    DepotResponse,
    DepotListResponse,
)
from app.schemas.vehicle import (
    VehicleCreate,
    VehicleUpdate,
    VehicleResponse,
    VehicleListResponse,
    VehicleThermoParams,
)
from app.schemas.customer import (
    CustomerCreate,
    CustomerUpdate,
    CustomerResponse,
)
from app.schemas.shipment import (
    TimeWindowSchema,
    DimensionsSchema,
    ShipmentCreate,
    ShipmentUpdate,
    ShipmentResponse,
    ShipmentListResponse,
)
from app.schemas.route import (
    RouteStopResponse,
    RouteResponse,
    RouteListResponse,
)
from app.schemas.optimization import (
    OptimizationRequest,
    OptimizationResponse,
    OptimizationStatusResponse,
)

__all__ = [
    # Base
    "BaseSchema",
    "PaginatedResponse",
    # Driver
    "DriverCreate",
    "DriverUpdate",
    "DriverResponse",
    "DriverListResponse",
    # Depot
    "DepotCreate",
    "DepotUpdate",
    "DepotResponse",
    "DepotListResponse",
    # Vehicle
    "VehicleCreate",
    "VehicleUpdate",
    "VehicleResponse",
    "VehicleListResponse",
    "VehicleThermoParams",
    # Customer
    "CustomerCreate",
    "CustomerUpdate",
    "CustomerResponse",
    # Shipment
    "TimeWindowSchema",
    "DimensionsSchema",
    "ShipmentCreate",
    "ShipmentUpdate",
    "ShipmentResponse",
    "ShipmentListResponse",
    # Route
    "RouteStopResponse",
    "RouteResponse",
    "RouteListResponse",
    # Optimization
    "OptimizationRequest",
    "OptimizationResponse",
    "OptimizationStatusResponse",
]
