"""
Optimization job model for ICCDDS.

Tracks async optimization tasks that run via Celery.
"""
from datetime import datetime, date
from typing import Optional, Any
from uuid import UUID

from sqlalchemy import String, Text, Date, DateTime
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel
from app.models.enums import OptimizationStatus


class OptimizationJob(BaseModel):
    """
    Async optimization task tracking for Celery integration.

    This model tracks the lifecycle of OR-Tools optimization jobs:
    1. PENDING: Job created, waiting to be picked up by worker
    2. RUNNING: Worker is executing OR-Tools solver
    3. COMPLETED: Optimization finished, routes generated
    4. FAILED: Error during optimization
    5. CANCELLED: Job cancelled by user

    Attributes:
        celery_task_id: Celery task UUID for status polling
        status: Current job status
        plan_date: Date being optimized
        vehicle_ids: Which vehicles to consider
        shipment_ids: Which shipments to optimize
        parameters: Algorithm parameters (time limit, strategy, etc.)
        result_summary: Summary of optimization results
        route_ids: Generated route UUIDs
    """
    __tablename__ = "optimization_jobs"

    # =========================================================================
    # Celery Integration
    # =========================================================================
    celery_task_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        unique=True,
        nullable=True,
        index=True,
        comment="Celery async task ID for status polling",
    )

    # =========================================================================
    # Job Status
    # =========================================================================
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=OptimizationStatus.PENDING.value,
        index=True,
    )

    # Progress percentage (0-100)
    progress: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
        comment="Optimization progress percentage (0-100)",
    )

    # =========================================================================
    # Input Parameters
    # =========================================================================
    plan_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )

    # Which vehicles to consider (NULL = all available)
    vehicle_ids: Mapped[Optional[list[UUID]]] = mapped_column(
        ARRAY(PG_UUID(as_uuid=True)),
        nullable=True,
        comment="Specific vehicles to use (NULL = all available)",
    )

    # Which shipments to optimize (NULL = all pending)
    shipment_ids: Mapped[Optional[list[UUID]]] = mapped_column(
        ARRAY(PG_UUID(as_uuid=True)),
        nullable=True,
        comment="Specific shipments to optimize (NULL = all pending)",
    )

    # Algorithm parameters
    # Example:
    # {
    #     "time_limit_seconds": 300,
    #     "strategy": "MINIMIZE_VEHICLES",
    #     "ambient_temperature": 30.0,
    #     "allow_partial": false
    # }
    parameters: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Algorithm configuration parameters",
    )

    # =========================================================================
    # Results
    # =========================================================================

    # Summary of results
    # Example:
    # {
    #     "routes_created": 5,
    #     "shipments_assigned": 47,
    #     "shipments_unassigned": 3,
    #     "total_distance_km": 234.5,
    #     "total_cost": 12345.67,
    #     "solver_status": "OPTIMAL",
    #     "iterations": 1523
    # }
    result_summary: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Optimization result summary",
    )

    # Generated route IDs
    route_ids: Mapped[Optional[list[UUID]]] = mapped_column(
        ARRAY(PG_UUID(as_uuid=True)),
        nullable=True,
        comment="IDs of routes created by this job",
    )

    # Unassigned shipment IDs (if any)
    unassigned_shipment_ids: Mapped[Optional[list[UUID]]] = mapped_column(
        ARRAY(PG_UUID(as_uuid=True)),
        nullable=True,
        comment="Shipments that could not be assigned",
    )

    # =========================================================================
    # Timing
    # =========================================================================
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # =========================================================================
    # Error Information
    # =========================================================================
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    error_traceback: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    # =========================================================================
    # Helper Properties
    # =========================================================================

    @property
    def is_pending(self) -> bool:
        return self.status == OptimizationStatus.PENDING.value

    @property
    def is_running(self) -> bool:
        return self.status == OptimizationStatus.RUNNING.value

    @property
    def is_completed(self) -> bool:
        return self.status == OptimizationStatus.COMPLETED.value

    @property
    def is_failed(self) -> bool:
        return self.status == OptimizationStatus.FAILED.value

    @property
    def is_finished(self) -> bool:
        """Check if job has finished (completed, failed, or cancelled)."""
        return self.status in (
            OptimizationStatus.COMPLETED.value,
            OptimizationStatus.FAILED.value,
            OptimizationStatus.CANCELLED.value,
        )

    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate job duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    def mark_started(self) -> None:
        """Mark job as started."""
        self.status = OptimizationStatus.RUNNING.value
        self.started_at = datetime.now()

    def mark_completed(
        self,
        route_ids: list[UUID],
        result_summary: dict[str, Any],
        unassigned: Optional[list[UUID]] = None,
    ) -> None:
        """Mark job as completed with results."""
        self.status = OptimizationStatus.COMPLETED.value
        self.completed_at = datetime.now()
        self.route_ids = route_ids
        self.result_summary = result_summary
        self.unassigned_shipment_ids = unassigned

    def mark_failed(self, error_message: str, traceback: Optional[str] = None) -> None:
        """Mark job as failed with error details."""
        self.status = OptimizationStatus.FAILED.value
        self.completed_at = datetime.now()
        self.error_message = error_message
        self.error_traceback = traceback

    def __repr__(self) -> str:
        return (
            f"<OptimizationJob(id={self.id}, status={self.status}, "
            f"date={self.plan_date})>"
        )
