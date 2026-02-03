"""
Geocoding API endpoints.
"""
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.geocoding import geocoding_service, GeocodingError

router = APIRouter()


class GeocodeRequest(BaseModel):
    """Request to geocode an address."""
    address: str = Field(..., min_length=1, max_length=500, description="Address to geocode")
    country: Optional[str] = Field(default="Taiwan", description="Country to limit search")


class GeocodeResponse(BaseModel):
    """Geocoding response with coordinates."""
    latitude: Decimal = Field(..., description="Latitude in decimal degrees")
    longitude: Decimal = Field(..., description="Longitude in decimal degrees")
    display_name: str = Field(..., description="Formatted address from Nominatim")
    address: dict = Field(default_factory=dict, description="Detailed address components")


@router.post("/geocode", response_model=GeocodeResponse)
async def geocode_address(request: GeocodeRequest):
    """
    Convert address to latitude/longitude coordinates.

    Uses Nominatim (OpenStreetMap) API with rate limiting (1 req/sec).

    **Example Request:**
    ```json
    {
        "address": "台北101, 台北市信義區信義路五段7號",
        "country": "Taiwan"
    }
    ```

    **Example Response:**
    ```json
    {
        "latitude": 25.0330,
        "longitude": 121.5654,
        "display_name": "台北101, 信義路五段, 信義區, 台北市, 110, 臺灣",
        "address": {
            "building": "台北101",
            "road": "信義路五段",
            "suburb": "信義區",
            "city": "台北市",
            "postcode": "110",
            "country": "臺灣"
        }
    }
    ```

    **Rate Limits:**
    - Maximum 1 request per second (enforced by service)
    - For batch operations, consider using Excel with pre-filled coordinates

    **Error Responses:**
    - 400: Invalid address or geocoding failed
    - 422: Validation error
    """
    try:
        result = await geocoding_service.geocode(
            address=request.address,
            country=request.country,
        )

        return GeocodeResponse(
            latitude=result.latitude,
            longitude=result.longitude,
            display_name=result.display_name,
            address=result.address,
        )

    except GeocodingError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Geocoding service error: {str(e)}",
        )
