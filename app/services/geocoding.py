"""
Geocoding service using Nominatim (OpenStreetMap).

Converts addresses to latitude/longitude coordinates.
"""
import asyncio
from typing import Optional
from decimal import Decimal

import httpx
from pydantic import BaseModel


class GeocodingResult(BaseModel):
    """Geocoding result from Nominatim."""
    latitude: Decimal
    longitude: Decimal
    display_name: str
    address: dict


class GeocodingError(Exception):
    """Raised when geocoding fails."""
    pass


class GeocodingService:
    """
    Geocoding service using Nominatim API.

    Usage Policy:
    - Maximum 1 request per second
    - Must provide User-Agent header
    - For production, consider self-hosting Nominatim

    Nominatim API Documentation:
    https://nominatim.org/release-docs/latest/api/Search/
    """

    BASE_URL = "https://nominatim.openstreetmap.org/search"
    USER_AGENT = "ICCDDS/1.0 (Intelligent Cold-Chain Dispatch System)"

    # Rate limiting: 1 request per second
    _last_request_time: float = 0
    _min_interval: float = 1.0

    @classmethod
    async def geocode(
        cls,
        address: str,
        country: Optional[str] = "Taiwan",
    ) -> GeocodingResult:
        """
        Convert address to coordinates using Nominatim.

        Args:
            address: Full address string to geocode
            country: Country to limit search (default: Taiwan)

        Returns:
            GeocodingResult with lat/lon and metadata

        Raises:
            GeocodingError: If geocoding fails or no results found
        """
        if not address or not address.strip():
            raise GeocodingError("Address cannot be empty")

        # Rate limiting: ensure 1 second between requests
        current_time = asyncio.get_event_loop().time()
        time_since_last = current_time - cls._last_request_time

        if time_since_last < cls._min_interval:
            wait_time = cls._min_interval - time_since_last
            await asyncio.sleep(wait_time)

        cls._last_request_time = asyncio.get_event_loop().time()

        # Prepare request
        params = {
            "q": address,
            "format": "json",
            "addressdetails": "1",
            "limit": "1",
        }

        if country:
            params["countrycodes"] = cls._get_country_code(country)

        headers = {
            "User-Agent": cls.USER_AGENT,
        }

        # Make request
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.get(
                    cls.BASE_URL,
                    params=params,
                    headers=headers,
                )
                response.raise_for_status()
            except httpx.HTTPError as e:
                raise GeocodingError(f"Nominatim API request failed: {e}")

        # Parse response
        data = response.json()

        if not data or len(data) == 0:
            raise GeocodingError(f"No results found for address: {address}")

        result = data[0]

        try:
            return GeocodingResult(
                latitude=Decimal(result["lat"]),
                longitude=Decimal(result["lon"]),
                display_name=result.get("display_name", ""),
                address=result.get("address", {}),
            )
        except (KeyError, ValueError) as e:
            raise GeocodingError(f"Failed to parse Nominatim response: {e}")

    @staticmethod
    def _get_country_code(country: str) -> str:
        """Get ISO 3166-1 alpha-2 country code."""
        country_map = {
            "taiwan": "tw",
            "台灣": "tw",
            "china": "cn",
            "中國": "cn",
            "japan": "jp",
            "日本": "jp",
            "usa": "us",
            "united states": "us",
        }

        country_lower = country.lower()
        return country_map.get(country_lower, country_lower[:2])


# Singleton instance
geocoding_service = GeocodingService()
