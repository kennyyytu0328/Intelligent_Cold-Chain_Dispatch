"""Labor compliance API endpoints."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.dependencies import get_current_user
from app.db.database import get_async_session
from app.models.user import User
from app.schemas.labor import (
    LaborComplianceResponse,
    LaborComplianceSummaryResponse,
    LaborOverrideRequest,
    LaborOverrideResponse,
)
from app.services.labor.labor_service import LaborHoursService

router = APIRouter()


@router.get(
    "/compliance/summary",
    response_model=LaborComplianceSummaryResponse,
)
async def get_compliance_summary(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Get labor compliance summary for all active drivers."""
    settings = get_settings()
    if not settings.enable_labor_dimension:
        return LaborComplianceSummaryResponse(enabled=False, data=None)

    service = LaborHoursService(session)
    statuses = await service.check_all_compliance()
    return LaborComplianceSummaryResponse(enabled=True, data=statuses)


@router.get(
    "/compliance/{driver_id}",
    response_model=LaborComplianceResponse,
)
async def get_driver_compliance(
    driver_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Get labor compliance status for a driver."""
    settings = get_settings()
    if not settings.enable_labor_dimension:
        return LaborComplianceResponse(enabled=False, data=None)

    service = LaborHoursService(session)
    try:
        status = await service.check_compliance(driver_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return LaborComplianceResponse(enabled=True, data=status)


@router.post(
    "/override",
    response_model=LaborOverrideResponse,
)
async def override_labor_violation(
    request: LaborOverrideRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Override a labor violation with audit trail."""
    settings = get_settings()
    if not settings.enable_labor_dimension:
        return LaborOverrideResponse(
            enabled=False, violation_id=None, message="Labor tracking is disabled"
        )

    from app.models.route import Route

    service = LaborHoursService(session)
    try:
        route = await session.get(Route, request.route_id)
        if not route:
            raise HTTPException(status_code=404, detail="Route not found")

        violation = await service.approve_with_override(
            request.driver_id, route, current_user.id, request.reason
        )
        await session.commit()
        return LaborOverrideResponse(
            enabled=True,
            violation_id=violation.id,
            message="Override recorded successfully",
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
