# Labor Hours Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add optional labor hour tracking and compliance as a soft constraint in the OR-Tools solver, with compliance APIs and nightly reconciliation.

**Architecture:** Feature-flagged via `ENABLE_LABOR_DIMENSION` (default off). When on, solver adds a `LaborMinutes` dimension with per-driver soft upper bounds based on remaining daily/weekly capacity. `LaborHoursService` tracks hours and compliance. Nightly Celery task reconciles accumulated totals from ground truth.

**Tech Stack:** FastAPI, SQLAlchemy (async), OR-Tools, Celery, Pydantic v2

---

### Task 1: Add Config Settings

**Files:**
- Modify: `app/core/config.py:113-165`

**Step 1: Add labor settings to Settings class**

Add these fields after the `h3_resolution` block (before Infeasibility Markers):

```python
    # =========================================================================
    # Labor Compliance
    # =========================================================================
    enable_labor_dimension: bool = Field(
        default=False,
        description="Enable labor hour tracking and solver constraints",
    )

    driver_weekly_limit_minutes: int = Field(
        default=2880,
        description="Weekly driver work limit in minutes (48h = Taiwan Labor Standards Act)",
    )

    driver_daily_limit_minutes: int = Field(
        default=720,
        description="Daily driver work limit in minutes (12h including overtime)",
    )

    labor_warning_threshold: float = Field(
        default=0.85,
        description="Warn at this fraction of limit (0.85 = 85%)",
    )
```

**Step 2: Verify settings load**

Run: `python -c "from app.core.config import get_settings; s = get_settings(); print(s.enable_labor_dimension, s.driver_weekly_limit_minutes)"`
Expected: `False 2880`

**Step 3: Commit**

```bash
git add app/core/config.py
git commit -m "feat: add labor compliance settings to config"
```

---

### Task 2: Add Pydantic Schemas for Labor

**Files:**
- Create: `app/schemas/labor.py`

**Step 1: Create labor schemas**

```python
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
```

**Step 2: Commit**

```bash
git add app/schemas/labor.py
git commit -m "feat: add labor compliance Pydantic schemas"
```

---

### Task 3: Implement LaborHoursService (TDD)

**Files:**
- Create: `tests/unit/test_labor_service.py`
- Create: `app/services/labor/__init__.py`
- Create: `app/services/labor/labor_service.py`

**Step 1: Write failing tests**

```python
"""Tests for LaborHoursService."""
import pytest
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.core.config import get_settings


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def mock_driver():
    """Create a mock Driver object."""
    driver = MagicMock()
    driver.id = uuid4()
    driver.name = "Test Driver"
    driver.employee_id = "DRV001"
    driver.accumulated_weekly_minutes = 0
    driver.accumulated_daily_minutes = 0
    driver.is_active = True
    return driver


@pytest.fixture
def mock_route():
    """Create a mock Route object."""
    route = MagicMock()
    route.id = uuid4()
    route.total_duration = 120  # 2 hours
    route.plan_date = date(2026, 3, 4)
    route.planned_departure_at = datetime(2026, 3, 4, 8, 0, tzinfo=timezone.utc)
    return route


@pytest.fixture
def service(mock_session):
    """Create LaborHoursService with mock session."""
    from app.services.labor.labor_service import LaborHoursService
    return LaborHoursService(mock_session)


# ---------------------------------------------------------------------------
# check_compliance
# ---------------------------------------------------------------------------
class TestCheckCompliance:
    async def test_ok_status_when_below_threshold(self, service, mock_session, mock_driver):
        """Driver with low hours should be OK."""
        mock_driver.accumulated_weekly_minutes = 1000
        mock_driver.accumulated_daily_minutes = 200
        mock_session.get = AsyncMock(return_value=mock_driver)

        result = await service.check_compliance(mock_driver.id)

        assert result.status == "OK"
        assert result.weekly_minutes == 1000
        assert result.daily_minutes == 200

    async def test_warning_status_at_85_percent(self, service, mock_session, mock_driver):
        """Driver at 85%+ of weekly limit should be WARNING."""
        mock_driver.accumulated_weekly_minutes = 2500  # 2500/2880 = 86.8%
        mock_driver.accumulated_daily_minutes = 200
        mock_session.get = AsyncMock(return_value=mock_driver)

        result = await service.check_compliance(mock_driver.id)

        assert result.status == "WARNING"

    async def test_violation_status_over_limit(self, service, mock_session, mock_driver):
        """Driver over weekly limit should be VIOLATION."""
        mock_driver.accumulated_weekly_minutes = 3000  # over 2880
        mock_driver.accumulated_daily_minutes = 200
        mock_session.get = AsyncMock(return_value=mock_driver)

        result = await service.check_compliance(mock_driver.id)

        assert result.status == "VIOLATION"

    async def test_daily_violation_overrides_weekly_ok(self, service, mock_session, mock_driver):
        """Daily violation takes precedence even if weekly is OK."""
        mock_driver.accumulated_weekly_minutes = 1000  # weekly OK
        mock_driver.accumulated_daily_minutes = 750    # daily over 720
        mock_session.get = AsyncMock(return_value=mock_driver)

        result = await service.check_compliance(mock_driver.id)

        assert result.status == "VIOLATION"

    async def test_driver_not_found_raises(self, service, mock_session):
        """Non-existent driver should raise ValueError."""
        mock_session.get = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="Driver .* not found"):
            await service.check_compliance(uuid4())


# ---------------------------------------------------------------------------
# record_dispatch
# ---------------------------------------------------------------------------
class TestRecordDispatch:
    @patch("app.services.labor.labor_service.get_settings")
    async def test_record_creates_labor_log(self, mock_get_settings, service, mock_session, mock_driver, mock_route):
        """Recording dispatch should create a DriverLaborLog."""
        settings = get_settings()
        mock_get_settings.return_value = settings
        settings.enable_labor_dimension = True

        mock_session.get = AsyncMock(return_value=mock_driver)
        mock_session.execute = AsyncMock()

        await service.record_dispatch(mock_driver.id, mock_route)

        mock_session.add.assert_called_once()
        mock_session.execute.assert_called_once()  # UPDATE drivers

    @patch("app.services.labor.labor_service.get_settings")
    async def test_record_noop_when_disabled(self, mock_get_settings, service, mock_session, mock_driver, mock_route):
        """Recording dispatch should be a no-op when feature is disabled."""
        settings = get_settings()
        mock_get_settings.return_value = settings
        settings.enable_labor_dimension = False

        await service.record_dispatch(mock_driver.id, mock_route)

        mock_session.add.assert_not_called()


# ---------------------------------------------------------------------------
# approve_with_override
# ---------------------------------------------------------------------------
class TestApproveWithOverride:
    @patch("app.services.labor.labor_service.get_settings")
    async def test_override_creates_violation_record(self, mock_get_settings, service, mock_session, mock_driver, mock_route):
        """Override should create LaborViolation and still record dispatch."""
        settings = get_settings()
        mock_get_settings.return_value = settings
        settings.enable_labor_dimension = True

        mock_driver.accumulated_weekly_minutes = 2800
        mock_session.get = AsyncMock(return_value=mock_driver)
        mock_session.execute = AsyncMock()

        user_id = uuid4()
        await service.approve_with_override(
            mock_driver.id, mock_route, user_id, "Emergency delivery"
        )

        # Should add both violation and labor log
        assert mock_session.add.call_count == 2
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_labor_service.py -v`
Expected: FAIL (ImportError — module doesn't exist yet)

**Step 3: Create the service**

Create `app/services/labor/__init__.py`:
```python
"""Labor hour tracking services."""
from app.services.labor.labor_service import LaborHoursService

__all__ = ["LaborHoursService"]
```

Create `app/services/labor/labor_service.py`:
```python
"""Labor hour tracking and compliance service."""
from datetime import datetime, timezone
from typing import Optional
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
        statuses = []
        for driver in drivers:
            # Inline the logic to avoid N+1 queries
            settings = get_settings()
            weekly_limit = settings.driver_weekly_limit_minutes
            daily_limit = settings.driver_daily_limit_minutes
            threshold = settings.labor_warning_threshold

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
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_labor_service.py -v`
Expected: All 8 tests PASS

**Step 5: Commit**

```bash
git add app/services/labor/ tests/unit/test_labor_service.py app/schemas/labor.py
git commit -m "feat: add LaborHoursService with compliance checks and dispatch recording"
```

---

### Task 4: Add Labor API Endpoints (TDD)

**Files:**
- Create: `tests/api/test_labor_api.py`
- Create: `app/api/v1/endpoints/labor.py`
- Modify: `app/api/v1/__init__.py`

**Step 1: Write failing API tests**

```python
"""Tests for labor compliance API endpoints."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
def mock_driver():
    driver = MagicMock()
    driver.id = uuid4()
    driver.name = "Test Driver"
    driver.employee_id = "DRV001"
    driver.accumulated_weekly_minutes = 1500
    driver.accumulated_daily_minutes = 300
    driver.is_active = True
    return driver


class TestComplianceEndpoint:
    """GET /api/v1/labor/compliance/{driver_id}"""

    @patch("app.api.v1.endpoints.labor.get_settings")
    async def test_returns_disabled_when_flag_off(self, mock_settings, valid_token):
        settings = MagicMock()
        settings.enable_labor_dimension = False
        mock_settings.return_value = settings

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                f"/api/v1/labor/compliance/{uuid4()}",
                headers={"Authorization": f"Bearer {valid_token}"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is False
        assert data["data"] is None

    @patch("app.api.v1.endpoints.labor.get_async_session")
    @patch("app.api.v1.endpoints.labor.get_settings")
    async def test_returns_compliance_when_enabled(
        self, mock_settings, mock_get_session, valid_token, mock_driver
    ):
        settings = MagicMock()
        settings.enable_labor_dimension = True
        settings.driver_weekly_limit_minutes = 2880
        settings.driver_daily_limit_minutes = 720
        settings.labor_warning_threshold = 0.85
        mock_settings.return_value = settings

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_driver)
        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                f"/api/v1/labor/compliance/{mock_driver.id}",
                headers={"Authorization": f"Bearer {valid_token}"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is True
        assert data["data"]["status"] == "OK"


class TestComplianceSummaryEndpoint:
    """GET /api/v1/labor/compliance/summary"""

    @patch("app.api.v1.endpoints.labor.get_settings")
    async def test_returns_disabled_when_flag_off(self, mock_settings, valid_token):
        settings = MagicMock()
        settings.enable_labor_dimension = False
        mock_settings.return_value = settings

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/labor/compliance/summary",
                headers={"Authorization": f"Bearer {valid_token}"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is False


class TestOverrideEndpoint:
    """POST /api/v1/labor/override"""

    @patch("app.api.v1.endpoints.labor.get_settings")
    async def test_returns_disabled_when_flag_off(self, mock_settings, valid_token):
        settings = MagicMock()
        settings.enable_labor_dimension = False
        mock_settings.return_value = settings

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/labor/override",
                headers={"Authorization": f"Bearer {valid_token}"},
                json={
                    "driver_id": str(uuid4()),
                    "route_id": str(uuid4()),
                    "reason": "Emergency delivery required",
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is False
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/api/test_labor_api.py -v`
Expected: FAIL (ImportError)

**Step 3: Create the labor endpoint**

Create `app/api/v1/endpoints/labor.py`:
```python
"""Labor compliance API endpoints."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.core.config import get_settings
from app.core.dependencies import get_current_user
from app.db.database import get_async_session
from app.schemas.labor import (
    LaborComplianceResponse,
    LaborComplianceSummaryResponse,
    LaborOverrideRequest,
    LaborOverrideResponse,
)
from app.services.labor.labor_service import LaborHoursService

router = APIRouter()


@router.get(
    "/compliance/{driver_id}",
    response_model=LaborComplianceResponse,
)
async def get_driver_compliance(
    driver_id: UUID,
    current_user=Depends(get_current_user),
):
    """Get labor compliance status for a driver."""
    settings = get_settings()
    if not settings.enable_labor_dimension:
        return LaborComplianceResponse(enabled=False, data=None)

    async with get_async_session() as session:
        service = LaborHoursService(session)
        try:
            status = await service.check_compliance(driver_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        return LaborComplianceResponse(enabled=True, data=status)


@router.get(
    "/compliance/summary",
    response_model=LaborComplianceSummaryResponse,
)
async def get_compliance_summary(
    current_user=Depends(get_current_user),
):
    """Get labor compliance summary for all active drivers."""
    settings = get_settings()
    if not settings.enable_labor_dimension:
        return LaborComplianceSummaryResponse(enabled=False, data=None)

    async with get_async_session() as session:
        service = LaborHoursService(session)
        statuses = await service.check_all_compliance()
        return LaborComplianceSummaryResponse(enabled=True, data=statuses)


@router.post(
    "/override",
    response_model=LaborOverrideResponse,
)
async def override_labor_violation(
    request: LaborOverrideRequest,
    current_user=Depends(get_current_user),
):
    """Override a labor violation with audit trail."""
    settings = get_settings()
    if not settings.enable_labor_dimension:
        return LaborOverrideResponse(
            enabled=False, violation_id=None, message="Labor tracking is disabled"
        )

    async with get_async_session() as session:
        service = LaborHoursService(session)
        try:
            route = await session.get(
                __import__("app.models.route", fromlist=["Route"]).Route,
                request.route_id,
            )
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
```

**Step 4: Register the router in `app/api/v1/__init__.py`**

Add after the recommendation router:
```python
from app.api.v1.endpoints import auth, depots, vehicles, shipments, routes, optimization, geocoding, import_excel, insertion, recommendation, labor
```

And add:
```python
api_router.include_router(
    labor.router,
    prefix="/labor",
    tags=["Labor Compliance"],
)
```

**Step 5: Run tests to verify they pass**

Run: `pytest tests/api/test_labor_api.py -v`
Expected: All 4 tests PASS

**Step 6: Commit**

```bash
git add app/api/v1/endpoints/labor.py app/api/v1/__init__.py tests/api/test_labor_api.py
git commit -m "feat: add labor compliance API endpoints"
```

---

### Task 5: Solver Labor Dimension (TDD)

**Files:**
- Create: `tests/solver/test_labor_dimension.py`
- Modify: `app/services/solver/solver.py`
- Modify: `app/services/solver/data_model.py`

**Step 1: Add `driver_labor_cache` to VRPDataModel**

In `app/services/solver/data_model.py`, add field to `VRPDataModel`:
```python
    # Labor tracking (driver_id -> accumulated weekly minutes)
    driver_weekly_cache: dict[str, int] = field(default_factory=dict)
    driver_daily_cache: dict[str, int] = field(default_factory=dict)
```

**Step 2: Write failing solver tests**

```python
"""Tests for labor dimension in solver."""
import pytest
from app.services.solver.data_model import (
    VRPDataModel, LocationNode, VehicleData,
    compute_distance_matrix, compute_time_matrix,
)
from app.services.solver.solver import ColdChainVRPSolver


def _build_test_model(
    num_shipments: int = 6,
    num_vehicles: int = 2,
    driver_weekly_cache: dict | None = None,
    driver_daily_cache: dict | None = None,
    enable_labor: bool = True,
) -> VRPDataModel:
    """Build a small test model for labor dimension tests."""
    nodes = [
        LocationNode(
            index=0, latitude=25.033, longitude=121.565,
            address="Depot", time_windows=[(0, 1440)], service_duration=0,
        )
    ]
    # Create shipments spread around depot
    offsets = [
        (0.01, 0.01), (0.02, 0.01), (0.01, 0.02),
        (-0.01, 0.01), (-0.02, 0.01), (-0.01, 0.02),
    ]
    for i in range(num_shipments):
        dy, dx = offsets[i % len(offsets)]
        nodes.append(LocationNode(
            index=i + 1,
            latitude=25.033 + dy,
            longitude=121.565 + dx,
            address=f"Stop {i+1}",
            shipment_id=f"SHP-{i+1:03d}",
            time_windows=[(360, 1080)],  # 06:00-18:00
            service_duration=15,
            demand_weight=10.0,
            demand_volume=0.1,
            temp_limit_upper=5.0,
            is_strict_sla=False,
            priority=50,
        ))

    vehicles_list = []
    for i in range(num_vehicles):
        vehicles_list.append(VehicleData(
            index=i,
            vehicle_id=f"V-{i+1}",
            license_plate=f"TEST-{i+1}",
            capacity_weight=1000.0,
            capacity_volume=10.0,
            k_value=0.05,
            door_coefficient=0.8,
            has_strip_curtains=False,
            cooling_rate=-2.5,
            initial_temp=-5.0,
            driver_id=f"DRV-{i+1}",
            driver_name=f"Driver {i+1}",
        ))

    model = VRPDataModel(
        nodes=nodes,
        vehicles=vehicles_list,
        ambient_temperature=30.0,
        time_limit_seconds=30,
        vehicle_fixed_cost=50000,
        infeasible_cost=10000000,
        earliest_departure_minutes=360,
        driver_weekly_cache=driver_weekly_cache or {},
        driver_daily_cache=driver_daily_cache or {},
    )
    model.distance_matrix = compute_distance_matrix(model.nodes)
    model.time_matrix = compute_time_matrix(model.nodes, model.distance_matrix)
    return model


@pytest.mark.solver
class TestLaborDimension:
    """Tests for labor dimension in solver (uses real OR-Tools)."""

    def test_solver_works_without_labor_dimension(self):
        """Solver should work normally when labor is disabled."""
        model = _build_test_model(enable_labor=False)
        solver = ColdChainVRPSolver(model)
        result = solver.solve()
        assert result.is_success
        assert result.shipments_assigned > 0

    def test_solver_works_with_labor_dimension_no_limits(self):
        """Solver with labor enabled but no accumulated hours should work normally."""
        model = _build_test_model(enable_labor=True)
        solver = ColdChainVRPSolver(model, enable_labor=True)
        result = solver.solve()
        assert result.is_success
        assert result.shipments_assigned > 0

    def test_driver_near_limit_gets_fewer_stops(self):
        """Driver at 95% weekly limit should get fewer stops than fresh driver."""
        model = _build_test_model(
            num_shipments=6,
            num_vehicles=2,
            driver_weekly_cache={"DRV-1": 2740, "DRV-2": 0},  # DRV-1 at 95%
            driver_daily_cache={"DRV-1": 600, "DRV-2": 0},    # DRV-1 near daily too
        )
        solver = ColdChainVRPSolver(model, enable_labor=True)
        result = solver.solve()

        assert result.is_success
        # Find stops per driver
        drv1_stops = sum(r.num_stops for r in result.routes if r.driver_id == "DRV-1")
        drv2_stops = sum(r.num_stops for r in result.routes if r.driver_id == "DRV-2")

        # DRV-2 (fresh) should handle more stops than DRV-1 (near limit)
        assert drv2_stops >= drv1_stops

    def test_all_drivers_at_limit_still_produces_solution(self):
        """Even if all drivers are over limit, solver should still produce a solution (soft constraint)."""
        model = _build_test_model(
            num_shipments=4,
            num_vehicles=2,
            driver_weekly_cache={"DRV-1": 3000, "DRV-2": 3000},  # Both over limit
            driver_daily_cache={"DRV-1": 700, "DRV-2": 700},
        )
        solver = ColdChainVRPSolver(model, enable_labor=True)
        result = solver.solve()

        # Must still produce a solution (soft constraint, not hard)
        assert result.is_success
        assert result.shipments_assigned > 0

    def test_labor_penalty_less_than_infeasible_cost(self):
        """Labor penalty should be less than infeasible_cost so solver never refuses."""
        model = _build_test_model()
        solver = ColdChainVRPSolver(model, enable_labor=True)
        penalty = solver._calculate_labor_penalty()
        assert penalty < model.infeasible_cost
        assert penalty >= model.vehicle_fixed_cost
```

**Step 3: Run tests to verify they fail**

Run: `pytest tests/solver/test_labor_dimension.py -v`
Expected: FAIL (solver doesn't accept `enable_labor` yet)

**Step 4: Implement labor dimension in solver**

Modify `app/services/solver/solver.py`:

1. Update `__init__` to accept `enable_labor`:
```python
    def __init__(
        self,
        data: VRPDataModel,
        plan_date: Optional[date] = None,
        enable_labor: bool = False,
    ):
        self.data = data
        self.plan_date = plan_date or date.today()
        self.enable_labor = enable_labor
        self.manager = None
        self.routing = None
        self.temp_tracker = None
        self.result: Optional[SolverResult] = None
```

2. Add `_add_labor_dimension()` call in `solve()` after `_add_disjunctions_for_optional_nodes()`:
```python
        # Add labor constraints (optional)
        if self.enable_labor:
            self._add_labor_dimension()
```

3. Add the labor dimension methods:
```python
    def _add_labor_dimension(self):
        """Add labor hours as a soft-capped dimension to the routing model."""
        from app.core.config import get_settings
        settings = get_settings()

        def labor_transit_callback(from_index, to_index):
            """Returns estimated work minutes for traveling from_index -> to_index."""
            from_node = self.manager.IndexToNode(from_index)
            to_node = self.manager.IndexToNode(to_index)
            travel_minutes = self.data.time_matrix[from_node][to_node]
            service_minutes = (
                self.data.nodes[to_node].service_duration
                if to_node != self.data.depot_index
                else 0
            )
            return travel_minutes + service_minutes

        transit_callback_index = self.routing.RegisterTransitCallback(
            labor_transit_callback
        )

        # Add dimension: tracks cumulative work minutes per vehicle
        self.routing.AddDimension(
            transit_callback_index,
            0,           # no slack (work time is always counted)
            1440,        # max 24h hard cap per route (safety net)
            True,        # start cumul to zero
            "LaborMinutes",
        )

        labor_dimension = self.routing.GetDimensionOrDie("LaborMinutes")
        weekly_limit = settings.driver_weekly_limit_minutes
        daily_limit = settings.driver_daily_limit_minutes
        penalty = self._calculate_labor_penalty()

        for vehicle_idx, vehicle_data in enumerate(self.data.vehicles):
            driver_id = vehicle_data.driver_id
            remaining_weekly = max(
                0,
                weekly_limit - self.data.driver_weekly_cache.get(driver_id, 0),
            )
            remaining_daily = max(
                0,
                daily_limit - self.data.driver_daily_cache.get(driver_id, 0),
            )
            effective_limit = min(remaining_daily, remaining_weekly)

            end_index = self.routing.End(vehicle_idx)
            labor_dimension.SetCumulVarSoftUpperBound(
                end_index,
                int(effective_limit),
                penalty,
            )

    def _calculate_labor_penalty(self) -> int:
        """Dynamic penalty that scales with problem size but stays below infeasible_cost."""
        max_distance = 0
        if self.data.distance_matrix:
            for row in self.data.distance_matrix:
                for val in row:
                    if val > max_distance:
                        max_distance = val
        return max(self.data.vehicle_fixed_cost, max_distance)
```

**Step 5: Run tests to verify they pass**

Run: `pytest tests/solver/test_labor_dimension.py -v`
Expected: All 5 tests PASS

**Step 6: Commit**

```bash
git add app/services/solver/solver.py app/services/solver/data_model.py tests/solver/test_labor_dimension.py
git commit -m "feat: add LaborMinutes dimension to OR-Tools solver (soft constraint)"
```

---

### Task 6: Wire Solver Labor Into Celery Task

**Files:**
- Modify: `app/services/tasks.py`

**Step 1: Load driver labor caches before solving**

In `run_optimization()`, after loading vehicles and before building the VRP data model, add:

```python
            # Load driver labor caches if labor dimension is enabled
            driver_weekly_cache = {}
            driver_daily_cache = {}
            enable_labor = settings.enable_labor_dimension
            if enable_labor:
                driver_weekly_cache, driver_daily_cache = _load_driver_labor_caches(
                    session, vehicles
                )
```

Pass them to `build_vrp_data_model` — but since `build_vrp_data_model` doesn't accept them, set them on the model after:

```python
            data_model.driver_weekly_cache = driver_weekly_cache
            data_model.driver_daily_cache = driver_daily_cache
```

Pass `enable_labor` to the solver:
```python
                solver = ColdChainVRPSolver(data_model, plan_date, enable_labor=enable_labor)
```

**Step 2: Add `_load_driver_labor_caches` helper**

```python
def _load_driver_labor_caches(
    session: Session,
    vehicles: list[dict],
) -> tuple[dict[str, int], dict[str, int]]:
    """Load accumulated weekly/daily minutes for drivers assigned to vehicles."""
    from app.models.driver import Driver

    driver_ids = [v["driver_id"] for v in vehicles if v.get("driver_id")]
    if not driver_ids:
        return {}, {}

    result = session.execute(
        select(Driver.id, Driver.accumulated_weekly_minutes, Driver.accumulated_daily_minutes)
        .where(Driver.id.in_([UUID(did) for did in driver_ids]))
    )
    rows = result.all()

    weekly = {str(row[0]): row[1] for row in rows}
    daily = {str(row[0]): row[2] for row in rows}
    return weekly, daily
```

**Step 3: Run existing solver tests to verify nothing broke**

Run: `pytest tests/solver/ -v`
Expected: All solver tests PASS

**Step 4: Commit**

```bash
git add app/services/tasks.py
git commit -m "feat: wire labor dimension into Celery optimization task"
```

---

### Task 7: Nightly Reconciliation Celery Task (TDD)

**Files:**
- Create: `tests/unit/test_labor_reconciliation.py`
- Modify: `app/services/tasks.py`

**Step 1: Write failing test**

```python
"""Tests for labor reconciliation Celery task."""
import pytest
from datetime import date, timedelta
from unittest.mock import patch, MagicMock
from uuid import uuid4


class TestReconcileLaborHours:
    @patch("app.services.tasks.sync_engine")
    @patch("app.services.tasks.get_settings")
    def test_early_return_when_disabled(self, mock_settings, mock_engine):
        """Reconciliation should do nothing when labor is disabled."""
        settings = MagicMock()
        settings.enable_labor_dimension = False
        mock_settings.return_value = settings

        from app.services.tasks import reconcile_labor_hours
        result = reconcile_labor_hours()

        assert result == {"status": "skipped", "reason": "labor dimension disabled"}
        mock_engine.connect.assert_not_called()

    @patch("app.services.tasks.Session")
    @patch("app.services.tasks.sync_engine")
    @patch("app.services.tasks.get_settings")
    def test_reconciliation_runs_when_enabled(self, mock_settings, mock_engine, mock_session_cls):
        """Reconciliation should execute SQL when labor is enabled."""
        settings = MagicMock()
        settings.enable_labor_dimension = True
        settings.driver_weekly_limit_minutes = 2880
        mock_settings.return_value = settings

        mock_session = MagicMock()
        mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)

        from app.services.tasks import reconcile_labor_hours
        result = reconcile_labor_hours()

        assert result["status"] == "completed"
        mock_session.execute.assert_called()
        mock_session.commit.assert_called()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_labor_reconciliation.py -v`
Expected: FAIL (function doesn't exist)

**Step 3: Add reconciliation task to tasks.py**

```python
@celery_app.task(
    bind=True,
    name="app.services.tasks.reconcile_labor_hours",
    queue="default",
    soft_time_limit=1200,
)
def reconcile_labor_hours(self=None) -> dict:
    """
    Nightly job: Recalculate accumulated minutes from ground truth
    (driver_labor_logs) and fix any drift from transactional updates.
    """
    from app.core.config import get_settings
    settings = get_settings()

    if not settings.enable_labor_dimension:
        return {"status": "skipped", "reason": "labor dimension disabled"}

    today = date.today()
    week_start = today - timedelta(days=today.weekday())  # Monday

    with Session(sync_engine) as session:
        from sqlalchemy import text

        # Reconcile weekly totals from labor logs
        session.execute(text("""
            UPDATE drivers d
            SET accumulated_weekly_minutes = COALESCE(agg.total, 0),
                accumulated_daily_minutes = COALESCE(daily.total, 0),
                weekly_reset_at = CASE
                    WHEN d.weekly_reset_at IS NULL OR d.weekly_reset_at < :week_start
                    THEN :week_start
                    ELSE d.weekly_reset_at
                END
            FROM (
                SELECT driver_id, SUM(drive_time_minutes + service_time_minutes) AS total
                FROM driver_labor_logs
                WHERE log_date >= :week_start
                GROUP BY driver_id
            ) agg
            LEFT JOIN (
                SELECT driver_id, SUM(drive_time_minutes + service_time_minutes) AS total
                FROM driver_labor_logs
                WHERE log_date = :today
                GROUP BY driver_id
            ) daily ON daily.driver_id = agg.driver_id
            WHERE d.id = agg.driver_id
        """), {"week_start": week_start, "today": today})

        # Reset drivers with no logs this week
        session.execute(text("""
            UPDATE drivers
            SET accumulated_weekly_minutes = 0,
                accumulated_daily_minutes = 0
            WHERE id NOT IN (
                SELECT DISTINCT driver_id
                FROM driver_labor_logs
                WHERE log_date >= :week_start
            )
        """), {"week_start": week_start})

        session.commit()

    return {"status": "completed", "week_start": str(week_start)}
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_labor_reconciliation.py -v`
Expected: All 2 tests PASS

**Step 5: Run full test suite**

Run: `pytest -v`
Expected: All tests PASS (existing + new)

**Step 6: Commit**

```bash
git add app/services/tasks.py tests/unit/test_labor_reconciliation.py
git commit -m "feat: add nightly labor hours reconciliation Celery task"
```

---

### Task 8: Run Full Test Suite and Update Docs

**Files:**
- Modify: `CLAUDE.md` (test count and coverage)
- Modify: `TODO.md` (mark Step 5 items complete)

**Step 1: Run full test suite with coverage**

Run: `pytest --tb=short`
Expected: All tests PASS, coverage maintained at 76%+

**Step 2: Update TODO.md**

Mark all Step 5 items as `[x]` complete.

**Step 3: Update CLAUDE.md**

Update test counts, add new test files to the infrastructure table, add labor endpoints to API section.

**Step 4: Commit**

```bash
git add CLAUDE.md TODO.md
git commit -m "docs: update TODO and CLAUDE.md for Step 5 labor hours completion"
```

---

**Plan complete and saved to `docs/plans/2026-03-04-labor-hours.md`. Two execution options:**

**1. Subagent-Driven (this session)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** — Open new session with executing-plans, batch execution with checkpoints

Which approach?