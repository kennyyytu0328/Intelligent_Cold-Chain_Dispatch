"""Labor compliance Pydantic schemas."""
from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema


class LaborComplianceStatus(BaseSchema):
    """Compliance status for a single driver."""
    driver_id: UUID
    driver_name: str
    employee_id: str
    weekly_minutes: int = Field(description="Accumulated weekly work minutes")
    weekly_limit: int = Field(description="Weekly limit in minutes")
    weekly_utilization: float = Field(description="Weekly usage as fraction (0.0-1.0+)")
    daily_minutes: int = Field(description="Accumulated daily work minutes")
    daily_limit: int = Field(description="Daily limit in minutes")
    daily_utilization: float = Field(description="Daily usage as fraction (0.0-1.0+)")
    status: str = Field(description="OK | WARNING | VIOLATION")


class LaborComplianceResponse(BaseSchema):
    """Response wrapper for compliance check."""
    enabled: bool
    data: Optional[LaborComplianceStatus] = None


class LaborComplianceSummaryResponse(BaseSchema):
    """Response wrapper for all-driver compliance summary."""
    enabled: bool
    data: Optional[list[LaborComplianceStatus]] = None


class LaborOverrideRequest(BaseSchema):
    """Request to override a labor violation."""
    driver_id: UUID
    route_id: UUID
    reason: str = Field(..., min_length=5, max_length=500)


class LaborOverrideResponse(BaseSchema):
    """Response after creating a labor override."""
    enabled: bool
    violation_id: Optional[UUID] = None
    message: str


class LaborLogResponse(BaseSchema):
    """Single labor log entry."""
    id: UUID
    driver_id: UUID
    route_id: Optional[UUID]
    log_date: date
    shift_start: datetime
    shift_end: Optional[datetime]
    drive_time_minutes: int
    service_time_minutes: int
    break_time_minutes: int
    total_minutes: Optional[int]
    source: str
