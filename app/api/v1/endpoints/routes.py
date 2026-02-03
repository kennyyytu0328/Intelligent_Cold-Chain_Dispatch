"""
Route API endpoints.
"""
from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.database import get_async_session
from app.models import Route, RouteStop, RouteStatus
from app.schemas.route import (
    RouteResponse,
    RouteListResponse,
    RouteStopResponse,
    RouteStopUpdate,
    RouteSummary,
)

router = APIRouter()


@router.get("", response_model=RouteListResponse)
async def list_routes(
    plan_date: Optional[date] = None,
    status: Optional[RouteStatus] = None,
    vehicle_id: Optional[UUID] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    session: AsyncSession = Depends(get_async_session),
):
    """
    List all routes with optional filtering.

    - **plan_date**: Filter by planning date
    - **status**: Filter by route status
    - **vehicle_id**: Filter by assigned vehicle
    """
    query = select(Route).options(selectinload(Route.stops))

    if plan_date:
        query = query.where(Route.plan_date == plan_date)
    if status:
        query = query.where(Route.status == status)
    if vehicle_id:
        query = query.where(Route.vehicle_id == vehicle_id)

    query = query.order_by(Route.plan_date.desc(), Route.created_at.desc())
    query = query.offset(skip).limit(limit)

    result = await session.execute(query)
    routes = result.scalars().unique().all()

    # Get total count
    count_query = select(func.count(Route.id))
    if plan_date:
        count_query = count_query.where(Route.plan_date == plan_date)
    if status:
        count_query = count_query.where(Route.status == status)
    if vehicle_id:
        count_query = count_query.where(Route.vehicle_id == vehicle_id)
    total = await session.scalar(count_query)

    return RouteListResponse(
        items=[_route_to_response(r) for r in routes],
        total=total,
    )


@router.get("/map-data")
async def get_routes_for_map(
    plan_date: date,
    job_id: Optional[UUID] = None,
    session: AsyncSession = Depends(get_async_session),
):
    """
    Get routes with coordinates for map visualization.

    Returns route data with lat/lon extracted from geometry for frontend map display.
    """
    from geoalchemy2.functions import ST_X, ST_Y
    from sqlalchemy.orm import selectinload

    query = (
        select(Route)
        .options(
            selectinload(Route.stops).selectinload(RouteStop.shipment),
            selectinload(Route.vehicle),
        )
        .where(Route.plan_date == plan_date)
    )

    if job_id:
        query = query.where(Route.optimization_job_id == job_id)

    result = await session.execute(query)
    routes = result.scalars().unique().all()

    if not routes:
        return {"routes": [], "depot": None}

    # Get depot coordinates from first route
    depot = None
    first_route = routes[0]
    if first_route.depot_location:
        depot_result = await session.execute(
            select(
                ST_X(Route.depot_location).label("lon"),
                ST_Y(Route.depot_location).label("lat"),
            ).where(Route.id == first_route.id)
        )
        depot_row = depot_result.first()
        if depot_row:
            depot = {"lat": float(depot_row.lat), "lon": float(depot_row.lon)}

    map_routes = []
    for route in routes:
        stops_data = []
        for stop in sorted(route.stops, key=lambda s: s.sequence_number):
            # Extract lat/lon from geometry
            coord_result = await session.execute(
                select(
                    ST_X(RouteStop.location).label("lon"),
                    ST_Y(RouteStop.location).label("lat"),
                ).where(RouteStop.id == stop.id)
            )
            coord = coord_result.first()

            stops_data.append({
                "sequence": stop.sequence_number,
                "shipmentId": str(stop.shipment_id),
                "customerName": stop.shipment.order_number if stop.shipment else "Unknown",
                "address": stop.address,
                "lat": coord.lat if coord else 0,
                "lon": coord.lon if coord else 0,
                "arrivalTime": stop.expected_arrival_at.strftime("%H:%M") if stop.expected_arrival_at else "",
                "departureTime": stop.expected_departure_at.strftime("%H:%M") if stop.expected_departure_at else "",
                "temperature": float(stop.predicted_arrival_temp),
                "tempLimit": float(stop.shipment.temp_limit_upper) if stop.shipment and stop.shipment.temp_limit_upper else 8.0,
                "feasible": stop.is_temp_feasible,
            })

        map_routes.append({
            "vehicleId": str(route.vehicle_id),
            "licensePlate": route.vehicle.license_plate if route.vehicle else f"Vehicle-{route.vehicle_id}",
            "color": "",  # Frontend will assign
            "totalDistance": float(route.total_distance or 0),
            "totalTime": route.total_duration or 0,
            "stops": stops_data,
        })

    return {"routes": map_routes, "depot": depot}


@router.get("/summary")
async def get_routes_summary(
    plan_date: date,
    session: AsyncSession = Depends(get_async_session),
):
    """
    Get summary of routes for a specific date.

    Returns aggregate metrics for planning overview.
    """
    query = select(Route).where(Route.plan_date == plan_date)
    result = await session.execute(query)
    routes = result.scalars().all()

    if not routes:
        return {
            "plan_date": str(plan_date),
            "total_routes": 0,
            "total_vehicles": 0,
            "total_stops": 0,
            "total_distance_km": 0,
            "routes": [],
        }

    return {
        "plan_date": str(plan_date),
        "total_routes": len(routes),
        "total_vehicles": len(routes),
        "total_stops": sum(r.total_stops for r in routes),
        "total_distance_km": sum(float(r.total_distance or 0) for r in routes),
        "total_duration_minutes": sum(r.total_duration or 0 for r in routes),
        "temperature_feasible_count": sum(
            1 for r in routes
            if r.predicted_max_temp and r.predicted_max_temp <= 5
        ),
        "routes": [
            {
                "id": str(r.id),
                "route_code": r.route_code,
                "vehicle_id": str(r.vehicle_id),
                "driver_name": r.driver_name,
                "status": r.status.value,
                "total_stops": r.total_stops,
                "total_distance_km": float(r.total_distance or 0),
                "predicted_max_temp": float(r.predicted_max_temp or 0),
            }
            for r in routes
        ],
    }


@router.get("/{route_id}", response_model=RouteResponse)
async def get_route(
    route_id: UUID,
    session: AsyncSession = Depends(get_async_session),
):
    """
    Get a specific route by ID with all stops.

    Includes temperature predictions at each stop.
    """
    result = await session.execute(
        select(Route)
        .options(selectinload(Route.stops))
        .where(Route.id == route_id)
    )
    route = result.scalar_one_or_none()

    if not route:
        raise HTTPException(status_code=404, detail="Route not found")

    return _route_to_response(route)


@router.get("/{route_id}/temperature-analysis")
async def get_route_temperature_analysis(
    route_id: UUID,
    session: AsyncSession = Depends(get_async_session),
):
    """
    Get detailed temperature analysis for a route.

    Shows temperature progression through the route with all
    thermodynamic calculations.
    """
    result = await session.execute(
        select(Route)
        .options(selectinload(Route.stops))
        .where(Route.id == route_id)
    )
    route = result.scalar_one_or_none()

    if not route:
        raise HTTPException(status_code=404, detail="Route not found")

    # Sort stops by sequence
    stops = sorted(route.stops, key=lambda s: s.sequence_number)

    analysis = {
        "route_id": str(route.id),
        "route_code": route.route_code,
        "vehicle_license": route.vehicle.license_plate if route.vehicle else None,
        "initial_temperature": float(route.initial_temperature),
        "final_temperature": float(route.predicted_final_temp or 0),
        "max_temperature": float(route.predicted_max_temp or 0),
        "is_feasible": all(s.is_temp_feasible for s in stops),
        "stops": [],
    }

    current_temp = float(route.initial_temperature)

    for stop in stops:
        stop_analysis = {
            "sequence": stop.sequence_number,
            "address": stop.address,
            "shipment_id": str(stop.shipment_id),
            "temperature": {
                "before_arrival": current_temp,
                "transit_rise": float(stop.transit_temp_rise or 0),
                "cooling_applied": float(stop.cooling_applied or 0),
                "arrival_temp": float(stop.predicted_arrival_temp),
                "door_rise": float(stop.service_temp_rise or 0),
                "departure_temp": float(stop.predicted_departure_temp or 0),
            },
            "constraints": {
                "temp_limit_upper": float(stop.shipment.temp_limit_upper) if stop.shipment else None,
                "is_feasible": stop.is_temp_feasible,
                "violation_amount": max(
                    0,
                    float(stop.predicted_arrival_temp) -
                    float(stop.shipment.temp_limit_upper if stop.shipment else 999)
                ),
            },
            "timing": {
                "arrival_time": stop.expected_arrival_at.isoformat() if stop.expected_arrival_at else None,
                "service_duration_minutes": stop.shipment.service_duration if stop.shipment else 15,
                "departure_time": stop.expected_departure_at.isoformat() if stop.expected_departure_at else None,
            },
        }

        analysis["stops"].append(stop_analysis)
        current_temp = float(stop.predicted_departure_temp or 0)

    return analysis


@router.patch("/{route_id}/status")
async def update_route_status(
    route_id: UUID,
    status: RouteStatus,
    session: AsyncSession = Depends(get_async_session),
):
    """Update route status."""
    result = await session.execute(
        select(Route).where(Route.id == route_id)
    )
    route = result.scalar_one_or_none()

    if not route:
        raise HTTPException(status_code=404, detail="Route not found")

    route.status = status
    await session.flush()

    return {"id": str(route.id), "status": route.status.value}


@router.patch("/{route_id}/stops/{stop_id}")
async def update_route_stop(
    route_id: UUID,
    stop_id: UUID,
    data: RouteStopUpdate,
    session: AsyncSession = Depends(get_async_session),
):
    """
    Update a route stop (typically during execution).

    Used to record actual arrival times and temperatures.
    """
    result = await session.execute(
        select(RouteStop).where(
            RouteStop.id == stop_id,
            RouteStop.route_id == route_id,
        )
    )
    stop = result.scalar_one_or_none()

    if not stop:
        raise HTTPException(status_code=404, detail="Route stop not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(stop, field, value)

    await session.flush()
    await session.refresh(stop)

    return RouteStopResponse.model_validate(stop)


def _route_to_response(route: Route) -> RouteResponse:
    """Convert Route model to response schema."""
    stops = sorted(route.stops, key=lambda s: s.sequence_number)

    return RouteResponse(
        id=route.id,
        route_code=route.route_code,
        plan_date=route.plan_date,
        vehicle_id=route.vehicle_id,
        driver_id=route.driver_id,
        driver_name=route.driver_name,
        status=route.status,
        total_stops=route.total_stops,
        total_distance=route.total_distance,
        total_duration=route.total_duration,
        total_weight=route.total_weight,
        total_volume=route.total_volume,
        initial_temperature=route.initial_temperature,
        predicted_final_temp=route.predicted_final_temp,
        predicted_max_temp=route.predicted_max_temp,
        planned_departure_at=route.planned_departure_at,
        planned_return_at=route.planned_return_at,
        actual_departure_at=route.actual_departure_at,
        actual_return_at=route.actual_return_at,
        depot_address=route.depot_address,
        optimization_job_id=route.optimization_job_id,
        optimization_cost=route.optimization_cost,
        algorithm_version=route.algorithm_version,
        stops=[RouteStopResponse.model_validate(s) for s in stops],
        created_at=route.created_at,
        updated_at=route.updated_at,
    )
