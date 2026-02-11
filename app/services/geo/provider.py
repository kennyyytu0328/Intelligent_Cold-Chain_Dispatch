"""
GeoProvider abstraction for spatial indexing.

Provides H3 hexagonal indexing as the primary strategy,
with a pure-Python geohash fallback for environments where
the h3 C extension cannot be installed.
"""
from abc import ABC, abstractmethod
from typing import Optional

import logging

logger = logging.getLogger(__name__)

# H3 resolution → geohash precision mapping (approximate spatial equivalence)
_H3_TO_GEOHASH_PRECISION: dict[int, int] = {
    0: 1, 1: 1, 2: 2, 3: 2, 4: 3,
    5: 4, 6: 5, 7: 6, 8: 7, 9: 7,
    10: 8, 11: 8, 12: 9, 13: 9, 14: 10, 15: 10,
}


class GeoProvider(ABC):
    """Abstract base class for geospatial cell indexing."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the provider identifier ('h3' or 'geohash')."""

    def validate_coordinate(self, lat: float, lng: float) -> None:
        """Validate that coordinates are within valid bounds.

        Raises:
            ValueError: If coordinates are out of range.
        """
        if not (-90.0 <= lat <= 90.0):
            raise ValueError(
                f"Latitude {lat} out of range [-90, 90]"
            )
        if not (-180.0 <= lng <= 180.0):
            raise ValueError(
                f"Longitude {lng} out of range [-180, 180]"
            )

    @abstractmethod
    def lat_lng_to_cell(self, lat: float, lng: float, resolution: int) -> str:
        """Convert a coordinate pair to a cell identifier.

        Args:
            lat: Latitude in degrees.
            lng: Longitude in degrees.
            resolution: Grid resolution (0-15 for H3, 1-12 for geohash).

        Returns:
            Cell identifier string.
        """

    @abstractmethod
    def cell_to_parent(self, cell: str, parent_resolution: int) -> str:
        """Get the coarser parent cell containing *cell*.

        Args:
            cell: Cell identifier.
            parent_resolution: Target coarser resolution.

        Returns:
            Parent cell identifier string.
        """

    @abstractmethod
    def cell_to_lat_lng(self, cell: str) -> tuple[float, float]:
        """Return the center coordinate of a cell.

        Returns:
            (latitude, longitude) tuple.
        """


class H3Provider(GeoProvider):
    """H3 hexagonal grid provider (requires the ``h3`` package)."""

    @property
    def provider_name(self) -> str:
        return "h3"

    def lat_lng_to_cell(self, lat: float, lng: float, resolution: int) -> str:
        import h3

        self.validate_coordinate(lat, lng)
        return h3.latlng_to_cell(lat, lng, resolution)

    def cell_to_parent(self, cell: str, parent_resolution: int) -> str:
        import h3

        return h3.cell_to_parent(cell, parent_resolution)

    def cell_to_lat_lng(self, cell: str) -> tuple[float, float]:
        import h3

        return h3.cell_to_latlng(cell)


class GeohashProvider(GeoProvider):
    """Pure-Python geohash fallback provider."""

    @property
    def provider_name(self) -> str:
        return "geohash"

    def _h3_res_to_precision(self, resolution: int) -> int:
        """Map H3 resolution to geohash precision."""
        return _H3_TO_GEOHASH_PRECISION.get(resolution, 6)

    def lat_lng_to_cell(self, lat: float, lng: float, resolution: int) -> str:
        import pygeohash

        self.validate_coordinate(lat, lng)
        precision = self._h3_res_to_precision(resolution)
        return pygeohash.encode(lat, lng, precision=precision)

    def cell_to_parent(self, cell: str, parent_resolution: int) -> str:
        parent_precision = self._h3_res_to_precision(parent_resolution)
        return cell[:parent_precision]

    def cell_to_lat_lng(self, cell: str) -> tuple[float, float]:
        import pygeohash

        lat, lng = pygeohash.decode(cell)
        return (float(lat), float(lng))


# ---------------------------------------------------------------------------
# Factory / singleton
# ---------------------------------------------------------------------------

_cached_provider: Optional[GeoProvider] = None


def get_geo_provider() -> GeoProvider:
    """Return the best available GeoProvider (cached singleton).

    Prefers H3; falls back to geohash if h3 is not importable.
    """
    global _cached_provider
    if _cached_provider is not None:
        return _cached_provider

    try:
        import h3  # noqa: F401

        _cached_provider = H3Provider()
        logger.info("GeoProvider: using H3")
    except ImportError:
        _cached_provider = GeohashProvider()
        logger.warning(
            "GeoProvider: h3 not available, falling back to geohash"
        )

    return _cached_provider


def reset_geo_provider() -> None:
    """Clear the cached provider (for testing)."""
    global _cached_provider
    _cached_provider = None
