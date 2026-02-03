"""
Vehicle API endpoints.
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_async_session
from app.models import Vehicle, VehicleStatus
from app.schemas.vehicle import (
    VehicleCreate,
    VehicleUpdate,
    VehicleResponse,
    VehicleListResponse,
)

router = APIRouter()


@router.get("", response_model=VehicleListResponse)
async def list_vehicles(
    status: Optional[VehicleStatus] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    session: AsyncSession = Depends(get_async_session),
):
    """
    List all vehicles with optional filtering.

    - **status**: Filter by vehicle status (AVAILABLE, IN_USE, MAINTENANCE, OFFLINE)
    """
    query = select(Vehicle)

    if status:
        query = query.where(Vehicle.status == status)

    query = query.offset(skip).limit(limit)

    result = await session.execute(query)
    vehicles = result.scalars().all()

    # Get total count
    count_query = select(func.count(Vehicle.id))
    if status:
        count_query = count_query.where(Vehicle.status == status)
    total = await session.scalar(count_query)

    return VehicleListResponse(
        items=[VehicleResponse.model_validate(v) for v in vehicles],
        total=total,
    )


@router.get("/{vehicle_id}", response_model=VehicleResponse)
async def get_vehicle(
    vehicle_id: UUID,
    session: AsyncSession = Depends(get_async_session),
):
    """Get a specific vehicle by ID."""
    result = await session.execute(
        select(Vehicle).where(Vehicle.id == vehicle_id)
    )
    vehicle = result.scalar_one_or_none()

    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")

    return VehicleResponse.model_validate(vehicle)


@router.post("", response_model=VehicleResponse, status_code=201)
async def create_vehicle(
    data: VehicleCreate,
    session: AsyncSession = Depends(get_async_session),
):
    """
    Create a new vehicle.

    Thermodynamic parameters will be automatically derived from insulation_grade and door_type.
    """
    # Check for duplicate license plate
    existing = await session.execute(
        select(Vehicle).where(Vehicle.license_plate == data.license_plate)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail=f"Vehicle with license plate {data.license_plate} already exists",
        )

    # Create vehicle with derived thermodynamic values
    vehicle = Vehicle(
        license_plate=data.license_plate,
        driver_id=data.driver_id,
        driver_name=data.driver_name,
        capacity_weight=data.capacity_weight,
        capacity_volume=data.capacity_volume,
        internal_length=data.internal_length,
        internal_width=data.internal_width,
        internal_height=data.internal_height,
        insulation_grade=data.insulation_grade,
        k_value=data.insulation_grade.k_value,
        door_type=data.door_type,
        door_coefficient=data.door_type.coefficient,
        has_strip_curtains=data.has_strip_curtains,
        cooling_rate=data.cooling_rate,
        min_temp_capability=data.min_temp_capability,
    )

    session.add(vehicle)
    await session.flush()
    await session.refresh(vehicle)

    return VehicleResponse.model_validate(vehicle)


@router.patch("/{vehicle_id}", response_model=VehicleResponse)
async def update_vehicle(
    vehicle_id: UUID,
    data: VehicleUpdate,
    session: AsyncSession = Depends(get_async_session),
):
    """Update a vehicle."""
    result = await session.execute(
        select(Vehicle).where(Vehicle.id == vehicle_id)
    )
    vehicle = result.scalar_one_or_none()

    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")

    # Update fields
    update_data = data.model_dump(exclude_unset=True)

    # If insulation_grade changes, update k_value
    if "insulation_grade" in update_data:
        update_data["k_value"] = update_data["insulation_grade"].k_value

    # If door_type changes, update door_coefficient
    if "door_type" in update_data:
        update_data["door_coefficient"] = update_data["door_type"].coefficient

    for field, value in update_data.items():
        setattr(vehicle, field, value)

    await session.flush()
    await session.refresh(vehicle)

    return VehicleResponse.model_validate(vehicle)


@router.delete("/{vehicle_id}", status_code=204)
async def delete_vehicle(
    vehicle_id: UUID,
    session: AsyncSession = Depends(get_async_session),
):
    """Delete a vehicle."""
    result = await session.execute(
        select(Vehicle).where(Vehicle.id == vehicle_id)
    )
    vehicle = result.scalar_one_or_none()

    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")

    await session.delete(vehicle)


@router.get("/{vehicle_id}/thermodynamics")
async def get_vehicle_thermodynamics(
    vehicle_id: UUID,
    session: AsyncSession = Depends(get_async_session),
):
    """
    Get thermodynamic parameters for a vehicle.

    Returns the parameters used in temperature calculations:
    - K_insulation (heat transfer coefficient)
    - C_door (door coefficient)
    - Has strip curtains (reduces heat loss by 50%)
    - Cooling rate (°C/min)
    """
    result = await session.execute(
        select(Vehicle).where(Vehicle.id == vehicle_id)
    )
    vehicle = result.scalar_one_or_none()

    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")

    return {
        "vehicle_id": str(vehicle.id),
        "license_plate": vehicle.license_plate,
        "thermodynamics": {
            "insulation_grade": vehicle.insulation_grade.value,
            "k_value": float(vehicle.k_value),
            "door_type": vehicle.door_type.value,
            "door_coefficient": float(vehicle.door_coefficient),
            "has_strip_curtains": vehicle.has_strip_curtains,
            "curtain_factor": 0.5 if vehicle.has_strip_curtains else 1.0,
            "cooling_rate": float(vehicle.cooling_rate),
            "min_temp_capability": float(vehicle.min_temp_capability),
        },
        "formulas": {
            "transit_rise": "ΔT_drive = Time × (T_ambient - T_current) × K_insulation",
            "door_rise": "ΔT_door = Time × C_door × (1 - 0.5 × IsCurtain)",
            "cooling": "ΔT_cooling = Time × Rate_cooling",
        },
    }
