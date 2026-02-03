"""
Route and RouteStop Pydantic schemas.
"""
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, Any
from uuid import UUID

from pydantic import Field

from app.models.enums import RouteStatus, DeliveryStatus
from app.schemas.base import BaseSchema


class RouteStopResponse(BaseSchema):
    """
    Schema for route stop response.

    Includes thermodynamic predictions:
    - transit_temp_rise: ΔT_drive during travel
    - service_temp_rise: ΔT_door during service
    - cooling_applied: ΔT_cooling from refrigeration
    - predicted_arrival_temp: Critical constraint check
    """
    id: UUID
    route_id: UUID
    shipment_id: UUID

    # Sequence & Location
    sequence_number: int
    address: str
    # location geometry excluded

    # Timing predictions
    expected_arrival_at: datetime
    expected_departure_at: datetime
    target_time_window_index: int
    slack_minutes: Optional[int]

    # THERMODYNAMIC PREDICTIONS
    predicted_arrival_temp: Decimal = Field(
        ...,
        description="Predicted temperature upon arrival (°C) - critical constraint",
    )
    transit_temp_rise: Optional[Decimal] = Field(
        None,
        description="ΔT_drive: temperature rise during transit (°C)",
    )
    service_temp_rise: Optional[Decimal] = Field(
        None,
        description="ΔT_door: temperature rise during service (°C)",
    )
    cooling_applied: Optional[Decimal] = Field(
        None,
        description="ΔT_cooling: cooling effect (°C, negative)",
    )
    predicted_departure_temp: Optional[Decimal] = Field(
        None,
        description="Predicted temperature after service (°C)",
    )
    is_temp_feasible: bool

    # Travel metrics
    distance_from_prev: Optional[Decimal]
    travel_time_from_prev: Optional[int]

    # Actual results
    actual_arrival_at: Optional[datetime]
    actual_temperature: Optional[Decimal]
    delivery_status: Optional[DeliveryStatus]
    notes: Optional[str]

    # Timestamps
    created_at: datetime
    updated_at: datetime


class RouteResponse(BaseSchema):
    """Schema for route response."""
    id: UUID
    route_code: str
    plan_date: date

    # Assignment
    vehicle_id: UUID
    driver_id: Optional[UUID]
    driver_name: Optional[str]

    # Status
    status: RouteStatus

    # Summary metrics
    total_stops: int
    total_distance: Optional[Decimal]
    total_duration: Optional[int]
    total_weight: Optional[Decimal]
    total_volume: Optional[Decimal]

    # Temperature predictions
    initial_temperature: Decimal
    predicted_final_temp: Optional[Decimal]
    predicted_max_temp: Optional[Decimal]

    # Timing
    planned_departure_at: Optional[datetime]
    planned_return_at: Optional[datetime]
    actual_departure_at: Optional[datetime]
    actual_return_at: Optional[datetime]

    # Depot
    depot_address: Optional[str]

    # Optimization metadata
    optimization_job_id: Optional[UUID]
    optimization_cost: Optional[Decimal]
    algorithm_version: Optional[str]

    # Stops (ordered by sequence)
    stops: list[RouteStopResponse] = []

    # Timestamps
    created_at: datetime
    updated_at: datetime

    @property
    def is_temperature_feasible(self) -> bool:
        """Check if all stops have feasible temperature."""
        return all(stop.is_temp_feasible for stop in self.stops)


class RouteListResponse(BaseSchema):
    """Schema for list of routes."""
    items: list[RouteResponse]
    total: int


class RouteStopUpdate(BaseSchema):
    """Schema for updating a route stop during execution."""
    actual_arrival_at: Optional[datetime] = None
    actual_temperature: Optional[Decimal] = None
    delivery_status: Optional[DeliveryStatus] = None
    notes: Optional[str] = None


class RouteSummary(BaseSchema):
    """Lightweight route summary for lists."""
    id: UUID
    route_code: str
    plan_date: date
    vehicle_id: UUID
    driver_name: Optional[str]
    status: RouteStatus
    total_stops: int
    total_distance: Optional[Decimal]
    predicted_max_temp: Optional[Decimal]
    is_temperature_feasible: bool
