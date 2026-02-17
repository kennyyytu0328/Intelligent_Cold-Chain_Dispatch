"""Unit tests for RecommendationService."""
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.recommendation.service import RecommendationService
from app.services.recommendation.exceptions import (
    InsufficientDataException,
    InvalidRouteSignatureException,
)


ROUTE_ID = uuid4()
VEHICLE_ID_1 = uuid4()
VEHICLE_ID_2 = uuid4()
VEHICLE_ID_3 = uuid4()
VEHICLE_ID_4 = uuid4()
VEHICLE_ID_5 = uuid4()
USER_ID = uuid4()
DRIVER_ID_1 = uuid4()
DRIVER_ID_2 = uuid4()


def _make_mock_vehicle(vehicle_id, plate="ABC-123", driver_name="Driver A", driver_id=None):
    v = MagicMock()
    v.id = vehicle_id
    v.license_plate = plate
    v.driver_name = driver_name
    v.driver_id = driver_id or uuid4()
    v.status = "AVAILABLE"
    return v


def _make_mock_route(route_id, signature=None):
    r = MagicMock()
    r.id = route_id
    r.route_signature = signature if signature is not None else ["cell_a", "cell_b"]
    r.vehicle_id = None
    r.driver_id = None
    r.driver_name = None
    return r


def _make_affinity_result(score, confidence=0.8):
    return {
        "affinity_score": score,
        "confidence": confidence,
        "cell_details": [
            {"cell": "cell_a", "trip_count": 5, "avg_success": 0.9},
        ],
    }


# =========================================================================
# TestRecommendForRoute
# =========================================================================
class TestRecommendForRoute:
    """Tests for RecommendationService.recommend_for_route."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @patch(
        "app.services.recommendation.service.PatternAnalysisService",
        autospec=True,
    )
    async def test_recommend_success(self, MockPattern, mock_session):
        """Ranks vehicles by affinity and returns top_k results."""
        mock_route = _make_mock_route(ROUTE_ID, ["cell_a", "cell_b"])
        vehicle_1 = _make_mock_vehicle(VEHICLE_ID_1, "AAA-111", "Driver A")
        vehicle_2 = _make_mock_vehicle(VEHICLE_ID_2, "BBB-222", "Driver B")

        # Setup sequential execute calls: route query, then vehicles query
        route_result = MagicMock()
        route_result.scalar_one_or_none.return_value = mock_route

        vehicles_result = MagicMock()
        vehicles_scalars = MagicMock()
        vehicles_scalars.all.return_value = [vehicle_1, vehicle_2]
        vehicles_result.scalars.return_value = vehicles_scalars

        mock_session.execute = AsyncMock(
            side_effect=[route_result, vehicles_result]
        )

        # Pattern analysis returns different scores
        pattern_instance = MockPattern.return_value
        pattern_instance.calculate_vehicle_affinity = AsyncMock(
            side_effect=[
                _make_affinity_result(0.75),
                _make_affinity_result(0.90),
            ]
        )

        svc = RecommendationService(mock_session)
        result = await svc.recommend_for_route(ROUTE_ID, top_k=5)

        assert result["route_id"] == str(ROUTE_ID)
        assert result["route_signature"] == ["cell_a", "cell_b"]
        assert len(result["recommendations"]) == 2
        # Sorted descending by score
        assert result["recommendations"][0]["affinity_score"] == 0.90
        assert result["recommendations"][0]["vehicle_id"] == str(VEHICLE_ID_2)
        assert result["recommendations"][1]["affinity_score"] == 0.75

    @patch(
        "app.services.recommendation.service.PatternAnalysisService",
        autospec=True,
    )
    async def test_route_not_found(self, MockPattern, mock_session):
        """Raises ValueError when route does not exist."""
        route_result = MagicMock()
        route_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=route_result)

        svc = RecommendationService(mock_session)

        with pytest.raises(ValueError, match="not found"):
            await svc.recommend_for_route(ROUTE_ID)

    @patch(
        "app.services.recommendation.service.PatternAnalysisService",
        autospec=True,
    )
    async def test_empty_signature(self, MockPattern, mock_session):
        """Raises InvalidRouteSignatureException for empty signature."""
        mock_route = _make_mock_route(ROUTE_ID, signature=[])

        route_result = MagicMock()
        route_result.scalar_one_or_none.return_value = mock_route
        mock_session.execute = AsyncMock(return_value=route_result)

        svc = RecommendationService(mock_session)

        with pytest.raises(InvalidRouteSignatureException, match="empty"):
            await svc.recommend_for_route(ROUTE_ID)

    @patch(
        "app.services.recommendation.service.PatternAnalysisService",
        autospec=True,
    )
    async def test_null_signature(self, MockPattern, mock_session):
        """Raises InvalidRouteSignatureException for None signature."""
        mock_route = _make_mock_route(ROUTE_ID, signature=None)
        mock_route.route_signature = None

        route_result = MagicMock()
        route_result.scalar_one_or_none.return_value = mock_route
        mock_session.execute = AsyncMock(return_value=route_result)

        svc = RecommendationService(mock_session)

        with pytest.raises(InvalidRouteSignatureException, match="empty"):
            await svc.recommend_for_route(ROUTE_ID)

    @patch(
        "app.services.recommendation.service.PatternAnalysisService",
        autospec=True,
    )
    async def test_no_available_vehicles(self, MockPattern, mock_session):
        """Raises InsufficientDataException when no vehicles are available."""
        mock_route = _make_mock_route(ROUTE_ID)

        route_result = MagicMock()
        route_result.scalar_one_or_none.return_value = mock_route

        vehicles_result = MagicMock()
        vehicles_scalars = MagicMock()
        vehicles_scalars.all.return_value = []
        vehicles_result.scalars.return_value = vehicles_scalars

        mock_session.execute = AsyncMock(
            side_effect=[route_result, vehicles_result]
        )

        svc = RecommendationService(mock_session)

        with pytest.raises(InsufficientDataException, match="No available"):
            await svc.recommend_for_route(ROUTE_ID)


# =========================================================================
# TestRecommendForCoordinates
# =========================================================================
class TestRecommendForCoordinates:
    """Tests for RecommendationService.recommend_for_coordinates."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @patch(
        "app.services.recommendation.service.PatternAnalysisService",
        autospec=True,
    )
    async def test_preview_success(self, MockPattern, mock_session):
        """Decomposes coordinates to cells and ranks vehicles."""
        vehicle_1 = _make_mock_vehicle(VEHICLE_ID_1, "AAA-111", "Driver A")

        vehicles_result = MagicMock()
        vehicles_scalars = MagicMock()
        vehicles_scalars.all.return_value = [vehicle_1]
        vehicles_result.scalars.return_value = vehicles_scalars
        mock_session.execute = AsyncMock(return_value=vehicles_result)

        pattern_instance = MockPattern.return_value
        pattern_instance.decompose_coordinates_to_cells.return_value = [
            "hex_1", "hex_2"
        ]
        pattern_instance.calculate_vehicle_affinity = AsyncMock(
            return_value=_make_affinity_result(0.85)
        )

        svc = RecommendationService(mock_session)
        coords = [(25.0, 121.5), (25.1, 121.6)]
        result = await svc.recommend_for_coordinates(coords, top_k=5)

        assert result["route_id"] is None
        assert result["route_signature"] == ["hex_1", "hex_2"]
        assert len(result["recommendations"]) == 1
        assert result["recommendations"][0]["affinity_score"] == 0.85
        pattern_instance.decompose_coordinates_to_cells.assert_called_once_with(coords)

    @patch(
        "app.services.recommendation.service.PatternAnalysisService",
        autospec=True,
    )
    async def test_preview_with_vehicle_filter(self, MockPattern, mock_session):
        """Passes vehicle_ids filter to _get_available_vehicles."""
        vehicle_1 = _make_mock_vehicle(VEHICLE_ID_1, "AAA-111", "Driver A")

        vehicles_result = MagicMock()
        vehicles_scalars = MagicMock()
        vehicles_scalars.all.return_value = [vehicle_1]
        vehicles_result.scalars.return_value = vehicles_scalars
        mock_session.execute = AsyncMock(return_value=vehicles_result)

        pattern_instance = MockPattern.return_value
        pattern_instance.decompose_coordinates_to_cells.return_value = ["hex_1"]
        pattern_instance.calculate_vehicle_affinity = AsyncMock(
            return_value=_make_affinity_result(0.60)
        )

        svc = RecommendationService(mock_session)
        result = await svc.recommend_for_coordinates(
            coords=[(25.0, 121.5)],
            vehicle_ids=[VEHICLE_ID_1],
            top_k=3,
        )

        assert len(result["recommendations"]) == 1
        assert result["recommendations"][0]["vehicle_id"] == str(VEHICLE_ID_1)

    @patch(
        "app.services.recommendation.service.PatternAnalysisService",
        autospec=True,
    )
    async def test_preview_no_vehicles(self, MockPattern, mock_session):
        """Raises InsufficientDataException when no vehicles match."""
        vehicles_result = MagicMock()
        vehicles_scalars = MagicMock()
        vehicles_scalars.all.return_value = []
        vehicles_result.scalars.return_value = vehicles_scalars
        mock_session.execute = AsyncMock(return_value=vehicles_result)

        pattern_instance = MockPattern.return_value
        pattern_instance.decompose_coordinates_to_cells.return_value = ["hex_1"]

        svc = RecommendationService(mock_session)

        with pytest.raises(InsufficientDataException):
            await svc.recommend_for_coordinates([(25.0, 121.5)])


# =========================================================================
# TestAcceptRecommendation
# =========================================================================
class TestAcceptRecommendation:
    """Tests for RecommendationService.accept_recommendation."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @patch(
        "app.services.recommendation.service.PatternAnalysisService",
        autospec=True,
    )
    async def test_accept_success(self, MockPattern, mock_session):
        """Updates route with vehicle assignment and returns ASSIGNED status."""
        mock_route = _make_mock_route(ROUTE_ID)
        mock_vehicle = _make_mock_vehicle(
            VEHICLE_ID_1, "AAA-111", "Driver A", driver_id=DRIVER_ID_1,
        )

        route_result = MagicMock()
        route_result.scalar_one_or_none.return_value = mock_route

        vehicle_result = MagicMock()
        vehicle_result.scalar_one_or_none.return_value = mock_vehicle

        # execute calls: select route, select vehicle, update route
        update_result = MagicMock()
        mock_session.execute = AsyncMock(
            side_effect=[route_result, vehicle_result, update_result]
        )
        mock_session.flush = AsyncMock()

        svc = RecommendationService(mock_session)
        result = await svc.accept_recommendation(ROUTE_ID, VEHICLE_ID_1, USER_ID)

        assert result["route_id"] == str(ROUTE_ID)
        assert result["vehicle_id"] == str(VEHICLE_ID_1)
        assert result["status"] == "ASSIGNED"
        mock_session.flush.assert_awaited_once()
        # 3 execute calls: select route, select vehicle, update
        assert mock_session.execute.await_count == 3

    @patch(
        "app.services.recommendation.service.PatternAnalysisService",
        autospec=True,
    )
    async def test_accept_route_not_found(self, MockPattern, mock_session):
        """Raises ValueError when route does not exist."""
        route_result = MagicMock()
        route_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=route_result)

        svc = RecommendationService(mock_session)

        with pytest.raises(ValueError, match="Route"):
            await svc.accept_recommendation(ROUTE_ID, VEHICLE_ID_1, USER_ID)

    @patch(
        "app.services.recommendation.service.PatternAnalysisService",
        autospec=True,
    )
    async def test_accept_vehicle_not_found(self, MockPattern, mock_session):
        """Raises ValueError when vehicle does not exist."""
        mock_route = _make_mock_route(ROUTE_ID)

        route_result = MagicMock()
        route_result.scalar_one_or_none.return_value = mock_route

        vehicle_result = MagicMock()
        vehicle_result.scalar_one_or_none.return_value = None

        mock_session.execute = AsyncMock(
            side_effect=[route_result, vehicle_result]
        )

        svc = RecommendationService(mock_session)

        with pytest.raises(ValueError, match="Vehicle"):
            await svc.accept_recommendation(ROUTE_ID, VEHICLE_ID_1, USER_ID)


# =========================================================================
# TestTopKFiltering
# =========================================================================
class TestTopKFiltering:
    """Tests for top_k result limiting."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @patch(
        "app.services.recommendation.service.PatternAnalysisService",
        autospec=True,
    )
    async def test_top_k_limits_results(self, MockPattern, mock_session):
        """Only returns top_k vehicles even when more are available."""
        vehicles = [
            _make_mock_vehicle(VEHICLE_ID_1, "AAA-111", "Driver A"),
            _make_mock_vehicle(VEHICLE_ID_2, "BBB-222", "Driver B"),
            _make_mock_vehicle(VEHICLE_ID_3, "CCC-333", "Driver C"),
            _make_mock_vehicle(VEHICLE_ID_4, "DDD-444", "Driver D"),
            _make_mock_vehicle(VEHICLE_ID_5, "EEE-555", "Driver E"),
        ]
        mock_route = _make_mock_route(ROUTE_ID, ["cell_a"])

        route_result = MagicMock()
        route_result.scalar_one_or_none.return_value = mock_route

        vehicles_result = MagicMock()
        vehicles_scalars = MagicMock()
        vehicles_scalars.all.return_value = vehicles
        vehicles_result.scalars.return_value = vehicles_scalars

        mock_session.execute = AsyncMock(
            side_effect=[route_result, vehicles_result]
        )

        # Each vehicle gets a different score
        scores = [0.50, 0.90, 0.70, 0.30, 0.80]
        pattern_instance = MockPattern.return_value
        pattern_instance.calculate_vehicle_affinity = AsyncMock(
            side_effect=[_make_affinity_result(s) for s in scores]
        )

        svc = RecommendationService(mock_session)
        result = await svc.recommend_for_route(ROUTE_ID, top_k=3)

        recs = result["recommendations"]
        assert len(recs) == 3
        # Top 3 scores: 0.90, 0.80, 0.70 (descending)
        assert recs[0]["affinity_score"] == 0.90
        assert recs[1]["affinity_score"] == 0.80
        assert recs[2]["affinity_score"] == 0.70
