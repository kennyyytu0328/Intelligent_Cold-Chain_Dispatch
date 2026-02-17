"""
Smart Assignment API endpoints (v3.1).

Provides vehicle-route recommendation based on historical delivery
performance per H3 hex cell with cold-start fallback.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.database import get_async_session
from app.models.user import User
from app.schemas.recommendation import (
    AcceptRequest,
    RecommendationPreviewRequest,
    RecommendationResponse,
    RecalculateResponse,
    VehicleRecommendationItem,
    CellDetail,
)
from app.services.recommendation import (
    RecommendationService,
    InsufficientDataException,
    InvalidRouteSignatureException,
)

router = APIRouter()


@router.get(
    "/{route_id}",
    response_model=RecommendationResponse,
)
async def recommend_for_route(
    route_id: UUID,
    top_k: int = 5,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Rank vehicles for a route based on hex-cell delivery affinity.

    Returns up to `top_k` vehicle recommendations sorted by affinity score.
    """
    service = RecommendationService(session)

    try:
        result = await service.recommend_for_route(
            route_id=route_id, top_k=top_k
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        )
    except InvalidRouteSignatureException as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc.message),
        )
    except InsufficientDataException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc.message)
        )

    return _build_response(result)


@router.post(
    "/preview",
    response_model=RecommendationResponse,
)
async def preview_recommendation(
    body: RecommendationPreviewRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Preview vehicle ranking for ad-hoc coordinates without a saved route.
    """
    service = RecommendationService(session)

    coords = [(c.latitude, c.longitude) for c in body.stop_coordinates]

    try:
        result = await service.recommend_for_coordinates(
            coords=coords,
            vehicle_ids=body.vehicle_ids,
            top_k=body.top_k,
        )
    except InsufficientDataException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc.message)
        )

    return _build_response(result)


@router.post(
    "/{route_id}/accept",
)
async def accept_recommendation(
    route_id: UUID,
    body: AcceptRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Accept a recommendation and assign the vehicle to the route.
    """
    service = RecommendationService(session)

    try:
        result = await service.accept_recommendation(
            route_id=route_id,
            vehicle_id=body.vehicle_id,
            user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        )

    return result


@router.post(
    "/admin/recalculate",
    response_model=RecalculateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def recalculate_affinities(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Trigger recalculation of vehicle hex affinities (stub).

    In production, this would queue a background Celery task.
    """
    return RecalculateResponse(
        message="Recalculation queued (stub)",
        processed_routes=0,
        updated_affinities=0,
    )


def _build_response(result: dict) -> RecommendationResponse:
    """Convert service result dict to response schema."""
    recommendations = [
        VehicleRecommendationItem(
            vehicle_id=r["vehicle_id"],
            license_plate=r["license_plate"],
            driver_name=r.get("driver_name"),
            affinity_score=r["affinity_score"],
            confidence=r["confidence"],
            cell_details=[CellDetail(**cd) for cd in r.get("cell_details", [])],
        )
        for r in result.get("recommendations", [])
    ]

    return RecommendationResponse(
        route_id=result.get("route_id"),
        route_signature=result.get("route_signature", []),
        recommendations=recommendations,
    )
