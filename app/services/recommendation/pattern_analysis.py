"""
Pattern Analysis Service for Smart Assignment (v3.1).

Calculates vehicle-cell affinity using weighted average formula with cold-start fallback.
Supports optional Redis caching for affinity scores (configurable TTL, graceful fallback).
"""
import hashlib
import json
import logging
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.geo import RouteHexStat, VehicleHexAffinity
from app.models.route import Route, RouteStop
from app.services.geo.provider import get_geo_provider
from app.services.recommendation.exceptions import InvalidRouteSignatureException

logger = logging.getLogger(__name__)


# Cold-start blending threshold
COLD_START_THRESHOLD = 10

# Confidence thresholds
HIGH_CONFIDENCE_PCT = 0.70
MEDIUM_CONFIDENCE_PCT = 0.30


class PatternAnalysisService:
    """Analyzes vehicle delivery patterns per H3 hex cell."""

    def __init__(self, session: AsyncSession, redis_client=None):
        self._session = session
        self._settings = get_settings()
        self._geo = get_geo_provider()
        self._resolution = self._settings.h3_resolution
        self._redis = redis_client

    @classmethod
    async def with_redis(
        cls, session: AsyncSession, redis_url: str
    ) -> "PatternAnalysisService":
        """Factory that creates the service with a connected async Redis client.

        Args:
            session: Async DB session.
            redis_url: Redis connection URL.

        Returns:
            PatternAnalysisService instance with Redis caching enabled.
        """
        import redis.asyncio as aioredis

        client = aioredis.from_url(redis_url, decode_responses=True)
        return cls(session=session, redis_client=client)

    async def decompose_route_to_cells(self, route_id: UUID) -> list[str]:
        """Load route stops and convert their locations to H3 cells.

        Args:
            route_id: Route to decompose.

        Returns:
            List of unique H3 cell indices.

        Raises:
            InvalidRouteSignatureException: If route has no signature and no stops.
        """
        # First try route_signature from the Route itself
        route_result = await self._session.execute(
            select(Route).where(Route.id == route_id)
        )
        route = route_result.scalar_one_or_none()
        if route is None:
            raise ValueError(f"Route {route_id} not found")

        if route.route_signature:
            return list(route.route_signature)

        # Fallback: decompose from stops using PostGIS ST_X/ST_Y
        stops_result = await self._session.execute(
            select(
                func.ST_Y(RouteStop.location).label("lat"),
                func.ST_X(RouteStop.location).label("lng"),
            )
            .where(RouteStop.route_id == route_id)
            .order_by(RouteStop.sequence_number)
        )
        rows = stops_result.all()

        if not rows:
            raise InvalidRouteSignatureException(
                f"Route {route_id} has no signature and no stops"
            )

        coords = [(float(row.lat), float(row.lng)) for row in rows]
        return self.decompose_coordinates_to_cells(coords)

    def decompose_coordinates_to_cells(
        self, coords: list[tuple[float, float]]
    ) -> list[str]:
        """Convert coordinate pairs to unique H3 cells.

        Args:
            coords: List of (lat, lng) tuples.

        Returns:
            List of unique H3 cell indices (order preserved, deduplicated).
        """
        seen: set[str] = set()
        cells: list[str] = []
        for lat, lng in coords:
            cell = self._geo.lat_lng_to_cell(lat, lng, self._resolution)
            if cell not in seen:
                seen.add(cell)
                cells.append(cell)
        return cells

    @staticmethod
    def _build_cache_key(vehicle_id: UUID, route_cells: list[str]) -> str:
        """Build a deterministic Redis cache key for the given vehicle + route cells.

        Key format: affinity:{vehicle_id}:{md5_of_sorted_cells[:12]}
        """
        sorted_hash = hashlib.md5(
            ":".join(sorted(route_cells)).encode()
        ).hexdigest()[:12]
        return f"affinity:{vehicle_id}:{sorted_hash}"

    @staticmethod
    def _serialize_result(result: dict) -> str:
        """Serialize affinity result to JSON, converting Decimal fields to strings."""

        def _default(obj):
            if isinstance(obj, Decimal):
                return str(obj)
            raise TypeError(f"Not serializable: {type(obj)}")

        return json.dumps(result, default=_default)

    @staticmethod
    def _deserialize_result(raw: str) -> dict:
        """Deserialize JSON affinity result, converting numeric strings back to Decimal."""
        data = json.loads(raw)
        data["affinity_score"] = Decimal(data["affinity_score"])
        for cell in data.get("cell_details", []):
            cell["affinity"] = Decimal(str(cell["affinity"]))
            cell["weight"] = Decimal(str(cell["weight"]))
        return data

    async def calculate_vehicle_affinity(
        self, vehicle_id: UUID, route_cells: list[str]
    ) -> dict:
        """Calculate weighted affinity score for a vehicle over route cells.

        Formula:
            score = sum [w(cell) * affinity(v, cell)] / sum [w(cell)]
            w(cell) = RouteHexStat.total_deliveries (default 1 if missing)

        When a Redis client is configured, results are cached for
        ``affinity_cache_ttl_seconds`` (default 300 s). Cache misses and
        Redis errors both fall through to the normal DB computation path.

        Returns:
            Dict with affinity_score (Decimal), confidence (str), cell_details (list).
        """
        if not route_cells:
            return {
                "affinity_score": Decimal("0.500"),
                "confidence": "LOW",
                "cell_details": [],
            }

        # --- Cache read ---
        cache_key: Optional[str] = None
        if self._redis is not None:
            cache_key = self._build_cache_key(vehicle_id, route_cells)
            try:
                cached = await self._redis.get(cache_key)
                if cached is not None:
                    logger.debug("Affinity cache HIT for key %s", cache_key)
                    return self._deserialize_result(cached)
                logger.debug("Affinity cache MISS for key %s", cache_key)
            except Exception as exc:
                logger.warning(
                    "Redis read error for key %s, falling through to DB: %s",
                    cache_key,
                    exc,
                )

        # --- Compute from DB ---
        cell_details = []
        weighted_sum = Decimal("0")
        weight_total = Decimal("0")

        for cell in route_cells:
            affinity, sample_size = await self._get_cell_affinity_with_fallback(
                vehicle_id, cell
            )
            weight = await self._get_cell_weight(cell)

            weighted_sum += weight * affinity
            weight_total += weight

            cell_details.append({
                "h3_index": cell,
                "affinity": affinity,
                "sample_size": sample_size,
                "weight": weight,
            })

        score = (
            weighted_sum / weight_total
            if weight_total > 0
            else Decimal("0.500")
        )

        confidence = self._calculate_confidence(cell_details)

        result = {
            "affinity_score": round(score, 3),
            "confidence": confidence,
            "cell_details": cell_details,
        }

        # --- Cache write ---
        if self._redis is not None and cache_key is not None:
            try:
                await self._redis.set(
                    cache_key,
                    self._serialize_result(result),
                    ex=self._settings.affinity_cache_ttl_seconds,
                )
            except Exception as exc:
                logger.warning(
                    "Redis write error for key %s: %s", cache_key, exc
                )

        return result

    async def _get_cell_affinity_with_fallback(
        self, vehicle_id: UUID, h3_index: str
    ) -> tuple[Decimal, int]:
        """Get affinity for vehicle+cell with cold-start blending.

        Fallback chain:
        1. If sample_size >= 10: use raw affinity
        2. If sample_size < 10: lambda = sample_size/10, blend with parent cell (resolution - 1)
        3. Falls back: parent cell -> global vehicle avg -> 0.5
        """
        # Query direct affinity
        result = await self._session.execute(
            select(VehicleHexAffinity.affinity_score, VehicleHexAffinity.sample_size)
            .where(
                VehicleHexAffinity.vehicle_id == vehicle_id,
                VehicleHexAffinity.h3_index == h3_index,
            )
        )
        row = result.first()

        if row is not None:
            affinity, sample_size = row[0], row[1]
            if sample_size >= COLD_START_THRESHOLD:
                return (affinity, sample_size)

            # Cold-start blending with parent
            lam = Decimal(str(sample_size)) / Decimal(str(COLD_START_THRESHOLD))
            parent_affinity = await self._get_parent_affinity(vehicle_id, h3_index)
            blended = lam * affinity + (Decimal("1") - lam) * parent_affinity
            return (round(blended, 3), sample_size)

        # No direct data -- try parent cell
        parent_affinity = await self._get_parent_affinity(vehicle_id, h3_index)
        return (parent_affinity, 0)

    async def _get_parent_affinity(
        self, vehicle_id: UUID, h3_index: str
    ) -> Decimal:
        """Get affinity from parent cell (resolution - 1).

        Falls back to global vehicle average, then 0.5.
        """
        if self._resolution <= 0:
            return await self._get_global_vehicle_avg(vehicle_id)

        parent_cell = self._geo.cell_to_parent(h3_index, self._resolution - 1)

        result = await self._session.execute(
            select(VehicleHexAffinity.affinity_score)
            .where(
                VehicleHexAffinity.vehicle_id == vehicle_id,
                VehicleHexAffinity.h3_index == parent_cell,
            )
        )
        row = result.scalar_one_or_none()

        if row is not None:
            return row

        return await self._get_global_vehicle_avg(vehicle_id)

    async def _get_global_vehicle_avg(self, vehicle_id: UUID) -> Decimal:
        """Get global average affinity for a vehicle across all cells."""
        result = await self._session.scalar(
            select(func.avg(VehicleHexAffinity.affinity_score))
            .where(VehicleHexAffinity.vehicle_id == vehicle_id)
        )
        return Decimal(str(round(result, 3))) if result is not None else Decimal("0.500")

    async def _get_cell_weight(self, h3_index: str) -> Decimal:
        """Get delivery weight for a cell from RouteHexStat."""
        result = await self._session.scalar(
            select(RouteHexStat.total_deliveries)
            .where(RouteHexStat.h3_index == h3_index)
        )
        return Decimal(str(result)) if result is not None else Decimal("1")

    @staticmethod
    def _calculate_confidence(cell_details: list[dict]) -> str:
        """Calculate confidence level based on % cells with adequate samples.

        HIGH: >= 70% cells have sample_size >= 10
        MEDIUM: 30-70%
        LOW: < 30%
        """
        if not cell_details:
            return "LOW"

        adequate = sum(
            1 for c in cell_details if c["sample_size"] >= COLD_START_THRESHOLD
        )
        pct = adequate / len(cell_details)

        if pct >= HIGH_CONFIDENCE_PCT:
            return "HIGH"
        elif pct >= MEDIUM_CONFIDENCE_PCT:
            return "MEDIUM"
        else:
            return "LOW"
