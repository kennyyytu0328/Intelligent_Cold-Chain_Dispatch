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
# check_all_compliance
# ---------------------------------------------------------------------------
class TestCheckAllCompliance:
    async def test_returns_empty_when_no_drivers(self, service, mock_session):
        """No active drivers should return empty list."""
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=result_mock)

        statuses = await service.check_all_compliance()

        assert statuses == []

    async def test_returns_ok_for_low_utilization_driver(self, service, mock_session, mock_driver):
        """Driver well below limits should be OK."""
        mock_driver.accumulated_weekly_minutes = 500
        mock_driver.accumulated_daily_minutes = 100
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [mock_driver]
        mock_session.execute = AsyncMock(return_value=result_mock)

        statuses = await service.check_all_compliance()

        assert len(statuses) == 1
        assert statuses[0].status == "OK"
        assert statuses[0].driver_id == mock_driver.id

    async def test_returns_violation_for_over_limit_driver(self, service, mock_session, mock_driver):
        """Driver over weekly limit should be VIOLATION."""
        mock_driver.accumulated_weekly_minutes = 3000  # over 2880
        mock_driver.accumulated_daily_minutes = 200
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [mock_driver]
        mock_session.execute = AsyncMock(return_value=result_mock)

        statuses = await service.check_all_compliance()

        assert statuses[0].status == "VIOLATION"

    async def test_returns_mixed_statuses_for_multiple_drivers(self, service, mock_session):
        """Multiple drivers should each get correct status."""
        driver_ok = MagicMock()
        driver_ok.id = uuid4()
        driver_ok.name = "OK Driver"
        driver_ok.employee_id = "DRV001"
        driver_ok.accumulated_weekly_minutes = 500
        driver_ok.accumulated_daily_minutes = 100

        driver_warning = MagicMock()
        driver_warning.id = uuid4()
        driver_warning.name = "Warning Driver"
        driver_warning.employee_id = "DRV002"
        driver_warning.accumulated_weekly_minutes = 2500  # 86.8%
        driver_warning.accumulated_daily_minutes = 200

        driver_violation = MagicMock()
        driver_violation.id = uuid4()
        driver_violation.name = "Violation Driver"
        driver_violation.employee_id = "DRV003"
        driver_violation.accumulated_weekly_minutes = 3000  # over limit
        driver_violation.accumulated_daily_minutes = 200

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [driver_ok, driver_warning, driver_violation]
        mock_session.execute = AsyncMock(return_value=result_mock)

        statuses = await service.check_all_compliance()

        assert len(statuses) == 3
        by_id = {str(s.driver_id): s.status for s in statuses}
        assert by_id[str(driver_ok.id)] == "OK"
        assert by_id[str(driver_warning.id)] == "WARNING"
        assert by_id[str(driver_violation.id)] == "VIOLATION"


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

    @patch("app.services.labor.labor_service.get_settings")
    async def test_override_raises_when_driver_not_found(self, mock_get_settings, service, mock_session, mock_route):
        """Override should raise ValueError when driver not found."""
        settings = get_settings()
        mock_get_settings.return_value = settings
        mock_session.get = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="Driver .* not found"):
            await service.approve_with_override(uuid4(), mock_route, uuid4(), "Emergency")
