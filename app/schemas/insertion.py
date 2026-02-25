"""
Dynamic Insertion Pydantic schemas (v3.1).

Request/response schemas for real-time order insertion into active routes.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema


class InsertionRequest(BaseSchema):
    """Body for POST /routes/{id}/insert."""

    shipment_id: UUID
    preferred_position: Optional[int] = Field(
        None,
        description="Desired stop position (1-indexed). Auto-picks best if null.",
        ge=1,
    )


class InsertionPreviewRequest(BaseSchema):
    """Body for POST /routes/{id}/insert/preview."""

    shipment_id: UUID


class InsertionCandidate(BaseSchema):
    """A candidate position for inserting a shipment into a route."""

    position: int = Field(..., description="Stop position (1-indexed)", ge=1)
    temp_risk_score: Decimal = Field(
        ...,
        description="Temperature risk score (0.000 = safe, 1.000 = critical)",
        ge=0,
        max_digits=8,
    )
    temp_risk_level: str = Field(
        ...,
        description="Risk tier: GREEN (<0.5), YELLOW (0.5-0.8), RED (>0.8)",
    )
    delay_impact_minutes: int = Field(
        ...,
        description="Additional delay introduced to downstream stops (minutes)",
    )
    extra_distance_meters: int = Field(
        ...,
        description="Additional distance added to route (meters)",
    )


class InsertionResult(BaseSchema):
    """Response for POST /routes/{id}/insert."""

    insertion_id: UUID
    status: str = Field(
        ...,
        description="Outcome: ACCEPTED, REJECTED, or CONFLICT",
    )
    position: int = Field(..., ge=1)
    temp_risk_score: Decimal = Field(..., ge=0, decimal_places=3)
    temp_risk_level: str
    delay_impact_minutes: int
    extra_distance_meters: int
    updated_route_version: int = Field(
        ...,
        description="New route version after insertion (for CAS)",
    )


class InsertionPreviewResponse(BaseSchema):
    """Response for POST /routes/{id}/insert/preview."""

    candidates: list[InsertionCandidate]
    recommended_position: int = Field(
        ...,
        description="Best position based on temp risk + delay trade-off",
        ge=1,
    )
    route_version: int = Field(
        ...,
        description="Current route version (client must send this on insert)",
    )


class InsertionHistoryEntry(BaseSchema):
    """Single entry in insertion history."""

    id: UUID
    route_id: UUID
    shipment_id: UUID
    target_route_version: int
    proposed_position: int
    temp_risk_score: Optional[Decimal]
    delay_impact_minutes: Optional[int]
    extra_distance_meters: Optional[int]
    status: str
    rejection_reason: Optional[str]
    attempted_by: Optional[UUID]
    created_at: datetime
    resolved_at: Optional[datetime]


class InsertionHistoryResponse(BaseSchema):
    """Response for GET /routes/{id}/insertion-history."""

    items: list[InsertionHistoryEntry]
    total: int


class StaleRouteError(BaseSchema):
    """Error schema for 409 Conflict (optimistic locking / CAS failure)."""

    detail: str = Field(
        default="Route has been modified since preview. Please re-fetch and retry.",
    )
    current_version: int = Field(
        ...,
        description="The current route version on the server",
    )
    requested_version: int = Field(
        ...,
        description="The stale version the client attempted to use",
    )
