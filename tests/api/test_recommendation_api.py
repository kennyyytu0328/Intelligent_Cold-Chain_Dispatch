"""API tests for Smart Assignment recommendation endpoints."""
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.services.recommendation.exceptions import (
    InsufficientDataException,
    InvalidRouteSignatureException,
)


ROUTE_ID = str(uuid4())
VEHICLE_ID = str(uuid4())


def _mock_recommendation_result(route_id=ROUTE_ID):
    return {
        "route_id": route_id,
        "route_signature": ["cell_a", "cell_b"],
        "recommendations": [
            {
                "vehicle_id": VEHICLE_ID,
                "license_plate": "ABC-1234",
                "driver_name": "Driver A",
                "affinity_score": Decimal("0.850"),
                "confidence": "HIGH",
                "cell_details": [
                    {
                        "h3_index": "cell_a",
                        "affinity": Decimal("0.900"),
                        "sample_size": 15,
                        "weight": Decimal("20"),
                    },
                    {
                        "h3_index": "cell_b",
                        "affinity": Decimal("0.800"),
                        "sample_size": 12,
                        "weight": Decimal("10"),
                    },
                ],
            },
        ],
    }


# --- Tests: GET /recommendations/{route_id} -----------------------------------

class TestRecommendForRoute:
    async def test_recommend_success(self, client):
        """GET /recommendations/{id} returns ranked vehicles."""
        with patch(
            "app.api.v1.endpoints.recommendation.RecommendationService"
        ) as MockSvc:
            instance = MockSvc.return_value
            instance.recommend_for_route = AsyncMock(
                return_value=_mock_recommendation_result()
            )

            resp = await client.get(f"/api/v1/recommendations/{ROUTE_ID}")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["recommendations"]) == 1
        assert data["recommendations"][0]["license_plate"] == "ABC-1234"
        assert data["route_signature"] == ["cell_a", "cell_b"]

    async def test_recommend_route_not_found(self, client):
        """GET /recommendations/{id} returns 404 when route not found."""
        with patch(
            "app.api.v1.endpoints.recommendation.RecommendationService"
        ) as MockSvc:
            instance = MockSvc.return_value
            instance.recommend_for_route = AsyncMock(
                side_effect=ValueError("Route not found")
            )

            resp = await client.get(f"/api/v1/recommendations/{ROUTE_ID}")

        assert resp.status_code == 404

    async def test_recommend_invalid_signature(self, client):
        """GET /recommendations/{id} returns 422 for empty signature."""
        with patch(
            "app.api.v1.endpoints.recommendation.RecommendationService"
        ) as MockSvc:
            instance = MockSvc.return_value
            instance.recommend_for_route = AsyncMock(
                side_effect=InvalidRouteSignatureException("Empty signature")
            )

            resp = await client.get(f"/api/v1/recommendations/{ROUTE_ID}")

        assert resp.status_code == 422

    async def test_recommend_no_vehicles(self, client):
        """GET /recommendations/{id} returns 404 when no vehicles available."""
        with patch(
            "app.api.v1.endpoints.recommendation.RecommendationService"
        ) as MockSvc:
            instance = MockSvc.return_value
            instance.recommend_for_route = AsyncMock(
                side_effect=InsufficientDataException("No available vehicles")
            )

            resp = await client.get(f"/api/v1/recommendations/{ROUTE_ID}")

        assert resp.status_code == 404

    async def test_recommend_requires_auth(self, unauthenticated_client):
        """GET /recommendations/{id} returns 401 without auth."""
        resp = await unauthenticated_client.get(
            f"/api/v1/recommendations/{ROUTE_ID}"
        )
        assert resp.status_code == 401


# --- Tests: POST /recommendations/preview ------------------------------------

class TestPreviewRecommendation:
    async def test_preview_success(self, client):
        """POST /recommendations/preview returns ranked vehicles for coords."""
        with patch(
            "app.api.v1.endpoints.recommendation.RecommendationService"
        ) as MockSvc:
            instance = MockSvc.return_value
            instance.recommend_for_coordinates = AsyncMock(
                return_value=_mock_recommendation_result(route_id=None)
            )

            resp = await client.post(
                "/api/v1/recommendations/preview",
                json={
                    "stop_coordinates": [
                        {"latitude": 25.033, "longitude": 121.565},
                        {"latitude": 25.047, "longitude": 121.517},
                    ],
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["recommendations"]) >= 1

    async def test_preview_no_vehicles(self, client):
        """POST /recommendations/preview returns 404 with no vehicles."""
        with patch(
            "app.api.v1.endpoints.recommendation.RecommendationService"
        ) as MockSvc:
            instance = MockSvc.return_value
            instance.recommend_for_coordinates = AsyncMock(
                side_effect=InsufficientDataException("No available vehicles")
            )

            resp = await client.post(
                "/api/v1/recommendations/preview",
                json={
                    "stop_coordinates": [
                        {"latitude": 25.033, "longitude": 121.565},
                    ],
                },
            )

        assert resp.status_code == 404


# --- Tests: POST /recommendations/{route_id}/accept --------------------------

class TestAcceptRecommendation:
    async def test_accept_success(self, client):
        """POST /recommendations/{id}/accept assigns vehicle to route."""
        with patch(
            "app.api.v1.endpoints.recommendation.RecommendationService"
        ) as MockSvc:
            instance = MockSvc.return_value
            instance.accept_recommendation = AsyncMock(
                return_value={
                    "route_id": ROUTE_ID,
                    "vehicle_id": VEHICLE_ID,
                    "status": "ASSIGNED",
                }
            )

            resp = await client.post(
                f"/api/v1/recommendations/{ROUTE_ID}/accept",
                json={"vehicle_id": VEHICLE_ID},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ASSIGNED"

    async def test_accept_route_not_found(self, client):
        """POST /recommendations/{id}/accept returns 404 if route missing."""
        with patch(
            "app.api.v1.endpoints.recommendation.RecommendationService"
        ) as MockSvc:
            instance = MockSvc.return_value
            instance.accept_recommendation = AsyncMock(
                side_effect=ValueError("Route not found")
            )

            resp = await client.post(
                f"/api/v1/recommendations/{ROUTE_ID}/accept",
                json={"vehicle_id": VEHICLE_ID},
            )

        assert resp.status_code == 404


# --- Tests: POST /recommendations/admin/recalculate --------------------------

class TestRecalculate:
    async def test_recalculate_stub(self, client):
        """POST /recommendations/admin/recalculate returns 202 stub."""
        resp = await client.post("/api/v1/recommendations/admin/recalculate")

        assert resp.status_code == 202
        data = resp.json()
        assert "queued" in data["message"].lower() or "stub" in data["message"].lower()
        assert data["processed_routes"] == 0
