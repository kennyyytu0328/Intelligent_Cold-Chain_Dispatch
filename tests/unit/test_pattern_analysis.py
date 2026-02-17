"""Unit tests for PatternAnalysisService."""
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.recommendation.pattern_analysis import (
    PatternAnalysisService,
    COLD_START_THRESHOLD,
)
from app.services.recommendation.exceptions import InvalidRouteSignatureException


VEHICLE_ID = uuid4()


@pytest.fixture
def mock_geo():
    """Mock GeoProvider."""
    geo = MagicMock()
    geo.lat_lng_to_cell.side_effect = lambda lat, lng, res: f"cell_{lat}_{lng}"
    geo.cell_to_parent.side_effect = lambda cell, res: f"parent_{cell}"
    return geo


@pytest.fixture
def service(mock_session, mock_geo):
    """PatternAnalysisService with mocked session and geo provider."""
    with patch(
        "app.services.recommendation.pattern_analysis.get_geo_provider",
        return_value=mock_geo,
    ):
        with patch(
            "app.services.recommendation.pattern_analysis.get_settings"
        ) as mock_settings:
            settings = MagicMock()
            settings.h3_resolution = 7
            mock_settings.return_value = settings
            svc = PatternAnalysisService(mock_session)
    return svc


# =========================================================================
# TestDecomposeCoordinatesToCells
# =========================================================================
class TestDecomposeCoordinatesToCells:
    def test_single_coordinate(self, service):
        result = service.decompose_coordinates_to_cells([(25.0, 121.5)])
        assert result == ["cell_25.0_121.5"]

    def test_multiple_coordinates_dedup(self, service):
        coords = [(25.0, 121.5), (25.1, 121.6), (25.0, 121.5)]
        result = service.decompose_coordinates_to_cells(coords)
        assert result == ["cell_25.0_121.5", "cell_25.1_121.6"]

    def test_empty_coordinates(self, service):
        result = service.decompose_coordinates_to_cells([])
        assert result == []


# =========================================================================
# TestCalculateVehicleAffinity
# =========================================================================
class TestCalculateVehicleAffinity:
    async def test_weighted_average_known_values(self, service, mock_session):
        """Two cells with known affinity and weight produce correct weighted avg."""
        vehicle_id = VEHICLE_ID
        cells = ["cellA", "cellB"]

        # cell A: affinity=0.8, sample=15 (high), weight=10
        # cell B: affinity=0.6, sample=12 (high), weight=5
        # expected: (10*0.8 + 5*0.6) / (10+5) = (8+3)/15 = 11/15 = 0.733
        exec_count = 0
        scalar_count = 0

        async def mock_execute(query):
            nonlocal exec_count
            exec_count += 1
            result = MagicMock()

            if exec_count == 1:
                # cellA direct affinity
                row = MagicMock()
                row.__getitem__ = lambda self, i: [Decimal("0.800"), 15][i]
                result.first.return_value = row
            elif exec_count == 2:
                # cellB direct affinity
                row = MagicMock()
                row.__getitem__ = lambda self, i: [Decimal("0.600"), 12][i]
                result.first.return_value = row
            else:
                result.first.return_value = None
                result.scalar_one_or_none.return_value = None

            return result

        async def mock_scalar(query):
            nonlocal scalar_count
            scalar_count += 1
            # _get_cell_weight calls: cellA weight=10, cellB weight=5
            if scalar_count == 1:
                return 10
            elif scalar_count == 2:
                return 5
            return None

        mock_session.execute = AsyncMock(side_effect=mock_execute)
        mock_session.scalar = AsyncMock(side_effect=mock_scalar)

        result = await service.calculate_vehicle_affinity(vehicle_id, cells)

        assert result["affinity_score"] == Decimal("0.733")
        assert result["confidence"] == "HIGH"
        assert len(result["cell_details"]) == 2

    async def test_single_cell_route(self, service, mock_session):
        """Single cell route returns that cell's affinity."""
        vehicle_id = VEHICLE_ID

        async def mock_execute(query):
            result = MagicMock()
            row = MagicMock()
            row.__getitem__ = lambda self, i: [Decimal("0.900"), 20][i]
            result.first.return_value = row
            return result

        mock_session.execute = AsyncMock(side_effect=mock_execute)
        mock_session.scalar = AsyncMock(return_value=5)  # weight

        result = await service.calculate_vehicle_affinity(vehicle_id, ["cellX"])

        assert result["affinity_score"] == Decimal("0.900")
        assert len(result["cell_details"]) == 1

    async def test_empty_cells(self, service):
        """Empty cells list returns default 0.500 LOW."""
        result = await service.calculate_vehicle_affinity(VEHICLE_ID, [])

        assert result["affinity_score"] == Decimal("0.500")
        assert result["confidence"] == "LOW"
        assert result["cell_details"] == []

    async def test_all_cells_no_data(self, service, mock_session):
        """When no affinity data exists anywhere, fallback to 0.500."""
        async def mock_execute(query):
            result = MagicMock()
            result.first.return_value = None
            result.scalar_one_or_none.return_value = None
            return result

        mock_session.execute = AsyncMock(side_effect=mock_execute)
        mock_session.scalar = AsyncMock(return_value=None)

        result = await service.calculate_vehicle_affinity(VEHICLE_ID, ["cellA"])

        assert result["affinity_score"] == Decimal("0.500")
        assert result["confidence"] == "LOW"


# =========================================================================
# TestColdStartFallback
# =========================================================================
class TestColdStartFallback:
    async def test_high_sample_uses_raw(self, service, mock_session):
        """sample_size >= 10 returns raw affinity without blending."""
        async def mock_execute(query):
            result = MagicMock()
            row = MagicMock()
            row.__getitem__ = lambda self, i: [Decimal("0.850"), 15][i]
            result.first.return_value = row
            return result

        mock_session.execute = AsyncMock(side_effect=mock_execute)

        affinity, sample = await service._get_cell_affinity_with_fallback(
            VEHICLE_ID, "cellA"
        )

        assert affinity == Decimal("0.850")
        assert sample == 15

    async def test_low_sample_blends_parent(self, service, mock_session):
        """sample_size < 10 blends with parent cell affinity."""
        # Direct: affinity=0.800, sample=4 -> lambda=0.4
        # Parent: affinity=0.600
        # Blended: 0.4*0.800 + 0.6*0.600 = 0.320 + 0.360 = 0.680
        call_count = 0

        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                # Direct affinity query
                row = MagicMock()
                row.__getitem__ = lambda self, i: [Decimal("0.800"), 4][i]
                result.first.return_value = row
            elif call_count == 2:
                # Parent cell affinity query
                result.scalar_one_or_none.return_value = Decimal("0.600")
            else:
                result.first.return_value = None
                result.scalar_one_or_none.return_value = None
            return result

        call_count = 0
        mock_session.execute = AsyncMock(side_effect=mock_execute)

        affinity, sample = await service._get_cell_affinity_with_fallback(
            VEHICLE_ID, "cellA"
        )

        assert affinity == Decimal("0.680")
        assert sample == 4

    async def test_zero_sample_blends_to_pure_parent(self, service, mock_session):
        """sample_size=0 means lambda=0, pure parent affinity."""
        call_count = 0

        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                # Direct: sample=0
                row = MagicMock()
                row.__getitem__ = lambda self, i: [Decimal("0.100"), 0][i]
                result.first.return_value = row
            elif call_count == 2:
                # Parent
                result.scalar_one_or_none.return_value = Decimal("0.700")
            else:
                result.first.return_value = None
                result.scalar_one_or_none.return_value = None
            return result

        call_count = 0
        mock_session.execute = AsyncMock(side_effect=mock_execute)

        affinity, sample = await service._get_cell_affinity_with_fallback(
            VEHICLE_ID, "cellA"
        )

        # lambda=0, so 0*0.1 + 1*0.7 = 0.7
        assert affinity == Decimal("0.700")
        assert sample == 0

    async def test_no_data_no_parent_uses_global(self, service, mock_session):
        """No direct, no parent -> global vehicle average."""
        async def mock_execute(query):
            result = MagicMock()
            result.first.return_value = None
            result.scalar_one_or_none.return_value = None
            return result

        mock_session.execute = AsyncMock(side_effect=mock_execute)
        mock_session.scalar = AsyncMock(return_value=Decimal("0.650"))

        affinity, sample = await service._get_cell_affinity_with_fallback(
            VEHICLE_ID, "cellA"
        )

        assert affinity == Decimal("0.650")
        assert sample == 0

    async def test_no_data_no_parent_no_global_uses_default(
        self, service, mock_session
    ):
        """Nothing anywhere -> 0.500 default."""
        async def mock_execute(query):
            result = MagicMock()
            result.first.return_value = None
            result.scalar_one_or_none.return_value = None
            return result

        mock_session.execute = AsyncMock(side_effect=mock_execute)
        mock_session.scalar = AsyncMock(return_value=None)

        affinity, sample = await service._get_cell_affinity_with_fallback(
            VEHICLE_ID, "cellA"
        )

        assert affinity == Decimal("0.500")
        assert sample == 0


# =========================================================================
# TestConfidence
# =========================================================================
class TestConfidence:
    def test_high_confidence(self):
        """>=70% cells with sample >= 10 -> HIGH."""
        details = [
            {"sample_size": 15},
            {"sample_size": 12},
            {"sample_size": 20},
            {"sample_size": 2},
        ]
        # 3/4 = 75% >= 70%
        assert PatternAnalysisService._calculate_confidence(details) == "HIGH"

    def test_medium_confidence(self):
        """30-70% cells with sample >= 10 -> MEDIUM."""
        details = [
            {"sample_size": 15},
            {"sample_size": 2},
            {"sample_size": 3},
        ]
        # 1/3 = 33% -> MEDIUM
        assert PatternAnalysisService._calculate_confidence(details) == "MEDIUM"

    def test_low_confidence(self):
        """<30% cells with sample >= 10 -> LOW."""
        details = [
            {"sample_size": 1},
            {"sample_size": 2},
            {"sample_size": 3},
            {"sample_size": 11},
        ]
        # 1/4 = 25% < 30%
        assert PatternAnalysisService._calculate_confidence(details) == "LOW"

    def test_empty_cells_low(self):
        """Empty details -> LOW."""
        assert PatternAnalysisService._calculate_confidence([]) == "LOW"
