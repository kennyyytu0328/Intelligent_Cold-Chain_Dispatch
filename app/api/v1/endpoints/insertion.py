"""
Dynamic Insertion API endpoints (v3.1).

Allows inserting new shipments into active routes with optimistic locking,
temperature risk assessment, and insertion history auditing.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.database import get_async_session
from app.models.user import User
from app.schemas.insertion import (
    InsertionHistoryResponse,
    InsertionHistoryEntry,
    InsertionPreviewRequest,
    InsertionPreviewResponse,
    InsertionCandidate as InsertionCandidateSchema,
    InsertionRequest,
    InsertionResult,
    StaleRouteError,
)
from app.services.insertion import (
    IncrementalInsertionService,
    InsertionRejectedException,
    StaleRouteException,
)

router = APIRouter()


@router.post(
    "/{route_id}/insert",
    response_model=InsertionResult,
    responses={
        409: {"model": StaleRouteError, "description": "Route version conflict"},
        422: {"description": "Insertion rejected (temperature risk too high)"},
    },
)
async def insert_shipment(
    route_id: UUID,
    body: InsertionRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Insert a new shipment into an existing route.

    Uses optimistic locking (CAS) to prevent concurrent modification conflicts.
    The temperature proxy model evaluates thermal safety before applying changes.
    """
    service = IncrementalInsertionService(session)

    try:
        result = await service.attempt_insertion(
            route_id=route_id,
            shipment_id=body.shipment_id,
            user_id=current_user.id,
            preferred_position=body.preferred_position,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except StaleRouteException as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "STALE_ROUTE",
                "message": exc.message,
                "current_version": exc.current_version,
                "requested_version": exc.expected_version,
            },
        )
    except InsertionRejectedException as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "INSERTION_REJECTED",
                "reason": exc.reason,
                "temp_risk_score": exc.temp_risk_score,
            },
        )

    return InsertionResult(**result)


@router.post(
    "/{route_id}/insert/preview",
    response_model=InsertionPreviewResponse,
)
async def preview_insertion(
    route_id: UUID,
    body: InsertionPreviewRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Preview insertion impact without applying changes.

    Returns all candidate positions ranked by extra distance,
    with temperature risk assessment for each.
    """
    service = IncrementalInsertionService(session)

    try:
        result = await service.preview_insertion(
            route_id=route_id,
            shipment_id=body.shipment_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    return InsertionPreviewResponse(
        candidates=[InsertionCandidateSchema(**c) for c in result["candidates"]],
        recommended_position=result["recommended_position"],
        route_version=result["route_version"],
    )


@router.get(
    "/{route_id}/insertion-history",
    response_model=InsertionHistoryResponse,
)
async def get_insertion_history(
    route_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """View past insertion attempts for a route."""
    service = IncrementalInsertionService(session)
    result = await service.get_insertion_history(
        route_id=route_id,
        skip=skip,
        limit=limit,
    )

    return InsertionHistoryResponse(
        items=[
            InsertionHistoryEntry.model_validate(a, from_attributes=True)
            for a in result["items"]
        ],
        total=result["total"],
    )
