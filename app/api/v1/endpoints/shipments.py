"""
Shipment API endpoints.
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from geoalchemy2.elements import WKTElement
from sqlalchemy import select, func, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_async_session
from app.models import Shipment, ShipmentStatus, Route, RouteStop
from app.schemas.shipment import (
    ShipmentCreate,
    ShipmentUpdate,
    ShipmentResponse,
    ShipmentListResponse,
    ShipmentBatchCreate,
)

router = APIRouter()


@router.get("", response_model=ShipmentListResponse)
async def list_shipments(
    status: Optional[ShipmentStatus] = None,
    customer_id: Optional[UUID] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    session: AsyncSession = Depends(get_async_session),
):
    """
    List all shipments with optional filtering.

    - **status**: Filter by shipment status
    - **customer_id**: Filter by customer
    """
    query = select(Shipment)

    if status:
        query = query.where(Shipment.status == status)
    if customer_id:
        query = query.where(Shipment.customer_id == customer_id)

    query = query.order_by(Shipment.created_at.desc())
    query = query.offset(skip).limit(limit)

    result = await session.execute(query)
    shipments = result.scalars().all()

    # Get total count
    count_query = select(func.count(Shipment.id))
    if status:
        count_query = count_query.where(Shipment.status == status)
    if customer_id:
        count_query = count_query.where(Shipment.customer_id == customer_id)
    total = await session.scalar(count_query)

    return ShipmentListResponse(
        items=[ShipmentResponse.model_validate(s) for s in shipments],
        total=total,
    )


@router.get("/pending")
async def list_pending_shipments(
    session: AsyncSession = Depends(get_async_session),
):
    """
    List all pending shipments ready for optimization.

    Returns a summary suitable for optimization planning.
    """
    query = select(Shipment).where(Shipment.status == ShipmentStatus.PENDING)
    result = await session.execute(query)
    shipments = result.scalars().all()

    total_weight = sum(float(s.weight) for s in shipments)
    total_volume = sum(float(s.volume or 0) for s in shipments)
    strict_count = sum(1 for s in shipments if s.sla_tier.value == "STRICT")

    return {
        "total_pending": len(shipments),
        "strict_sla_count": strict_count,
        "standard_sla_count": len(shipments) - strict_count,
        "total_weight_kg": total_weight,
        "total_volume_m3": total_volume,
        "shipments": [
            {
                "id": str(s.id),
                "order_number": s.order_number,
                "sla_tier": s.sla_tier.value,
                "temp_limit": float(s.temp_limit_upper),
                "time_windows": s.time_windows,
                "weight": float(s.weight),
            }
            for s in shipments
        ],
    }


@router.get("/{shipment_id}", response_model=ShipmentResponse)
async def get_shipment(
    shipment_id: UUID,
    session: AsyncSession = Depends(get_async_session),
):
    """Get a specific shipment by ID."""
    result = await session.execute(
        select(Shipment).where(Shipment.id == shipment_id)
    )
    shipment = result.scalar_one_or_none()

    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")

    return ShipmentResponse.model_validate(shipment)


@router.post("", response_model=ShipmentResponse, status_code=201)
async def create_shipment(
    data: ShipmentCreate,
    session: AsyncSession = Depends(get_async_session),
):
    """
    Create a new shipment.

    Time windows support OR logic - delivery must satisfy ANY one window.
    """
    # Check for duplicate order number
    existing = await session.execute(
        select(Shipment).where(Shipment.order_number == data.order_number)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail=f"Shipment with order number {data.order_number} already exists",
        )

    # Create PostGIS point from coordinates
    geo_location = WKTElement(
        f"POINT({float(data.longitude)} {float(data.latitude)})",
        srid=4326,
    )

    # Convert time windows to dict format
    time_windows = [tw.model_dump() for tw in data.time_windows]

    # Convert dimensions if provided
    dimensions = data.dimensions.model_dump() if data.dimensions else None

    shipment = Shipment(
        order_number=data.order_number,
        customer_id=data.customer_id,
        delivery_address=data.delivery_address,
        geo_location=geo_location,
        latitude=data.latitude,
        longitude=data.longitude,
        time_windows=time_windows,
        sla_tier=data.sla_tier,
        temp_limit_upper=data.temp_limit_upper,
        temp_limit_lower=data.temp_limit_lower,
        service_duration=data.service_duration,
        weight=data.weight,
        volume=data.volume,
        dimensions=dimensions,
        package_count=data.package_count,
        priority=data.priority,
        special_instructions=data.special_instructions,
    )

    session.add(shipment)
    await session.flush()
    await session.refresh(shipment)

    return ShipmentResponse.model_validate(shipment)


@router.post("/batch", status_code=201)
async def create_shipments_batch(
    data: ShipmentBatchCreate,
    session: AsyncSession = Depends(get_async_session),
):
    """
    Create multiple shipments in batch.

    Returns summary of created shipments.
    """
    created = []
    errors = []

    for shipment_data in data.shipments:
        try:
            # Check for duplicate
            existing = await session.execute(
                select(Shipment).where(Shipment.order_number == shipment_data.order_number)
            )
            if existing.scalar_one_or_none():
                errors.append({
                    "order_number": shipment_data.order_number,
                    "error": "Duplicate order number",
                })
                continue

            geo_location = WKTElement(
                f"POINT({float(shipment_data.longitude)} {float(shipment_data.latitude)})",
                srid=4326,
            )

            time_windows = [tw.model_dump() for tw in shipment_data.time_windows]
            dimensions = shipment_data.dimensions.model_dump() if shipment_data.dimensions else None

            shipment = Shipment(
                order_number=shipment_data.order_number,
                customer_id=shipment_data.customer_id,
                delivery_address=shipment_data.delivery_address,
                geo_location=geo_location,
                latitude=shipment_data.latitude,
                longitude=shipment_data.longitude,
                time_windows=time_windows,
                sla_tier=shipment_data.sla_tier,
                temp_limit_upper=shipment_data.temp_limit_upper,
                temp_limit_lower=shipment_data.temp_limit_lower,
                service_duration=shipment_data.service_duration,
                weight=shipment_data.weight,
                volume=shipment_data.volume,
                dimensions=dimensions,
                package_count=shipment_data.package_count,
                priority=shipment_data.priority,
                special_instructions=shipment_data.special_instructions,
            )

            session.add(shipment)
            created.append(shipment_data.order_number)

        except Exception as e:
            errors.append({
                "order_number": shipment_data.order_number,
                "error": str(e),
            })

    await session.flush()

    return {
        "created_count": len(created),
        "error_count": len(errors),
        "created_orders": created,
        "errors": errors,
    }


@router.patch("/{shipment_id}", response_model=ShipmentResponse)
async def update_shipment(
    shipment_id: UUID,
    data: ShipmentUpdate,
    session: AsyncSession = Depends(get_async_session),
):
    """Update a shipment."""
    result = await session.execute(
        select(Shipment).where(Shipment.id == shipment_id)
    )
    shipment = result.scalar_one_or_none()

    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")

    # Get update data
    update_data = data.model_dump(exclude_unset=True)

    # Handle special fields
    if "time_windows" in update_data:
        update_data["time_windows"] = [tw.model_dump() for tw in data.time_windows]

    if "dimensions" in update_data and data.dimensions:
        update_data["dimensions"] = data.dimensions.model_dump()

    # Update geo_location if coordinates change
    if "latitude" in update_data or "longitude" in update_data:
        lat = update_data.get("latitude", shipment.latitude)
        lon = update_data.get("longitude", shipment.longitude)
        update_data["geo_location"] = WKTElement(
            f"POINT({float(lon)} {float(lat)})",
            srid=4326,
        )

    for field, value in update_data.items():
        setattr(shipment, field, value)

    await session.flush()
    await session.refresh(shipment)

    return ShipmentResponse.model_validate(shipment)


@router.delete("/{shipment_id}", status_code=204)
async def delete_shipment(
    shipment_id: UUID,
    session: AsyncSession = Depends(get_async_session),
):
    """Delete a shipment (only if PENDING status)."""
    result = await session.execute(
        select(Shipment).where(Shipment.id == shipment_id)
    )
    shipment = result.scalar_one_or_none()

    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")

    if shipment.status != ShipmentStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete shipment with status {shipment.status.value}",
        )

    await session.delete(shipment)


@router.post("/reset")
async def reset_all_shipments(
    session: AsyncSession = Depends(get_async_session),
):
    """
    Reset all shipments to PENDING status.

    This operation:
    1. Deletes all route_stops
    2. Deletes all routes
    3. Resets all shipments to PENDING status
    4. Clears route_id and route_sequence from shipments

    Use this to start fresh without deleting shipment data.
    """
    # Step 1: Delete all route_stops
    await session.execute(delete(RouteStop))

    # Step 2: Reset all shipments - clear route assignment and set status to PENDING
    await session.execute(
        update(Shipment).values(
            status=ShipmentStatus.PENDING,
            route_id=None,
            route_sequence=None,
        )
    )

    # Step 3: Delete all routes
    await session.execute(delete(Route))

    await session.flush()

    # Get count of reset shipments
    count = await session.scalar(select(func.count(Shipment.id)))

    return {
        "message": "All shipments have been reset to PENDING status",
        "shipments_reset": count,
    }
