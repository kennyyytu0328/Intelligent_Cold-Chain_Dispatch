"""
Depot API endpoints for warehouse/depot location management.
"""
import os
import tempfile
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from geoalchemy2.elements import WKTElement
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_async_session
from app.models import Depot
from app.schemas.depot import (
    DepotCreate,
    DepotUpdate,
    DepotResponse,
    DepotListResponse,
)
from app.services.depot_import import import_depots_from_excel, DepotImportError

router = APIRouter()


@router.get("", response_model=DepotListResponse)
async def list_depots(
    is_active: Optional[bool] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    session: AsyncSession = Depends(get_async_session),
):
    """
    List all depots with optional filtering.

    - **is_active**: Filter by active status (true/false)
    - **skip**: Number of records to skip (pagination)
    - **limit**: Maximum number of records to return
    """
    query = select(Depot)

    if is_active is not None:
        query = query.where(Depot.is_active == is_active)

    query = query.order_by(Depot.created_at.desc()).offset(skip).limit(limit)

    result = await session.execute(query)
    depots = result.scalars().all()

    # Get total count
    count_query = select(func.count(Depot.id))
    if is_active is not None:
        count_query = count_query.where(Depot.is_active == is_active)
    total = await session.scalar(count_query)

    return DepotListResponse(
        total=total or 0,
        depots=[DepotResponse.model_validate(d) for d in depots],
    )


@router.get("/{depot_id}", response_model=DepotResponse)
async def get_depot(
    depot_id: UUID,
    session: AsyncSession = Depends(get_async_session),
):
    """Get a specific depot by ID."""
    result = await session.execute(
        select(Depot).where(Depot.id == depot_id)
    )
    depot = result.scalar_one_or_none()

    if not depot:
        raise HTTPException(status_code=404, detail="Depot not found")

    return DepotResponse.model_validate(depot)


@router.post("", response_model=DepotResponse, status_code=201)
async def create_depot(
    data: DepotCreate,
    session: AsyncSession = Depends(get_async_session),
):
    """
    Create a new depot.

    PostGIS geography point will be automatically created from latitude and longitude.
    """
    # Check for duplicate code if provided
    if data.code:
        existing = await session.execute(
            select(Depot).where(Depot.code == data.code)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=400,
                detail=f"Depot with code {data.code} already exists",
            )

    # Create PostGIS geography point from lat/lon
    # Format: POINT(longitude latitude) - note the order!
    location_wkt = f"POINT({data.longitude} {data.latitude})"

    depot = Depot(
        name=data.name,
        code=data.code,
        address=data.address,
        latitude=data.latitude,
        longitude=data.longitude,
        location=WKTElement(location_wkt, srid=4326),
        is_active=data.is_active,
        contact_person=data.contact_person,
        contact_phone=data.contact_phone,
    )

    session.add(depot)
    await session.flush()
    await session.refresh(depot)

    return DepotResponse.model_validate(depot)


@router.patch("/{depot_id}", response_model=DepotResponse)
async def update_depot(
    depot_id: UUID,
    data: DepotUpdate,
    session: AsyncSession = Depends(get_async_session),
):
    """Update a depot."""
    result = await session.execute(
        select(Depot).where(Depot.id == depot_id)
    )
    depot = result.scalar_one_or_none()

    if not depot:
        raise HTTPException(status_code=404, detail="Depot not found")

    # Update fields
    update_data = data.model_dump(exclude_unset=True)

    # If code is changing, check for duplicates
    if "code" in update_data and update_data["code"] != depot.code:
        existing = await session.execute(
            select(Depot).where(Depot.code == update_data["code"])
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=400,
                detail=f"Depot with code {update_data['code']} already exists",
            )

    # If lat/lon changed, update PostGIS location
    lat_changed = "latitude" in update_data
    lon_changed = "longitude" in update_data

    if lat_changed or lon_changed:
        new_lat = update_data.get("latitude", depot.latitude)
        new_lon = update_data.get("longitude", depot.longitude)
        location_wkt = f"POINT({new_lon} {new_lat})"
        update_data["location"] = WKTElement(location_wkt, srid=4326)

    for field, value in update_data.items():
        setattr(depot, field, value)

    await session.flush()
    await session.refresh(depot)

    return DepotResponse.model_validate(depot)


@router.delete("/{depot_id}", status_code=204)
async def delete_depot(
    depot_id: UUID,
    session: AsyncSession = Depends(get_async_session),
):
    """
    Delete a depot.

    Note: This is a hard delete. Consider implementing soft delete
    by setting is_active=False instead for production use.
    """
    result = await session.execute(
        select(Depot).where(Depot.id == depot_id)
    )
    depot = result.scalar_one_or_none()

    if not depot:
        raise HTTPException(status_code=404, detail="Depot not found")

    await session.delete(depot)
    await session.flush()

    return None


class DepotImportResponse(BaseModel):
    """Response for depot Excel import."""
    total: int
    success: int
    skipped: int
    failed: int
    geocoded: int
    errors: list[str]


@router.post("/import", response_model=DepotImportResponse)
async def import_depots(
    file: UploadFile = File(...),
    skip_geocoding: bool = Query(
        False,
        description="Skip rows without coordinates (don't geocode)",
    ),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Import depots from Excel file.

    **Supported formats:** .xlsx, .xls

    **Expected sheet name:** "倉庫 (Depots)"

    **Columns:**
    - name (required): Depot name
    - code (optional): Unique depot code
    - address (optional*): Full address
    - latitude (optional*): Latitude in decimal degrees
    - longitude (optional*): Longitude in decimal degrees
    - is_active (required): TRUE or FALSE
    - contact_person (optional): Contact person name
    - contact_phone (optional): Contact phone number

    **Coordinate modes:**
    1. Pre-filled: Provide latitude and longitude → Used directly
    2. Address-only: Provide address → Geocoded via Nominatim (1 sec/row)

    **Rate limiting:**
    - Geocoding is rate-limited to 1 request per second
    - Example: 50 rows with address-only = ~50 seconds

    **Recommendations:**
    - For batch imports (10+ depots), pre-fill coordinates in Excel
    - Use skip_geocoding=true to skip rows without coordinates
    """
    # Validate file type
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(
            status_code=400,
            detail="Invalid file format. Only .xlsx and .xls are supported.",
        )

    # Save uploaded file to temporary location
    temp_file = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
            content = await file.read()
            tmp.write(content)
            temp_file = tmp.name

        # Import depots
        stats = await import_depots_from_excel(
            file_path=temp_file,
            session=session,
            skip_geocoding=skip_geocoding,
        )

        return DepotImportResponse(**stats)

    except DepotImportError as e:
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Import failed: {str(e)}",
        )

    finally:
        # Clean up temporary file
        if temp_file and os.path.exists(temp_file):
            os.remove(temp_file)
