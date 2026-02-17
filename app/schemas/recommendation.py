"""
Smart Assignment Pydantic schemas (v3.1).

Request/response schemas for vehicle-route recommendation based on H3 hex affinity.
"""
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema, GeoLocation


class RecommendationPreviewRequest(BaseSchema):
    """Body for POST /recommendations/preview."""

    stop_coordinates: list[GeoLocation] = Field(
        ...,
        description="Delivery stop coordinates to analyze",
        min_length=1,
    )
    vehicle_ids: Optional[list[UUID]] = Field(
        None,
        description="Optional filter: only rank these vehicles",
    )
    top_k: int = Field(
        5,
        description="Maximum number of recommendations to return",
        ge=1,
        le=50,
    )


class CellDetail(BaseSchema):
    """Affinity detail for a single H3 cell."""

    h3_index: str
    affinity: Decimal = Field(..., ge=0, le=1, decimal_places=3)
    sample_size: int = Field(..., ge=0)
    weight: Decimal = Field(..., ge=0)


class VehicleRecommendationItem(BaseSchema):
    """A ranked vehicle recommendation."""

    vehicle_id: UUID
    license_plate: str
    driver_name: Optional[str] = None
    affinity_score: Decimal = Field(
        ...,
        description="Weighted affinity score (0.000-1.000)",
        ge=0,
        le=1,
        decimal_places=3,
    )
    confidence: str = Field(
        ...,
        description="Confidence level: HIGH, MEDIUM, or LOW",
    )
    cell_details: list[CellDetail] = Field(
        default_factory=list,
        description="Per-cell affinity breakdown",
    )


class RecommendationResponse(BaseSchema):
    """Response for GET /{route_id} and POST /preview."""

    route_id: Optional[UUID] = None
    route_signature: list[str] = Field(
        default_factory=list,
        description="H3 cell indices representing route footprint",
    )
    recommendations: list[VehicleRecommendationItem] = Field(
        default_factory=list,
    )


class AcceptRequest(BaseSchema):
    """Body for POST /{route_id}/accept."""

    vehicle_id: UUID


class RecalculateResponse(BaseSchema):
    """Response for POST /admin/recalculate."""

    message: str
    processed_routes: int = 0
    updated_affinities: int = 0
