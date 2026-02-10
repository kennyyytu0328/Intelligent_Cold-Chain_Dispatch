"""Tests for Optimization endpoints."""
import pytest
from datetime import datetime, date
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from tests.api.conftest import make_mock_result


class TestGetJobStatus:

    async def test_not_found_returns_404(self, client, mock_session):
        mock_session.execute = AsyncMock(
            return_value=make_mock_result(scalar_value=None)
        )

        response = await client.get(f"/api/v1/optimization/{uuid4()}")
        assert response.status_code == 404

    async def test_found_returns_200(self, client, mock_session):
        job = MagicMock()
        job.id = uuid4()
        job.celery_task_id = "task-123"
        job.status = "COMPLETED"
        job.progress = 100
        job.plan_date = date(2024, 1, 30)
        job.vehicle_ids = []
        job.shipment_ids = []
        job.route_ids = []
        job.unassigned_shipment_ids = []
        job.parameters = {}
        job.result_summary = {"total_distance_km": 50}
        job.error_message = None
        job.created_at = datetime(2024, 1, 30, 8, 0, 0)
        job.started_at = datetime(2024, 1, 30, 8, 0, 1)
        job.completed_at = datetime(2024, 1, 30, 8, 0, 30)

        mock_session.execute = AsyncMock(
            return_value=make_mock_result(scalar_value=job)
        )

        response = await client.get(f"/api/v1/optimization/{job.id}")
        assert response.status_code == 200
