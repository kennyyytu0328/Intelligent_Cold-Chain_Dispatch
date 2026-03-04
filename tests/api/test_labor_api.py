"""Tests for labor compliance API endpoints."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

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
    async def test_returns_disabled_when_flag_off(self, mock_settings, client):
        settings = MagicMock()
        settings.enable_labor_dimension = False
        mock_settings.return_value = settings

        resp = await client.get(f"/api/v1/labor/compliance/{uuid4()}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is False
        assert data["data"] is None

    @patch("app.api.v1.endpoints.labor.get_settings")
    async def test_returns_compliance_when_enabled(
        self, mock_settings, client, mock_session, mock_driver
    ):
        settings = MagicMock()
        settings.enable_labor_dimension = True
        settings.driver_weekly_limit_minutes = 2880
        settings.driver_daily_limit_minutes = 720
        settings.labor_warning_threshold = 0.85
        mock_settings.return_value = settings

        mock_session.get = AsyncMock(return_value=mock_driver)

        resp = await client.get(f"/api/v1/labor/compliance/{mock_driver.id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is True
        assert data["data"]["status"] == "OK"


class TestComplianceSummaryEndpoint:
    """GET /api/v1/labor/compliance/summary"""

    @patch("app.api.v1.endpoints.labor.get_settings")
    async def test_returns_disabled_when_flag_off(self, mock_settings, client):
        settings = MagicMock()
        settings.enable_labor_dimension = False
        mock_settings.return_value = settings

        resp = await client.get("/api/v1/labor/compliance/summary")

        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is False


class TestOverrideEndpoint:
    """POST /api/v1/labor/override"""

    @patch("app.api.v1.endpoints.labor.get_settings")
    async def test_returns_disabled_when_flag_off(self, mock_settings, client):
        settings = MagicMock()
        settings.enable_labor_dimension = False
        mock_settings.return_value = settings

        resp = await client.post(
            "/api/v1/labor/override",
            json={
                "driver_id": str(uuid4()),
                "route_id": str(uuid4()),
                "reason": "Emergency delivery required",
            },
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is False
