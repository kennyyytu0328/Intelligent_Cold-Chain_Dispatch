"""
Unit tests for Redis caching in PatternAnalysisService.

Verifies cache hit/miss/error behavior using AsyncMock for the Redis client.
All DB operations are also mocked -- no real Redis or PostgreSQL required.
"""
import hashlib
import json
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.recommendation.pattern_analysis import PatternAnalysisService


VEHICLE_ID = uuid4()
CELLS = ["cellA", "cellB"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_cached_payload(score="0.733", confidence="HIGH"):
    payload = {
        "affinity_score": score,
        "confidence": confidence,
        "cell_details": [
            {"h3_index": "cellA", "affinity": "0.800", "sample_size": 15, "weight": "10"},
            {"h3_index": "cellB", "affinity": "0.600", "sample_size": 12, "weight": "5"},
        ],
    }
    return json.dumps(payload)


def _make_service(mock_session, mock_redis=None):
    """Create PatternAnalysisService with mocked geo provider and optional Redis."""
    mock_geo = MagicMock()
    mock_geo.lat_lng_to_cell.side_effect = lambda lat, lng, res: f"cell_{lat}_{lng}"
    mock_geo.cell_to_parent.side_effect = lambda cell, res: f"parent_{cell}"
    with patch(
        "app.services.recommendation.pattern_analysis.get_geo_provider",
        return_value=mock_geo,
    ):
        with patch(
            "app.services.recommendation.pattern_analysis.get_settings"
        ) as mock_settings_fn:
            settings = MagicMock()
            settings.h3_resolution = 7
            settings.affinity_cache_ttl_seconds = 300
            mock_settings_fn.return_value = settings
            svc = PatternAnalysisService(mock_session, redis_client=mock_redis)
    return svc


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_redis():
    client = AsyncMock()
    client.get = AsyncMock(return_value=None)
    client.set = AsyncMock(return_value=True)
    return client


@pytest.fixture
def service_with_redis(mock_session, mock_redis):
    return _make_service(mock_session, mock_redis=mock_redis)


@pytest.fixture
def service_no_redis(mock_session):
    return _make_service(mock_session, mock_redis=None)


# ---------------------------------------------------------------------------
# TestAffinityCacheHit
# ---------------------------------------------------------------------------

class TestAffinityCacheHit:
    async def test_cache_hit_skips_db(self, mock_session, mock_redis):
        """When Redis has a cached result, DB must NOT be queried."""
        mock_redis.get = AsyncMock(return_value=_make_cached_payload())
        svc = _make_service(mock_session, mock_redis=mock_redis)

        await svc.calculate_vehicle_affinity(VEHICLE_ID, CELLS)

        mock_redis.get.assert_awaited_once()
        mock_session.execute.assert_not_awaited()
        mock_session.scalar.assert_not_awaited()

    async def test_cache_hit_returns_correct_data(self, mock_session, mock_redis):
        """Cached data is deserialized and returned with correct types."""
        mock_redis.get = AsyncMock(return_value=_make_cached_payload("0.733", "HIGH"))
        svc = _make_service(mock_session, mock_redis=mock_redis)

        result = await svc.calculate_vehicle_affinity(VEHICLE_ID, CELLS)

        assert result["affinity_score"] == Decimal("0.733")
        assert result["confidence"] == "HIGH"
        assert len(result["cell_details"]) == 2
        assert isinstance(result["affinity_score"], Decimal)
        for cell in result["cell_details"]:
            assert isinstance(cell["affinity"], Decimal)
            assert isinstance(cell["weight"], Decimal)

    async def test_cache_hit_does_not_write_back(self, mock_session, mock_redis):
        """On a cache hit Redis.set should NOT be called."""
        mock_redis.get = AsyncMock(return_value=_make_cached_payload())
        svc = _make_service(mock_session, mock_redis=mock_redis)

        await svc.calculate_vehicle_affinity(VEHICLE_ID, CELLS)

        mock_redis.set.assert_not_awaited()


# ---------------------------------------------------------------------------
# TestAffinityCacheMiss
# ---------------------------------------------------------------------------

class TestAffinityCacheMiss:
    async def test_cache_miss_queries_db_and_stores(self, mock_session, mock_redis):
        """On cache miss, DB is queried and result stored in Redis."""
        mock_redis.get = AsyncMock(return_value=None)
        exec_count = 0

        async def mock_execute(query):
            nonlocal exec_count
            exec_count += 1
            result = MagicMock()
            if exec_count == 1:
                row = MagicMock()
                row.__getitem__ = lambda self, i: [Decimal("0.800"), 15][i]
                result.first.return_value = row
            elif exec_count == 2:
                row = MagicMock()
                row.__getitem__ = lambda self, i: [Decimal("0.600"), 12][i]
                result.first.return_value = row
            else:
                result.first.return_value = None
                result.scalar_one_or_none.return_value = None
            return result

        scalar_count = 0

        async def mock_scalar(query):
            nonlocal scalar_count
            scalar_count += 1
            return 10 if scalar_count == 1 else 5

        mock_session.execute = AsyncMock(side_effect=mock_execute)
        mock_session.scalar = AsyncMock(side_effect=mock_scalar)

        svc = _make_service(mock_session, mock_redis=mock_redis)
        result = await svc.calculate_vehicle_affinity(VEHICLE_ID, CELLS)

        assert mock_session.execute.await_count == 2
        mock_redis.set.assert_awaited_once()
        assert result["affinity_score"] == Decimal("0.733")

    async def test_cache_miss_uses_correct_ttl(self, mock_session, mock_redis):
        """Redis.set is called with the configured TTL."""
        mock_redis.get = AsyncMock(return_value=None)

        async def mock_execute(query):
            result = MagicMock()
            row = MagicMock()
            row.__getitem__ = lambda self, i: [Decimal("0.700"), 15][i]
            result.first.return_value = row
            return result

        mock_session.execute = AsyncMock(side_effect=mock_execute)
        mock_session.scalar = AsyncMock(return_value=5)

        svc = _make_service(mock_session, mock_redis=mock_redis)
        await svc.calculate_vehicle_affinity(VEHICLE_ID, ["cellX"])

        call_kwargs = mock_redis.set.call_args
        assert call_kwargs.kwargs.get("ex") == 300

    async def test_cache_key_format(self, mock_session, mock_redis):
        """Cache key includes vehicle_id and a 12-char hex hash of sorted cells."""
        mock_redis.get = AsyncMock(return_value=None)

        async def mock_execute(query):
            result = MagicMock()
            row = MagicMock()
            row.__getitem__ = lambda self, i: [Decimal("0.700"), 15][i]
            result.first.return_value = row
            return result

        mock_session.execute = AsyncMock(side_effect=mock_execute)
        mock_session.scalar = AsyncMock(return_value=1)

        cells = ["cellA", "cellB"]
        expected_hash = hashlib.md5(":".join(sorted(cells)).encode()).hexdigest()[:12]
        expected_key = f"affinity:{VEHICLE_ID}:{expected_hash}"

        svc = _make_service(mock_session, mock_redis=mock_redis)
        await svc.calculate_vehicle_affinity(VEHICLE_ID, cells)

        mock_redis.get.assert_awaited_once_with(expected_key)
        set_args = mock_redis.set.call_args
        assert set_args.args[0] == expected_key

    async def test_cache_key_is_order_independent(self, mock_session, mock_redis):
        """Cells in different order produce the same cache key."""
        key_ab = PatternAnalysisService._build_cache_key(VEHICLE_ID, ["cellA", "cellB"])
        key_ba = PatternAnalysisService._build_cache_key(VEHICLE_ID, ["cellB", "cellA"])
        assert key_ab == key_ba


# ---------------------------------------------------------------------------
# TestAffinityCacheError
# ---------------------------------------------------------------------------

class TestAffinityCacheError:
    async def test_redis_get_error_falls_through_to_db(self, mock_session, mock_redis):
        """When Redis.get raises an exception, compute from DB normally."""
        mock_redis.get = AsyncMock(side_effect=ConnectionError("Redis down"))

        async def mock_execute(query):
            result = MagicMock()
            row = MagicMock()
            row.__getitem__ = lambda self, i: [Decimal("0.700"), 15][i]
            result.first.return_value = row
            return result

        mock_session.execute = AsyncMock(side_effect=mock_execute)
        mock_session.scalar = AsyncMock(return_value=5)

        svc = _make_service(mock_session, mock_redis=mock_redis)
        result = await svc.calculate_vehicle_affinity(VEHICLE_ID, ["cellX"])

        assert "affinity_score" in result
        assert isinstance(result["affinity_score"], Decimal)
        assert mock_session.execute.await_count >= 1

    async def test_redis_set_error_does_not_crash(self, mock_session, mock_redis):
        """When Redis.set raises, the computed result is still returned."""
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock(side_effect=ConnectionError("Redis down"))

        async def mock_execute(query):
            result = MagicMock()
            row = MagicMock()
            row.__getitem__ = lambda self, i: [Decimal("0.700"), 15][i]
            result.first.return_value = row
            return result

        mock_session.execute = AsyncMock(side_effect=mock_execute)
        mock_session.scalar = AsyncMock(return_value=5)

        svc = _make_service(mock_session, mock_redis=mock_redis)
        result = await svc.calculate_vehicle_affinity(VEHICLE_ID, ["cellX"])

        assert result["affinity_score"] == Decimal("0.700")

    async def test_redis_unavailable_no_crash(self, mock_session):
        """Service works correctly even when redis_client=None."""
        async def mock_execute(query):
            result = MagicMock()
            row = MagicMock()
            row.__getitem__ = lambda self, i: [Decimal("0.800"), 15][i]
            result.first.return_value = row
            return result

        mock_session.execute = AsyncMock(side_effect=mock_execute)
        mock_session.scalar = AsyncMock(return_value=3)

        svc = _make_service(mock_session, mock_redis=None)
        result = await svc.calculate_vehicle_affinity(VEHICLE_ID, ["cellX"])

        assert result["affinity_score"] == Decimal("0.800")
        assert result["confidence"] == "HIGH"


# ---------------------------------------------------------------------------
# TestWithRedisFactory
# ---------------------------------------------------------------------------

class TestWithRedisFactory:
    async def test_with_redis_creates_service_with_client(self, mock_session):
        """with_redis() factory produces a service with Redis configured."""
        fake_client = AsyncMock()

        with patch("app.services.recommendation.pattern_analysis.get_geo_provider", return_value=MagicMock()):
            with patch("app.services.recommendation.pattern_analysis.get_settings") as msf:
                s = MagicMock()
                s.h3_resolution = 7
                s.affinity_cache_ttl_seconds = 300
                msf.return_value = s
                with patch("redis.asyncio.from_url", return_value=fake_client) as mock_from_url:
                    svc = await PatternAnalysisService.with_redis(
                        mock_session, "redis://localhost:6379/0"
                    )
                    mock_from_url.assert_called_once_with(
                        "redis://localhost:6379/0", decode_responses=True
                    )
                    assert svc._redis is fake_client


# ---------------------------------------------------------------------------
# TestSerializationRoundtrip
# ---------------------------------------------------------------------------

class TestSerializationRoundtrip:
    def test_serialize_deserialize_roundtrip(self):
        """Serializing and deserializing a result preserves Decimal values."""
        original = {
            "affinity_score": Decimal("0.733"),
            "confidence": "HIGH",
            "cell_details": [
                {"h3_index": "cellA", "affinity": Decimal("0.800"), "sample_size": 15, "weight": Decimal("10")},
                {"h3_index": "cellB", "affinity": Decimal("0.600"), "sample_size": 12, "weight": Decimal("5")},
            ],
        }
        serialized = PatternAnalysisService._serialize_result(original)
        restored = PatternAnalysisService._deserialize_result(serialized)

        assert restored["affinity_score"] == Decimal("0.733")
        assert restored["confidence"] == "HIGH"
        assert restored["cell_details"][0]["affinity"] == Decimal("0.800")
        assert restored["cell_details"][1]["weight"] == Decimal("5")
        assert isinstance(restored["affinity_score"], Decimal)

    def test_build_cache_key_format(self):
        """Cache key has the correct prefix and 12-char hex hash suffix."""
        vehicle_id = uuid4()
        cells = ["cellX", "cellY"]
        key = PatternAnalysisService._build_cache_key(vehicle_id, cells)
        parts = key.split(":")
        assert parts[0] == "affinity"
        assert str(vehicle_id) in key
        # Last part must be exactly 12 lowercase hex chars
        assert len(parts[-1]) == 12
        assert all(c in "0123456789abcdef" for c in parts[-1])
