"""
Optimization API endpoints.

Provides asynchronous VRP optimization via Celery.
"""
from datetime import date
from typing import Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_async_session
from app.models import (
    OptimizationJob,
    Vehicle,
    Shipment,
    VehicleStatus,
    ShipmentStatus,
)
from app.schemas.optimization import (
    OptimizationRequest,
    OptimizationResponse,
    OptimizationStatusResponse,
    OptimizationResultSummary,
)
from app.core.celery_app import celery_app
from app.services.tasks import run_optimization

router = APIRouter()


@router.post("", response_model=OptimizationResponse, status_code=202)
async def create_optimization_job(
    request: OptimizationRequest,
    session: AsyncSession = Depends(get_async_session),
):
    """
    Start a new VRP optimization job.

    The optimization runs asynchronously via Celery. This endpoint returns
    immediately with a job_id that can be used to poll for status.

    ## Process Flow

    1. API validates request and counts available resources
    2. Creates OptimizationJob record in database
    3. Dispatches Celery task
    4. Returns job_id for status polling

    ## Optimization Parameters

    - **time_limit_seconds**: Maximum solver time (default: 300)
    - **strategy**: MINIMIZE_VEHICLES or MINIMIZE_DISTANCE
    - **ambient_temperature**: Outside temperature for calculations
    - **initial_vehicle_temp**: Starting compartment temperature

    ## Polling for Results

    Use `GET /optimization/{job_id}` to check status and retrieve results.
    """
    # Count available vehicles
    vehicle_query = select(func.count(Vehicle.id)).where(
        Vehicle.status == VehicleStatus.AVAILABLE
    )
    if request.vehicle_ids:
        vehicle_query = vehicle_query.where(Vehicle.id.in_(request.vehicle_ids))
    vehicle_count = await session.scalar(vehicle_query)

    if vehicle_count == 0:
        raise HTTPException(
            status_code=400,
            detail="No available vehicles found for optimization",
        )

    # Count pending shipments
    shipment_query = select(func.count(Shipment.id)).where(
        Shipment.status == ShipmentStatus.PENDING
    )
    if request.shipment_ids:
        shipment_query = shipment_query.where(Shipment.id.in_(request.shipment_ids))
    shipment_count = await session.scalar(shipment_query)

    if shipment_count == 0:
        raise HTTPException(
            status_code=400,
            detail="No pending shipments found for optimization",
        )

    # Create optimization job record
    job_id = uuid4()

    # Prepare parameters - convert Decimals to float for JSON serialization
    from decimal import Decimal
    raw_params = request.parameters.model_dump()
    parameters = {
        k: float(v) if isinstance(v, Decimal) else v
        for k, v in raw_params.items()
    }
    if request.depot_latitude:
        parameters["depot_latitude"] = float(request.depot_latitude)
    if request.depot_longitude:
        parameters["depot_longitude"] = float(request.depot_longitude)
    if request.depot_address:
        parameters["depot_address"] = request.depot_address

    # Add planned departure time
    parameters["planned_departure_time"] = request.planned_departure_time

    job = OptimizationJob(
        id=job_id,
        plan_date=request.plan_date,
        vehicle_ids=[UUID(str(vid)) for vid in request.vehicle_ids] if request.vehicle_ids else None,
        shipment_ids=[UUID(str(sid)) for sid in request.shipment_ids] if request.shipment_ids else None,
        parameters=parameters,
        status="PENDING",
    )

    session.add(job)
    await session.flush()

    # Dispatch Celery task
    celery_task = run_optimization.delay(
        job_id=str(job_id),
        plan_date_str=request.plan_date.isoformat(),
        vehicle_ids=[str(vid) for vid in request.vehicle_ids] if request.vehicle_ids else None,
        shipment_ids=[str(sid) for sid in request.shipment_ids] if request.shipment_ids else None,
        parameters=parameters,
    )

    # Update job with Celery task ID
    job.celery_task_id = celery_task.id
    await session.flush()

    return OptimizationResponse(
        job_id=job_id,
        celery_task_id=celery_task.id,
        status="PENDING",
        message="Optimization job queued successfully. Use GET /optimization/{job_id} to check status.",
        shipment_count=shipment_count,
        vehicle_count=vehicle_count,
    )


@router.get("/{job_id}", response_model=OptimizationStatusResponse)
async def get_optimization_status(
    job_id: UUID,
    session: AsyncSession = Depends(get_async_session),
):
    """
    Get optimization job status and results.

    ## Status Values

    - **PENDING**: Job queued, waiting for worker
    - **RUNNING**: Worker is executing OR-Tools solver
    - **COMPLETED**: Optimization finished successfully
    - **FAILED**: Error during optimization
    - **CANCELLED**: Job was cancelled

    ## Results

    When status is COMPLETED, the response includes:
    - route_ids: UUIDs of created routes
    - result_summary: Metrics and statistics
    - unassigned_shipment_ids: Shipments that couldn't be assigned
    """
    result = await session.execute(
        select(OptimizationJob).where(OptimizationJob.id == job_id)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Optimization job not found")

    # Calculate duration if available
    duration = None
    if job.started_at and job.completed_at:
        duration = (job.completed_at - job.started_at).total_seconds()

    # Parse result summary
    result_summary = None
    if job.result_summary:
        result_summary = OptimizationResultSummary(
            routes_created=job.result_summary.get("routes_created", 0),
            shipments_assigned=job.result_summary.get("shipments_assigned", 0),
            shipments_unassigned=job.result_summary.get("shipments_unassigned", 0),
            total_distance_km=job.result_summary.get("total_distance_km"),
            total_duration_minutes=job.result_summary.get("total_duration_minutes"),
            total_cost=job.result_summary.get("total_cost"),
            solver_status=job.result_summary.get("solver_status", ""),
            solver_time_seconds=job.result_summary.get("solver_time_seconds"),
        )

    return OptimizationStatusResponse(
        job_id=job.id,
        celery_task_id=job.celery_task_id,
        status=job.status,
        progress=job.progress,
        plan_date=job.plan_date,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        duration_seconds=duration,
        result_summary=result_summary,
        route_ids=job.route_ids,
        unassigned_shipment_ids=job.unassigned_shipment_ids,
        error_message=job.error_message,
    )


@router.get("/{job_id}/violations")
async def get_optimization_violations(
    job_id: UUID,
    session: AsyncSession = Depends(get_async_session),
):
    """
    Get detailed violation information for an optimization job.

    Returns temperature violations and unassigned shipment details.
    """
    from app.models import Route, RouteStop, Shipment

    # Get the job
    job_result = await session.execute(
        select(OptimizationJob).where(OptimizationJob.id == job_id)
    )
    job = job_result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Optimization job not found")

    violations = {
        "temperature_violations": [],
        "unassigned_shipments": [],
        "summary": {
            "total_temp_violations": 0,
            "total_unassigned": 0,
        }
    }

    # Get temperature violations from route stops
    if job.route_ids:
        stops_result = await session.execute(
            select(RouteStop, Shipment)
            .join(Shipment, RouteStop.shipment_id == Shipment.id)
            .join(Route, RouteStop.route_id == Route.id)
            .where(Route.optimization_job_id == job_id)
            .where(RouteStop.is_temp_feasible == False)
        )

        for stop, shipment in stops_result.all():
            violations["temperature_violations"].append({
                "order_number": shipment.order_number,
                "address": shipment.delivery_address,
                "sequence": stop.sequence_number,
                "predicted_temp": float(stop.predicted_arrival_temp),
                "temp_limit": float(shipment.temp_limit_upper),
                "violation_amount": float(stop.predicted_arrival_temp - shipment.temp_limit_upper),
                "sla_tier": shipment.sla_tier.value,
            })

    # Get unassigned shipment details with analysis
    if job.unassigned_shipment_ids:
        unassigned_result = await session.execute(
            select(Shipment).where(Shipment.id.in_(job.unassigned_shipment_ids))
        )

        # Get job parameters for analysis
        job_params = job.parameters or {}
        planned_departure = job_params.get("planned_departure_time", "06:00")
        dep_parts = planned_departure.split(":")
        departure_minutes = int(dep_parts[0]) * 60 + int(dep_parts[1])

        for shipment in unassigned_result.scalars().all():
            time_windows = shipment.time_windows or []
            tw_str = ", ".join([f"{tw['start']}-{tw['end']}" for tw in time_windows])

            # Analyze likely reasons for being unassigned
            likely_reasons = []

            # Check time window feasibility
            for tw in time_windows:
                tw_end_parts = tw['end'].split(":")
                tw_end_minutes = int(tw_end_parts[0]) * 60 + int(tw_end_parts[1])
                tw_start_parts = tw['start'].split(":")
                tw_start_minutes = int(tw_start_parts[0]) * 60 + int(tw_start_parts[1])

                # If time window ends before or shortly after departure, likely unreachable
                if tw_end_minutes < departure_minutes + 30:  # 30 min buffer for travel
                    likely_reasons.append({
                        "type": "TIME_WINDOW",
                        "message": f"Time window ends at {tw['end']}, but departure is at {planned_departure}",
                        "parameter": "planned_departure_time",
                        "current_value": planned_departure,
                        "constraint_value": tw['end'],
                    })

            # Check if STRICT SLA might be causing issues
            if shipment.sla_tier.value == "STRICT" and not likely_reasons:
                likely_reasons.append({
                    "type": "STRICT_SLA",
                    "message": "STRICT SLA cannot be satisfied with current constraints",
                    "parameter": "sla_tier",
                    "current_value": "STRICT",
                    "constraint_value": "Must meet all constraints",
                })

            # Check temperature constraint
            temp_limit = float(shipment.temp_limit_upper)
            if temp_limit <= 4.0:  # Very strict temperature
                likely_reasons.append({
                    "type": "TEMPERATURE",
                    "message": f"Strict temperature limit ({temp_limit}°C) may be difficult to maintain",
                    "parameter": "temp_limit_upper",
                    "current_value": f"{temp_limit}°C",
                    "constraint_value": "Requires excellent insulation",
                })

            # If no specific reason found
            if not likely_reasons:
                likely_reasons.append({
                    "type": "CAPACITY_OR_ROUTING",
                    "message": "Could not fit into any route due to capacity or routing constraints",
                    "parameter": "multiple",
                    "current_value": "N/A",
                    "constraint_value": "Vehicle capacity or route optimization",
                })

            violations["unassigned_shipments"].append({
                "order_number": shipment.order_number,
                "address": shipment.delivery_address,
                "time_windows": tw_str,
                "temp_limit": float(shipment.temp_limit_upper),
                "sla_tier": shipment.sla_tier.value,
                "weight_kg": float(shipment.weight),
                "likely_reasons": likely_reasons,
            })

    violations["summary"]["total_temp_violations"] = len(violations["temperature_violations"])
    violations["summary"]["total_unassigned"] = len(violations["unassigned_shipments"])

    return violations


@router.get("")
async def list_optimization_jobs(
    plan_date: Optional[date] = None,
    status: Optional[str] = None,
    limit: int = 20,
    session: AsyncSession = Depends(get_async_session),
):
    """List recent optimization jobs."""
    query = select(OptimizationJob)

    if plan_date:
        query = query.where(OptimizationJob.plan_date == plan_date)
    if status:
        query = query.where(OptimizationJob.status == status)

    query = query.order_by(OptimizationJob.created_at.desc()).limit(limit)

    result = await session.execute(query)
    jobs = result.scalars().all()

    return {
        "jobs": [
            {
                "id": str(job.id),
                "celery_task_id": job.celery_task_id,
                "status": job.status,
                "plan_date": str(job.plan_date),
                "created_at": job.created_at.isoformat(),
                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                "routes_created": job.result_summary.get("routes_created", 0) if job.result_summary else 0,
            }
            for job in jobs
        ],
        "total": len(jobs),
    }


@router.post("/{job_id}/cancel")
async def cancel_optimization_job(
    job_id: UUID,
    session: AsyncSession = Depends(get_async_session),
):
    """
    Cancel a pending or running optimization job.

    Note: Cannot cancel completed or already failed jobs.
    """
    result = await session.execute(
        select(OptimizationJob).where(OptimizationJob.id == job_id)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Optimization job not found")

    if job.status in ("COMPLETED", "FAILED", "CANCELLED"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel job with status {job.status}",
        )

    # Revoke Celery task
    if job.celery_task_id:
        celery_app.control.revoke(job.celery_task_id, terminate=True)

    # Update job status
    job.status = "CANCELLED"
    await session.flush()

    return {"id": str(job.id), "status": "CANCELLED", "message": "Job cancelled"}


@router.post("/quick-estimate")
async def quick_optimization_estimate(
    plan_date: date,
    session: AsyncSession = Depends(get_async_session),
):
    """
    Get a quick estimate for optimization without running the full solver.

    Provides rough metrics to help plan resource allocation.
    """
    # Count vehicles
    vehicle_result = await session.execute(
        select(Vehicle).where(Vehicle.status == VehicleStatus.AVAILABLE)
    )
    vehicles = vehicle_result.scalars().all()

    # Count shipments
    shipment_result = await session.execute(
        select(Shipment).where(Shipment.status == ShipmentStatus.PENDING)
    )
    shipments = shipment_result.scalars().all()

    if not vehicles or not shipments:
        return {
            "plan_date": str(plan_date),
            "is_feasible": False,
            "reason": "No available vehicles or pending shipments",
        }

    total_weight = sum(float(s.weight) for s in shipments)
    total_volume = sum(float(s.volume or 0) for s in shipments)
    total_capacity_weight = sum(float(v.capacity_weight) for v in vehicles)
    total_capacity_volume = sum(float(v.capacity_volume) for v in vehicles)

    strict_count = sum(1 for s in shipments if s.sla_tier.value == "STRICT")

    # Rough estimate: can we fit all shipments?
    weight_utilization = total_weight / total_capacity_weight if total_capacity_weight > 0 else 999
    volume_utilization = total_volume / total_capacity_volume if total_capacity_volume > 0 else 999

    min_vehicles_needed = max(
        int(weight_utilization * len(vehicles)) + 1,
        int(volume_utilization * len(vehicles)) + 1,
    )

    return {
        "plan_date": str(plan_date),
        "resources": {
            "available_vehicles": len(vehicles),
            "pending_shipments": len(shipments),
            "strict_sla_shipments": strict_count,
        },
        "capacity": {
            "total_weight_kg": total_weight,
            "total_volume_m3": total_volume,
            "fleet_weight_capacity_kg": total_capacity_weight,
            "fleet_volume_capacity_m3": total_capacity_volume,
            "weight_utilization_pct": round(weight_utilization * 100, 1),
            "volume_utilization_pct": round(volume_utilization * 100, 1),
        },
        "estimate": {
            "min_vehicles_needed": min(min_vehicles_needed, len(vehicles)),
            "is_likely_feasible": weight_utilization <= 1.0 and volume_utilization <= 1.0,
            "recommendation": (
                "Sufficient capacity"
                if weight_utilization <= 0.9 and volume_utilization <= 0.9
                else "Near capacity - consider adding vehicles"
                if weight_utilization <= 1.0 and volume_utilization <= 1.0
                else "Over capacity - some shipments may not be assigned"
            ),
        },
    }
