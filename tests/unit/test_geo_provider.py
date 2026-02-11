"""
Tests for GeoProvider service (H3 + Geohash providers).

No database required — pure computation tests.
"""
import importlib
import sys
from unittest.mock import patch

import pytest

from app.services.geo.provider import (
    GeoProvider,
    H3Provider,
    GeohashProvider,
    get_geo_provider,
    reset_geo_provider,
    _H3_TO_GEOHASH_PRECISION,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def h3_provider():
    return H3Provider()


@pytest.fixture()
def geohash_provider():
    return GeohashProvider()


@pytest.fixture(autouse=True)
def _reset_provider():
    """Reset the cached singleton before each test."""
    reset_geo_provider()
    yield
    reset_geo_provider()


# ---------------------------------------------------------------------------
# Coordinate validation (parametrized across both providers)
# ---------------------------------------------------------------------------

class TestCoordinateValidation:

    @pytest.mark.parametrize("provider_cls", [H3Provider, GeohashProvider])
    def test_valid_coordinate(self, provider_cls):
        p = provider_cls()
        p.validate_coordinate(25.033, 121.565)  # Should not raise

    @pytest.mark.parametrize("provider_cls", [H3Provider, GeohashProvider])
    def test_boundary_coordinates(self, provider_cls):
        p = provider_cls()
        p.validate_coordinate(90.0, 180.0)
        p.validate_coordinate(-90.0, -180.0)

    @pytest.mark.parametrize("provider_cls", [H3Provider, GeohashProvider])
    def test_invalid_latitude_high(self, provider_cls):
        p = provider_cls()
        with pytest.raises(ValueError, match="Latitude"):
            p.validate_coordinate(91.0, 0.0)

    @pytest.mark.parametrize("provider_cls", [H3Provider, GeohashProvider])
    def test_invalid_latitude_low(self, provider_cls):
        p = provider_cls()
        with pytest.raises(ValueError, match="Latitude"):
            p.validate_coordinate(-91.0, 0.0)

    @pytest.mark.parametrize("provider_cls", [H3Provider, GeohashProvider])
    def test_invalid_longitude_high(self, provider_cls):
        p = provider_cls()
        with pytest.raises(ValueError, match="Longitude"):
            p.validate_coordinate(0.0, 181.0)

    @pytest.mark.parametrize("provider_cls", [H3Provider, GeohashProvider])
    def test_invalid_longitude_low(self, provider_cls):
        p = provider_cls()
        with pytest.raises(ValueError, match="Longitude"):
            p.validate_coordinate(0.0, -181.0)


# ---------------------------------------------------------------------------
# H3Provider
# ---------------------------------------------------------------------------

class TestH3Provider:

    def test_provider_name(self, h3_provider):
        assert h3_provider.provider_name == "h3"

    def test_cell_format(self, h3_provider):
        """H3 cell IDs are 15-character hex strings."""
        cell = h3_provider.lat_lng_to_cell(25.033, 121.565, 7)
        assert isinstance(cell, str)
        assert len(cell) == 15

    def test_same_point_same_cell(self, h3_provider):
        """Same coordinates should always map to the same cell."""
        cell1 = h3_provider.lat_lng_to_cell(25.033, 121.565, 7)
        cell2 = h3_provider.lat_lng_to_cell(25.033, 121.565, 7)
        assert cell1 == cell2

    def test_different_cities_different_cells(self, h3_provider):
        """Taipei and Kaohsiung should be in different cells."""
        taipei = h3_provider.lat_lng_to_cell(25.033, 121.565, 7)
        kaohsiung = h3_provider.lat_lng_to_cell(22.627, 120.301, 7)
        assert taipei != kaohsiung

    def test_parent_child_relationship(self, h3_provider):
        """A cell's parent at coarser resolution should contain it."""
        child = h3_provider.lat_lng_to_cell(25.033, 121.565, 7)
        parent = h3_provider.cell_to_parent(child, 5)
        assert isinstance(parent, str)
        assert len(parent) == 15  # H3 cells are always 15 chars
        # Re-derive parent from same point at resolution 5
        direct_parent = h3_provider.lat_lng_to_cell(25.033, 121.565, 5)
        assert parent == direct_parent

    def test_roundtrip(self, h3_provider):
        """Cell center should be near the original point."""
        lat, lng = 25.033, 121.565
        cell = h3_provider.lat_lng_to_cell(lat, lng, 7)
        rlat, rlng = h3_provider.cell_to_lat_lng(cell)
        assert abs(rlat - lat) < 0.02  # Within ~2 km
        assert abs(rlng - lng) < 0.02

    def test_resolution_affects_cell(self, h3_provider):
        """Different resolutions should produce different cell IDs."""
        cell_5 = h3_provider.lat_lng_to_cell(25.033, 121.565, 5)
        cell_7 = h3_provider.lat_lng_to_cell(25.033, 121.565, 7)
        assert cell_5 != cell_7


# ---------------------------------------------------------------------------
# GeohashProvider
# ---------------------------------------------------------------------------

class TestGeohashProvider:

    def test_provider_name(self, geohash_provider):
        assert geohash_provider.provider_name == "geohash"

    def test_cell_format(self, geohash_provider):
        """Geohash cells are alphanumeric strings."""
        cell = geohash_provider.lat_lng_to_cell(25.033, 121.565, 7)
        assert isinstance(cell, str)
        assert cell.isalnum()

    def test_same_point_same_cell(self, geohash_provider):
        cell1 = geohash_provider.lat_lng_to_cell(25.033, 121.565, 7)
        cell2 = geohash_provider.lat_lng_to_cell(25.033, 121.565, 7)
        assert cell1 == cell2

    def test_different_cities_different_cells(self, geohash_provider):
        taipei = geohash_provider.lat_lng_to_cell(25.033, 121.565, 7)
        kaohsiung = geohash_provider.lat_lng_to_cell(22.627, 120.301, 7)
        assert taipei != kaohsiung

    def test_prefix_based_parent(self, geohash_provider):
        """Geohash parent is a prefix of the child."""
        child = geohash_provider.lat_lng_to_cell(25.033, 121.565, 7)
        parent = geohash_provider.cell_to_parent(child, 5)
        assert child.startswith(parent)

    def test_roundtrip(self, geohash_provider):
        """Decoded center should be near the original point."""
        lat, lng = 25.033, 121.565
        cell = geohash_provider.lat_lng_to_cell(lat, lng, 7)
        rlat, rlng = geohash_provider.cell_to_lat_lng(cell)
        assert abs(rlat - lat) < 0.02
        assert abs(rlng - lng) < 0.02

    def test_precision_mapping(self, geohash_provider):
        """Resolution 7 should map to geohash precision 6."""
        assert geohash_provider._h3_res_to_precision(7) == 6
        assert geohash_provider._h3_res_to_precision(5) == 4

    def test_precision_mapping_covers_all_h3_resolutions(self):
        """The mapping table should cover H3 resolutions 0-15."""
        for res in range(16):
            assert res in _H3_TO_GEOHASH_PRECISION


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

class TestFactory:

    def test_returns_h3_when_available(self):
        provider = get_geo_provider()
        assert provider.provider_name == "h3"
        assert isinstance(provider, H3Provider)

    def test_caching(self):
        """Factory should return the same instance on repeated calls."""
        p1 = get_geo_provider()
        p2 = get_geo_provider()
        assert p1 is p2

    def test_reset_clears_cache(self):
        p1 = get_geo_provider()
        reset_geo_provider()
        p2 = get_geo_provider()
        assert p1 is not p2

    def test_falls_back_to_geohash(self):
        """When h3 import fails, factory should return GeohashProvider."""
        import app.services.geo.provider as provider_module

        original_import = __builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__

        def mock_import(name, *args, **kwargs):
            if name == "h3":
                raise ImportError("Mocked h3 unavailable")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            reset_geo_provider()
            provider = get_geo_provider()
            assert provider.provider_name == "geohash"
            assert isinstance(provider, GeohashProvider)


# ---------------------------------------------------------------------------
# Cross-provider consistency
# ---------------------------------------------------------------------------

class TestCrossProviderConsistency:

    def test_both_roundtrip_near_original(self, h3_provider, geohash_provider):
        """Both providers should roundtrip close to the original point."""
        lat, lng = 25.033, 121.565

        h3_cell = h3_provider.lat_lng_to_cell(lat, lng, 7)
        h3_lat, h3_lng = h3_provider.cell_to_lat_lng(h3_cell)

        gh_cell = geohash_provider.lat_lng_to_cell(lat, lng, 7)
        gh_lat, gh_lng = geohash_provider.cell_to_lat_lng(gh_cell)

        # Both should be within ~2 km of original
        assert abs(h3_lat - lat) < 0.02
        assert abs(gh_lat - lat) < 0.02
        assert abs(h3_lng - lng) < 0.02
        assert abs(gh_lng - lng) < 0.02

    def test_both_distinguish_distant_cities(self, h3_provider, geohash_provider):
        """Both providers must distinguish Taipei from Kaohsiung."""
        for provider in (h3_provider, geohash_provider):
            taipei = provider.lat_lng_to_cell(25.033, 121.565, 7)
            kaohsiung = provider.lat_lng_to_cell(22.627, 120.301, 7)
            assert taipei != kaohsiung, f"{provider.provider_name} failed"

    def test_both_reject_invalid_coords(self, h3_provider, geohash_provider):
        """Both providers should reject out-of-range coordinates."""
        for provider in (h3_provider, geohash_provider):
            with pytest.raises(ValueError):
                provider.lat_lng_to_cell(999, 0, 7)
