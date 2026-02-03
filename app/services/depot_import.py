"""
Depot Excel import service with optional geocoding.
"""
import asyncio
from decimal import Decimal
from typing import Optional

import pandas as pd
from geoalchemy2.elements import WKTElement
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Depot
from app.services.geocoding import geocoding_service, GeocodingError


class DepotImportError(Exception):
    """Raised when depot import fails."""
    pass


async def import_depots_from_excel(
    file_path: str,
    session: AsyncSession,
    skip_geocoding: bool = False,
) -> dict:
    """
    Import depots from Excel file.

    Supports two modes:
    1. Pre-filled coordinates: Uses provided lat/lon directly
    2. Address-only: Geocodes address to get coordinates (1 req/sec)

    Args:
        file_path: Path to Excel file
        session: SQLAlchemy async session
        skip_geocoding: If True, skip rows without coordinates

    Returns:
        Dictionary with import statistics:
        {
            "total": 10,
            "success": 8,
            "skipped": 1,
            "failed": 1,
            "geocoded": 3,
            "errors": [...]
        }
    """
    try:
        # Read Excel file (support both .xlsx and .xls)
        if file_path.endswith('.xlsx'):
            df = pd.read_excel(file_path, sheet_name='倉庫 (Depots)', engine='openpyxl')
        else:
            df = pd.read_excel(file_path, sheet_name='倉庫 (Depots)')

    except Exception as e:
        raise DepotImportError(f"Failed to read Excel file: {e}")

    # Validate required columns
    required_columns = ['name', 'is_active']
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        raise DepotImportError(f"Missing required columns: {missing_columns}")

    # Statistics
    stats = {
        "total": len(df),
        "success": 0,
        "skipped": 0,
        "failed": 0,
        "geocoded": 0,
        "errors": [],
    }

    # Process each row
    for index, row in df.iterrows():
        row_num = index + 2  # Excel row number (1-indexed + header)

        try:
            # Required fields
            name = str(row['name']).strip()
            if not name or pd.isna(row['name']):
                stats["skipped"] += 1
                stats["errors"].append(f"Row {row_num}: Name is required")
                continue

            # Parse is_active
            is_active_str = str(row.get('is_active', 'TRUE')).strip().upper()
            is_active = is_active_str in ['TRUE', 'YES', '1', 'T', 'Y']

            # Get coordinates
            lat = row.get('latitude')
            lon = row.get('longitude')
            address = str(row.get('address', '')).strip() if not pd.isna(row.get('address')) else ''

            # Check if coordinates are provided
            has_coords = (
                not pd.isna(lat) and not pd.isna(lon) and
                lat != '' and lon != ''
            )

            if has_coords:
                # Use provided coordinates
                try:
                    latitude = Decimal(str(lat))
                    longitude = Decimal(str(lon))
                except (ValueError, TypeError) as e:
                    stats["failed"] += 1
                    stats["errors"].append(f"Row {row_num}: Invalid coordinates - {e}")
                    continue

            elif address and not skip_geocoding:
                # Geocode address
                try:
                    result = await geocoding_service.geocode(address, country="Taiwan")
                    latitude = result.latitude
                    longitude = result.longitude
                    stats["geocoded"] += 1
                except GeocodingError as e:
                    stats["failed"] += 1
                    stats["errors"].append(f"Row {row_num}: Geocoding failed - {e}")
                    continue

            else:
                # No coordinates and no address
                stats["skipped"] += 1
                stats["errors"].append(
                    f"Row {row_num}: Either coordinates or address must be provided"
                )
                continue

            # Optional fields
            code = str(row.get('code', '')).strip() if not pd.isna(row.get('code')) else None
            contact_person = str(row.get('contact_person', '')).strip() if not pd.isna(row.get('contact_person')) else None
            contact_phone = str(row.get('contact_phone', '')).strip() if not pd.isna(row.get('contact_phone')) else None

            # Check for duplicate code
            if code:
                existing = await session.execute(
                    select(Depot).where(Depot.code == code)
                )
                if existing.scalar_one_or_none():
                    stats["failed"] += 1
                    stats["errors"].append(f"Row {row_num}: Duplicate code '{code}'")
                    continue

            # Create PostGIS geography point
            location_wkt = f"POINT({longitude} {latitude})"

            # Create depot
            depot = Depot(
                name=name,
                code=code if code else None,
                address=address if address else None,
                latitude=latitude,
                longitude=longitude,
                location=WKTElement(location_wkt, srid=4326),
                is_active=is_active,
                contact_person=contact_person,
                contact_phone=contact_phone,
            )

            session.add(depot)
            stats["success"] += 1

        except Exception as e:
            stats["failed"] += 1
            stats["errors"].append(f"Row {row_num}: Unexpected error - {e}")
            continue

    # Commit all changes
    try:
        await session.flush()
    except Exception as e:
        raise DepotImportError(f"Database commit failed: {e}")

    return stats
