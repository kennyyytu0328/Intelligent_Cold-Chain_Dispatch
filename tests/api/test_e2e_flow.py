"""
Full end-to-end flow test:
  import → optimize → insert ad-hoc → check labor → complete route → verify affinities

This test chains real API endpoints in sequence, passing state (job_id, route_id)
from one step to the next, simulating a complete cold-chain dispatch day.

All external dependencies (DB, Celery, Redis) are mocked as in other API tests.
The goal is to exercise the HTTP/service integration layer end-to-end.
"""
from datetime import datetime, date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from tests.api.conftest import make_mock_result


# ─── Shared test data ─────────────────────────────────────────────────────────

PLAN_DATE = "2024-01-30"
DEPOT_LAT = 25.0330
DEPOT_LON = 121.5654


def _make_mock_job(job_id, route_id, status="COMPLETED"):
    job = MagicMock()
    job.id = job_id
    job.celery_task_id = "celery-task-e2e"
    job.status = status
    job.progress = 100 if status == "COMPLETED" else 50
    job.plan_date = date(2024, 1, 30)
    job.vehicle_ids = []
    job.shipment_ids = []
    job.route_ids = [route_id]
    job.unassigned_shipment_ids = []
    job.parameters = {}
    job.result_summary = {
        "routes_created": 1,
        "shipments_assigned": 3,
        "total_distance_km": 42.5,
    }
    job.error_message = None
    job.created_at = datetime(2024, 1, 30, 6, 0, 0)
    job.started_at = datetime(2024, 1, 30, 6, 0, 1)
    job.completed_at = datetime(2024, 1, 30, 6, 5, 0)
    return job


def _make_mock_route(route_id, status="IN_PROGRESS"):
    from app.models.enums import RouteStatus

    route = MagicMock()
    route.id = route_id
    route.status = RouteStatus(status)
    route.route_signature = ["8928308280fffff", "8928308281fffff"]
    route.actual_success_score = None
    return route


def _make_mock_driver(driver_id):
    driver = MagicMock()
    driver.id = driver_id
    driver.name = "E2E Test Driver"
    driver.employee_id = "DRV-E2E"
    driver.accumulated_weekly_minutes = 600
    driver.accumulated_daily_minutes = 120
    driver.is_active = True
    return driver


# ─── E2E Flow Test ────────────────────────────────────────────────────────────

class TestFullE2EFlow:
    """
    Chains 5 API steps in a single test, verifying state flows correctly:

    1. POST /optimization         → job_id
    2. GET  /optimization/{id}    → COMPLETED, route_ids=[route_id]
    3. POST /routes/{id}/insert   → ACCEPTED insertion
    4. GET  /labor/compliance/summary → driver status OK
    5. PATCH /routes/{id}/status  → COMPLETED → affinity triggered
    """

    async def test_full_dispatch_day_chain(self, client, mock_session):
        """
        Simulate a complete dispatch day from job creation to route completion.

        Each step asserts its own response, then passes state to the next step.
        """
        job_id = uuid4()
        route_id = uuid4()
        shipment_id = uuid4()
        driver_id = uuid4()

        # ─── Step 1: Create optimization job ──────────────────────────────────
        # Two scalar calls: vehicle_count=2, shipment_count=3
        mock_session.scalar = AsyncMock(side_effect=[2, 3])

        with patch("app.api.v1.endpoints.optimization.run_optimization") as mock_task:
            mock_celery_result = MagicMock()
            mock_celery_result.id = "celery-task-e2e"
            mock_task.delay.return_value = mock_celery_result

            # Patch uuid4 inside optimization to return predictable job_id
            with patch("app.api.v1.endpoints.optimization.uuid4", return_value=job_id):
                step1_resp = await client.post(
                    "/api/v1/optimization",
                    json={
                        "plan_date": PLAN_DATE,
                        "parameters": {},
                    },
                )

        assert step1_resp.status_code in (200, 202), (
            f"Step 1 failed: {step1_resp.status_code} {step1_resp.text}"
        )
        step1_data = step1_resp.json()
        assert step1_data["status"] == "PENDING"
        assert step1_data["vehicle_count"] == 2
        assert step1_data["shipment_count"] == 3
        mock_task.delay.assert_called_once()

        # ─── Step 2: Poll job status → COMPLETED ──────────────────────────────
        mock_job = _make_mock_job(job_id, route_id, status="COMPLETED")
        mock_session.execute = AsyncMock(
            return_value=make_mock_result(scalar_value=mock_job)
        )

        step2_resp = await client.get(f"/api/v1/optimization/{job_id}")

        assert step2_resp.status_code == 200, (
            f"Step 2 failed: {step2_resp.status_code} {step2_resp.text}"
        )
        step2_data = step2_resp.json()
        assert step2_data["status"] == "COMPLETED"
        assert step2_data["progress"] == 100
        assert len(step2_data["route_ids"]) == 1

        # ─── Step 3: Insert ad-hoc stop into the route ────────────────────────
        insertion_result = {
            "insertion_id": str(uuid4()),
            "status": "ACCEPTED",
            "position": 2,
            "temp_risk_score": Decimal("0.35"),
            "temp_risk_level": "GREEN",
            "delay_impact_minutes": 5,
            "extra_distance_meters": 3200,
            "updated_route_version": 2,
        }

        with patch("app.api.v1.endpoints.insertion.IncrementalInsertionService") as MockSvc:
            instance = MockSvc.return_value
            instance.attempt_insertion = AsyncMock(return_value=insertion_result)

            step3_resp = await client.post(
                f"/api/v1/routes/{route_id}/insert",
                json={"shipment_id": str(shipment_id)},
            )

        assert step3_resp.status_code == 200, (
            f"Step 3 failed: {step3_resp.status_code} {step3_resp.text}"
        )
        step3_data = step3_resp.json()
        assert step3_data["status"] == "ACCEPTED"
        assert step3_data["position"] == 2
        assert step3_data["updated_route_version"] == 2

        # ─── Step 4: Check labor compliance summary ────────────────────────────
        mock_driver = _make_mock_driver(driver_id)
        mock_session.execute = AsyncMock(
            return_value=make_mock_result(scalars_list=[mock_driver])
        )

        with patch("app.api.v1.endpoints.labor.get_settings") as mock_settings_fn:
            settings = MagicMock()
            settings.enable_labor_dimension = True
            settings.driver_weekly_limit_minutes = 2880
            settings.driver_daily_limit_minutes = 720
            settings.labor_warning_threshold = 0.85
            mock_settings_fn.return_value = settings

            step4_resp = await client.get("/api/v1/labor/compliance/summary")

        assert step4_resp.status_code == 200, (
            f"Step 4 failed: {step4_resp.status_code} {step4_resp.text}"
        )
        step4_data = step4_resp.json()
        assert step4_data["enabled"] is True
        # Driver at 600/2880 weekly minutes → should be OK
        assert step4_data["data"][0]["status"] == "OK"
        assert step4_data["data"][0]["weekly_minutes"] == 600

        # ─── Step 5: Complete route → triggers affinity pipeline ──────────────
        mock_route = _make_mock_route(route_id, status="IN_PROGRESS")
        mock_session.execute = AsyncMock(
            return_value=make_mock_result(scalar_value=mock_route)
        )

        with patch("app.api.v1.endpoints.routes.AffinityUpdateService") as MockAffinity:
            affinity_instance = MockAffinity.return_value
            affinity_instance.process_completed_route = AsyncMock()

            step5_resp = await client.patch(
                f"/api/v1/routes/{route_id}/status",
                params={"status": "COMPLETED"},
            )

        assert step5_resp.status_code == 200, (
            f"Step 5 failed: {step5_resp.status_code} {step5_resp.text}"
        )
        step5_data = step5_resp.json()
        assert step5_data["status"] == "COMPLETED"

        # Verify affinity pipeline was triggered exactly once on completion
        MockAffinity.assert_called_once_with(mock_session)
        affinity_instance.process_completed_route.assert_called_once_with(mock_route)


# ─── Individual step unit tests ───────────────────────────────────────────────
# These test each step in isolation for clear failure messages.

class TestE2EStep1CreateJob:
    """POST /optimization → returns PENDING job."""

    async def test_create_job_returns_pending(self, client, mock_session):
        mock_session.scalar = AsyncMock(side_effect=[1, 2])

        with patch("app.api.v1.endpoints.optimization.run_optimization") as mock_task:
            mock_task.delay.return_value = MagicMock(id="task-001")
            resp = await client.post(
                "/api/v1/optimization",
                json={"plan_date": PLAN_DATE, "parameters": {}},
            )

        assert resp.status_code in (200, 202)
        data = resp.json()
        assert data["status"] == "PENDING"
        assert "job_id" in data
        mock_task.delay.assert_called_once()

    async def test_create_job_fails_without_vehicles(self, client, mock_session):
        """No vehicles → 400."""
        mock_session.scalar = AsyncMock(return_value=0)
        resp = await client.post(
            "/api/v1/optimization",
            json={"plan_date": PLAN_DATE, "parameters": {}},
        )
        assert resp.status_code == 400
        assert "vehicle" in resp.json()["detail"].lower()


class TestE2EStep2PollJob:
    """GET /optimization/{job_id} → returns job state."""

    async def test_poll_completed_job(self, client, mock_session):
        job_id = uuid4()
        route_id = uuid4()
        mock_job = _make_mock_job(job_id, route_id)
        mock_session.execute = AsyncMock(return_value=make_mock_result(scalar_value=mock_job))

        resp = await client.get(f"/api/v1/optimization/{job_id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "COMPLETED"
        assert data["progress"] == 100

    async def test_poll_missing_job_returns_404(self, client, mock_session):
        mock_session.execute = AsyncMock(return_value=make_mock_result(scalar_value=None))
        resp = await client.get(f"/api/v1/optimization/{uuid4()}")
        assert resp.status_code == 404


class TestE2EStep3InsertAdHoc:
    """POST /routes/{id}/insert → ACCEPTED insertion."""

    async def test_insert_accepted(self, client):
        route_id = uuid4()
        insertion_result = {
            "insertion_id": str(uuid4()),
            "status": "ACCEPTED",
            "position": 3,
            "temp_risk_score": Decimal("0.25"),
            "temp_risk_level": "GREEN",
            "delay_impact_minutes": 4,
            "extra_distance_meters": 2100,
            "updated_route_version": 5,
        }

        with patch("app.api.v1.endpoints.insertion.IncrementalInsertionService") as MockSvc:
            MockSvc.return_value.attempt_insertion = AsyncMock(return_value=insertion_result)
            resp = await client.post(
                f"/api/v1/routes/{route_id}/insert",
                json={"shipment_id": str(uuid4())},
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "ACCEPTED"


class TestE2EStep4LaborCheck:
    """GET /labor/compliance/summary → driver statuses."""

    @patch("app.api.v1.endpoints.labor.get_settings")
    async def test_summary_returns_ok_drivers(self, mock_settings_fn, client, mock_session):
        settings = MagicMock()
        settings.enable_labor_dimension = True
        settings.driver_weekly_limit_minutes = 2880
        settings.driver_daily_limit_minutes = 720
        settings.labor_warning_threshold = 0.85
        mock_settings_fn.return_value = settings

        driver = _make_mock_driver(uuid4())
        mock_session.execute = AsyncMock(
            return_value=make_mock_result(scalars_list=[driver])
        )

        resp = await client.get("/api/v1/labor/compliance/summary")

        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is True
        assert len(data["data"]) == 1
        assert data["data"][0]["status"] == "OK"

    @patch("app.api.v1.endpoints.labor.get_settings")
    async def test_summary_detects_violation(self, mock_settings_fn, client, mock_session):
        settings = MagicMock()
        settings.enable_labor_dimension = True
        settings.driver_weekly_limit_minutes = 2880
        settings.driver_daily_limit_minutes = 720
        settings.labor_warning_threshold = 0.85
        mock_settings_fn.return_value = settings

        # Driver at 3000 minutes → over weekly limit
        driver = _make_mock_driver(uuid4())
        driver.accumulated_weekly_minutes = 3000
        mock_session.execute = AsyncMock(
            return_value=make_mock_result(scalars_list=[driver])
        )

        resp = await client.get("/api/v1/labor/compliance/summary")

        assert resp.status_code == 200
        data = resp.json()
        assert data["data"][0]["status"] == "VIOLATION"


class TestE2EStep5CompleteAndAffinity:
    """PATCH /routes/{id}/status=COMPLETED → affinity pipeline triggered."""

    async def test_completion_triggers_affinity(self, client, mock_session):
        route_id = uuid4()
        mock_route = _make_mock_route(route_id)
        mock_session.execute = AsyncMock(
            return_value=make_mock_result(scalar_value=mock_route)
        )

        with patch("app.api.v1.endpoints.routes.AffinityUpdateService") as MockAffinity:
            instance = MockAffinity.return_value
            instance.process_completed_route = AsyncMock()

            resp = await client.patch(
                f"/api/v1/routes/{route_id}/status",
                params={"status": "COMPLETED"},
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "COMPLETED"
        instance.process_completed_route.assert_called_once_with(mock_route)

    async def test_non_completion_skips_affinity(self, client, mock_session):
        route_id = uuid4()
        mock_route = _make_mock_route(route_id, status="SCHEDULED")
        mock_session.execute = AsyncMock(
            return_value=make_mock_result(scalar_value=mock_route)
        )

        with patch("app.api.v1.endpoints.routes.AffinityUpdateService") as MockAffinity:
            instance = MockAffinity.return_value
            instance.process_completed_route = AsyncMock()

            resp = await client.patch(
                f"/api/v1/routes/{route_id}/status",
                params={"status": "IN_PROGRESS"},
            )

        assert resp.status_code == 200
        instance.process_completed_route.assert_not_called()
