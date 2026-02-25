"""API tests for affinity pipeline trigger on route completion."""
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from tests.api.conftest import make_mock_result


ROUTE_ID = uuid4()


def _make_mock_route(route_id=None, status="IN_PROGRESS"):
    """Create a mock Route with the given status."""
    from app.models.enums import RouteStatus

    route = MagicMock()
    route.id = route_id or ROUTE_ID
    route.status = RouteStatus(status)
    return route


class TestAffinityTrigger:
    """Tests for affinity pipeline invocation on route status change."""

    async def test_completion_calls_affinity_service(self, client, mock_session):
        """PATCH status=COMPLETED should invoke AffinityUpdateService."""
        mock_route = _make_mock_route()
        mock_session.execute = AsyncMock(
            return_value=make_mock_result(scalar_value=mock_route)
        )

        with patch(
            "app.api.v1.endpoints.routes.AffinityUpdateService"
        ) as MockSvc:
            instance = MockSvc.return_value
            instance.process_completed_route = AsyncMock()

            resp = await client.patch(
                f"/api/v1/routes/{ROUTE_ID}/status",
                params={"status": "COMPLETED"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "COMPLETED"
        MockSvc.assert_called_once_with(mock_session)
        instance.process_completed_route.assert_called_once_with(mock_route)

    async def test_non_completion_skips_affinity(self, client, mock_session):
        """PATCH status=IN_PROGRESS should NOT invoke AffinityUpdateService."""
        mock_route = _make_mock_route()
        mock_session.execute = AsyncMock(
            return_value=make_mock_result(scalar_value=mock_route)
        )

        with patch(
            "app.api.v1.endpoints.routes.AffinityUpdateService"
        ) as MockSvc:
            instance = MockSvc.return_value
            instance.process_completed_route = AsyncMock()

            resp = await client.patch(
                f"/api/v1/routes/{ROUTE_ID}/status",
                params={"status": "IN_PROGRESS"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "IN_PROGRESS"
        MockSvc.assert_not_called()
        instance.process_completed_route.assert_not_called()
