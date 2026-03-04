"""Labor hour tracking and compliance service."""
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.driver import Driver
from app.models.labor import DriverLaborLog, LaborViolation
from app.schemas.labor import LaborComplianceStatus


class LaborHoursService:
    """Manages driver labor hour tracking and compliance checks."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def check_compliance(self, driver_id: UUID) -> LaborComplianceStatus:
        """Check current compliance status for a driver."""
        settings = get_settings()
        driver = await self.session.get(Driver, driver_id)
        if not driver:
            raise ValueError(f"Driver {driver_id} not found")

        weekly_limit = settings.driver_weekly_limit_minutes
        daily_limit = settings.driver_daily_limit_minutes
        threshold = settings.labor_warning_threshold

        weekly_pct = driver.accumulated_weekly_minutes / weekly_limit if weekly_limit else 0
        daily_pct = driver.accumulated_daily_minutes / daily_limit if daily_limit else 0

        # Determine status: worst of weekly/daily
        if weekly_pct >= 1.0 or daily_pct >= 1.0:
            status = "VIOLATION"
        elif weekly_pct >= threshold or daily_pct >= threshold:
            status = "WARNING"
        else:
            status = "OK"

        return LaborComplianceStatus(
            driver_id=driver.id,
            driver_name=driver.name,
            employee_id=driver.employee_id,
            weekly_minutes=driver.accumulated_weekly_minutes,
            weekly_limit=weekly_limit,
            weekly_utilization=round(weekly_pct, 4),
            daily_minutes=driver.accumulated_daily_minutes,
            daily_limit=daily_limit,
            daily_utilization=round(daily_pct, 4),
            status=status,
        )

    async def check_all_compliance(self) -> list[LaborComplianceStatus]:
        """Check compliance for all active drivers."""
        from sqlalchemy import select
        result = await self.session.execute(
            select(Driver).where(Driver.is_active.is_(True))
        )
        drivers = result.scalars().all()
        settings = get_settings()
        weekly_limit = settings.driver_weekly_limit_minutes
        daily_limit = settings.driver_daily_limit_minutes
        threshold = settings.labor_warning_threshold

        statuses = []
        for driver in drivers:
            weekly_pct = driver.accumulated_weekly_minutes / weekly_limit if weekly_limit else 0
            daily_pct = driver.accumulated_daily_minutes / daily_limit if daily_limit else 0

            if weekly_pct >= 1.0 or daily_pct >= 1.0:
                status = "VIOLATION"
            elif weekly_pct >= threshold or daily_pct >= threshold:
                status = "WARNING"
            else:
                status = "OK"

            statuses.append(LaborComplianceStatus(
                driver_id=driver.id,
                driver_name=driver.name,
                employee_id=driver.employee_id,
                weekly_minutes=driver.accumulated_weekly_minutes,
                weekly_limit=weekly_limit,
                weekly_utilization=round(weekly_pct, 4),
                daily_minutes=driver.accumulated_daily_minutes,
                daily_limit=daily_limit,
                daily_utilization=round(daily_pct, 4),
                status=status,
            ))
        return statuses

    async def record_dispatch(self, driver_id: UUID, route) -> None:
        """Increment accumulated minutes when route is dispatched. No-op if disabled."""
        settings = get_settings()
        if not settings.enable_labor_dimension:
            return

        estimated_minutes = route.total_duration or 0

        # Update driver accumulators
        stmt = (
            update(Driver)
            .where(Driver.id == driver_id)
            .values(
                accumulated_weekly_minutes=Driver.accumulated_weekly_minutes + estimated_minutes,
                accumulated_daily_minutes=Driver.accumulated_daily_minutes + estimated_minutes,
            )
        )
        await self.session.execute(stmt)

        # Create labor log entry
        log = DriverLaborLog(
            driver_id=driver_id,
            route_id=route.id,
            log_date=route.plan_date,
            shift_start=route.planned_departure_at or datetime.now(timezone.utc),
            drive_time_minutes=estimated_minutes,
            source="SYSTEM",
        )
        self.session.add(log)

    async def approve_with_override(
        self,
        driver_id: UUID,
        route,
        user_id: UUID,
        reason: str,
    ) -> LaborViolation:
        """Override a labor violation with audit trail, then record dispatch."""
        settings = get_settings()
        driver = await self.session.get(Driver, driver_id)
        if not driver:
            raise ValueError(f"Driver {driver_id} not found")

        projected = driver.accumulated_weekly_minutes + (route.total_duration or 0)
        weekly_limit = settings.driver_weekly_limit_minutes

        violation = LaborViolation(
            driver_id=driver_id,
            route_id=route.id,
            violation_type="WEEKLY_LIMIT_EXCEEDED",
            severity="VIOLATION",
            projected_minutes=projected,
            limit_minutes=weekly_limit,
            overage_minutes=max(0, projected - weekly_limit),
            was_overridden=True,
            overridden_by=user_id,
            override_reason=reason,
            override_at=datetime.now(timezone.utc),
        )
        self.session.add(violation)

        # Still record the dispatch
        await self.record_dispatch(driver_id, route)

        return violation
