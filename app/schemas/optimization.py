"""
Optimization job Pydantic schemas.
"""
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, Any
from uuid import UUID

from pydantic import Field

from app.models.enums import OptimizationStatus
from app.schemas.base import BaseSchema


class OptimizationParameters(BaseSchema):
    """
    Parameters for the optimization algorithm.

    These control OR-Tools solver behavior and constraints.
    """
    time_limit_seconds: int = Field(
        default=300,
        ge=10,
        le=3600,
        description="Maximum solver time in seconds",
    )

    # Optimization strategy
    strategy: str = Field(
        default="MINIMIZE_VEHICLES",
        description="MINIMIZE_VEHICLES or MINIMIZE_DISTANCE",
    )

    # Environmental conditions
    ambient_temperature: Decimal = Field(
        default=Decimal("30.0"),
        description="Assumed ambient temperature (°C)",
    )

    # Initial vehicle temperature
    initial_vehicle_temp: Decimal = Field(
        default=Decimal("-5.0"),
        description="Starting compartment temperature (°C)",
    )

    # Allow partial solution
    allow_partial: bool = Field(
        default=True,
        description="Allow solution even if some shipments unassigned",
    )

    # Maximum vehicles to use (0 = no limit)
    max_vehicles: int = Field(
        default=0,
        ge=0,
        description="Maximum vehicles to use (0 = no limit)",
    )


class OptimizationRequest(BaseSchema):
    """
    Request schema for starting an optimization job.

    The API will return a task_id immediately, and the optimization
    will run asynchronously via Celery.
    """
    plan_date: date = Field(
        ...,
        description="Date to optimize routes for",
    )

    planned_departure_time: str = Field(
        default="06:00",
        pattern=r"^\d{2}:\d{2}$",
        description="Earliest vehicle departure time (HH:MM format, e.g., '08:00'). "
                    "Vehicles cannot depart before this time. "
                    "Shipments with time windows ending before this + travel time will be infeasible.",
    )

    # Optional: specify which vehicles/shipments to include
    vehicle_ids: Optional[list[UUID]] = Field(
        None,
        description="Specific vehicles to use (None = all available)",
    )

    shipment_ids: Optional[list[UUID]] = Field(
        None,
        description="Specific shipments to optimize (None = all pending)",
    )

    # Algorithm parameters
    parameters: OptimizationParameters = Field(
        default_factory=OptimizationParameters,
        description="Algorithm configuration",
    )

    # Depot location (if not using default)
    depot_latitude: Optional[Decimal] = Field(None, ge=-90, le=90)
    depot_longitude: Optional[Decimal] = Field(None, ge=-180, le=180)
    depot_address: Optional[str] = None


class OptimizationResponse(BaseSchema):
    """
    Response schema when optimization job is created.

    Returns immediately with task_id for status polling.
    """
    job_id: UUID
    celery_task_id: Optional[str]
    status: str = OptimizationStatus.PENDING.value
    message: str = "Optimization job queued successfully"

    # Estimated info
    shipment_count: int
    vehicle_count: int


class OptimizationResultSummary(BaseSchema):
    """Summary of optimization results."""
    routes_created: int
    shipments_assigned: int
    shipments_unassigned: int
    total_distance_km: Optional[Decimal]
    total_duration_minutes: Optional[int]
    total_cost: Optional[Decimal]
    solver_status: str
    solver_time_seconds: Optional[float]


class OptimizationStatusResponse(BaseSchema):
    """
    Response schema for optimization job status.

    Used for polling job progress.
    """
    job_id: UUID
    celery_task_id: Optional[str]
    status: str
    progress: int = Field(default=0, ge=0, le=100, description="Progress percentage (0-100)")
    plan_date: date

    # Timing
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    duration_seconds: Optional[float]

    # Results (if completed)
    result_summary: Optional[OptimizationResultSummary]
    route_ids: Optional[list[UUID]]
    unassigned_shipment_ids: Optional[list[UUID]]

    # Error (if failed)
    error_message: Optional[str]

    @property
    def is_finished(self) -> bool:
        """Check if job has finished."""
        return self.status in (
            OptimizationStatus.COMPLETED.value,
            OptimizationStatus.FAILED.value,
            OptimizationStatus.CANCELLED.value,
        )

    @property
    def is_success(self) -> bool:
        """Check if job completed successfully."""
        return self.status == OptimizationStatus.COMPLETED.value


class OptimizationCancelRequest(BaseSchema):
    """Request to cancel a running optimization job."""
    job_id: UUID
    reason: Optional[str] = None
