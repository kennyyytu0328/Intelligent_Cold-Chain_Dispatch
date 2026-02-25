"""API tests for Dynamic Insertion endpoints."""
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.services.insertion.exceptions import (
    InsertionRejectedException,
    StaleRouteException,
)


ROUTE_ID = str(uuid4())
SHIPMENT_ID = str(uuid4())
INSERTION_ID = str(uuid4())


# ─── Tests: POST /routes/{route_id}/insert ───────────────────────────────────

class TestInsertShipment:
    async def test_insert_success(self, client):
        """POST /routes/{id}/insert returns 200 with insertion result."""
        mock_result = {
            "insertion_id": INSERTION_ID,
            "status": "ACCEPTED",
            "position": 2,
            "temp_risk_score": Decimal("0.35"),
            "temp_risk_level": "GREEN",
            "delay_impact_minutes": 5,
            "extra_distance_meters": 3000,
            "updated_route_version": 4,
        }

        with patch(
            "app.api.v1.endpoints.insertion.IncrementalInsertionService"
        ) as MockSvc:
            instance = MockSvc.return_value
            instance.attempt_insertion = AsyncMock(return_value=mock_result)

            resp = await client.post(
                f"/api/v1/routes/{ROUTE_ID}/insert",
                json={"shipment_id": SHIPMENT_ID},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ACCEPTED"
        assert data["position"] == 2
        assert data["updated_route_version"] == 4

    async def test_insert_conflict_409(self, client):
        """POST /routes/{id}/insert returns 409 on StaleRouteException."""
        with patch(
            "app.api.v1.endpoints.insertion.IncrementalInsertionService"
        ) as MockSvc:
            instance = MockSvc.return_value
            instance.attempt_insertion = AsyncMock(
                side_effect=StaleRouteException(
                    route_id=uuid4(), expected_version=1, current_version=3,
                )
            )

            resp = await client.post(
                f"/api/v1/routes/{ROUTE_ID}/insert",
                json={"shipment_id": SHIPMENT_ID},
            )

        assert resp.status_code == 409
        data = resp.json()
        assert data["detail"]["error"] == "STALE_ROUTE"

    async def test_insert_rejected_422(self, client):
        """POST /routes/{id}/insert returns 422 on InsertionRejectedException."""
        with patch(
            "app.api.v1.endpoints.insertion.IncrementalInsertionService"
        ) as MockSvc:
            instance = MockSvc.return_value
            instance.attempt_insertion = AsyncMock(
                side_effect=InsertionRejectedException(
                    reason="No feasible position", temp_risk_score=0.95,
                )
            )

            resp = await client.post(
                f"/api/v1/routes/{ROUTE_ID}/insert",
                json={"shipment_id": SHIPMENT_ID},
            )

        assert resp.status_code == 422
        data = resp.json()
        assert data["detail"]["error"] == "INSERTION_REJECTED"

    async def test_insert_not_found_404(self, client):
        """POST /routes/{id}/insert returns 404 when route/shipment not found."""
        with patch(
            "app.api.v1.endpoints.insertion.IncrementalInsertionService"
        ) as MockSvc:
            instance = MockSvc.return_value
            instance.attempt_insertion = AsyncMock(
                side_effect=ValueError("Route not found")
            )

            resp = await client.post(
                f"/api/v1/routes/{ROUTE_ID}/insert",
                json={"shipment_id": SHIPMENT_ID},
            )

        assert resp.status_code == 404

    async def test_insert_requires_auth(self, unauthenticated_client):
        """POST /routes/{id}/insert returns 401 without authentication."""
        resp = await unauthenticated_client.post(
            f"/api/v1/routes/{ROUTE_ID}/insert",
            json={"shipment_id": SHIPMENT_ID},
        )
        assert resp.status_code == 401


# ─── Tests: POST /routes/{route_id}/insert/preview ──────────────────────────

class TestPreviewInsertion:
    async def test_preview_success(self, client):
        """POST /routes/{id}/insert/preview returns candidates."""
        mock_result = {
            "candidates": [
                {
                    "position": 1,
                    "temp_risk_score": Decimal("0.3"),
                    "temp_risk_level": "GREEN",
                    "delay_impact_minutes": 3,
                    "extra_distance_meters": 2000,
                },
                {
                    "position": 2,
                    "temp_risk_score": Decimal("0.6"),
                    "temp_risk_level": "YELLOW",
                    "delay_impact_minutes": 8,
                    "extra_distance_meters": 5000,
                },
            ],
            "recommended_position": 1,
            "route_version": 3,
        }

        with patch(
            "app.api.v1.endpoints.insertion.IncrementalInsertionService"
        ) as MockSvc:
            instance = MockSvc.return_value
            instance.preview_insertion = AsyncMock(return_value=mock_result)

            resp = await client.post(
                f"/api/v1/routes/{ROUTE_ID}/insert/preview",
                json={"shipment_id": SHIPMENT_ID},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["candidates"]) == 2
        assert data["recommended_position"] == 1
        assert data["route_version"] == 3


# ─── Tests: GET /routes/{route_id}/insertion-history ─────────────────────────

class TestInsertionHistory:
    async def test_insertion_history(self, client, mock_session):
        """GET /routes/{id}/insertion-history returns list of attempts."""
        from datetime import datetime as dt

        mock_attempt = type("MockAttempt", (), {
            "id": uuid4(),
            "route_id": uuid4(),
            "shipment_id": uuid4(),
            "target_route_version": 1,
            "proposed_position": 2,
            "temp_risk_score": Decimal("0.4"),
            "delay_impact_minutes": 5,
            "extra_distance_meters": 3000,
            "status": "ACCEPTED",
            "rejection_reason": None,
            "attempted_by": uuid4(),
            "created_at": dt(2024, 1, 30, 10, 0),
            "resolved_at": dt(2024, 1, 30, 10, 1),
        })()

        mock_history = {
            "items": [mock_attempt],
            "total": 1,
        }

        with patch(
            "app.api.v1.endpoints.insertion.IncrementalInsertionService"
        ) as MockSvc:
            instance = MockSvc.return_value
            instance.get_insertion_history = AsyncMock(return_value=mock_history)

            resp = await client.get(
                f"/api/v1/routes/{ROUTE_ID}/insertion-history",
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["status"] == "ACCEPTED"
