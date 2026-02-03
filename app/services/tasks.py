"""
Celery tasks for ICCDDS.

Contains the main optimization task that runs OR-Tools solver asynchronously.
"""
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Optional, Any
from uuid import UUID
import logging
import traceback
import threading

from celery import shared_task
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.celery_app import celery_app
from app.services.solver import (
    ColdChainVRPSolver,
    build_vrp_data_model,
    SolverResult,
)

logger = logging.getLogger(__name__)


def _run_progress_updater(
    engine,
    job_id: str,
    time_limit_seconds: int,
    stop_event: threading.Event,
    update_interval: int = 10,
):
    """
    Background thread to update job progress based on elapsed time.

    Args:
        engine: SQLAlchemy engine for database connection
        job_id: UUID of the optimization job
        time_limit_seconds: Solver time limit for progress calculation
        stop_event: Event to signal thread to stop
        update_interval: Seconds between progress updates (default 10s)
    """
    from app.models import OptimizationJob

    logger.info(f"Progress updater started for job {job_id}")
    start_time = datetime.now()
    last_logged_progress = -1

    while not stop_event.is_set():
        elapsed = (datetime.now() - start_time).total_seconds()
        # Calculate progress: cap at 95% until solve completes
        progress = min(int((elapsed / time_limit_seconds) * 95), 95)

        try:
            with Session(engine) as session:
                stmt = (
                    update(OptimizationJob)
                    .where(OptimizationJob.id == UUID(job_id))
                    .values(progress=progress, updated_at=datetime.now())
                )
                session.execute(stmt)
                session.commit()
                # Only log when progress changes by 10% or more
                if progress - last_logged_progress >= 10:
                    logger.info(f"Job {job_id} progress: {progress}%")
                    last_logged_progress = progress
        except Exception as e:
            logger.error(f"Failed to update progress for job {job_id}: {e}")

        # Wait for next update or stop signal
        stop_event.wait(update_interval)

    logger.debug(f"Progress updater stopped for job {job_id}")

# Create sync engine for Celery workers (they can't use async)
sync_engine = create_engine(
    settings.database_url_sync,
    pool_size=5,
    max_overflow=10,
)


@celery_app.task(
    bind=True,
    name="app.services.tasks.run_optimization",
    queue="optimization",
    max_retries=2,
    soft_time_limit=settings.default_solver_time_limit + 60,
)
def run_optimization(
    self,
    job_id: str,
    plan_date_str: str,
    vehicle_ids: Optional[list[str]] = None,
    shipment_ids: Optional[list[str]] = None,
    parameters: Optional[dict] = None,
) -> dict:
    """
    Run VRP optimization as a Celery task.

    This task:
    1. Loads vehicles and shipments from database
    2. Builds the VRP data model
    3. Runs the OR-Tools solver
    4. Saves results back to database
    5. Returns summary

    Args:
        job_id: UUID of the optimization job
        plan_date_str: Date string (YYYY-MM-DD)
        vehicle_ids: Optional list of vehicle UUIDs to use
        shipment_ids: Optional list of shipment UUIDs to optimize
        parameters: Algorithm parameters dict

    Returns:
        Result summary dict
    """
    logger.info(f"Starting optimization task for job {job_id}")

    # Parse parameters
    params = parameters or {}
    plan_date = datetime.strptime(plan_date_str, "%Y-%m-%d").date()

    # Default parameters
    time_limit = params.get("time_limit_seconds", settings.default_solver_time_limit)
    ambient_temp = float(params.get("ambient_temperature", settings.default_ambient_temperature))
    initial_temp = float(params.get("initial_vehicle_temp", settings.default_initial_vehicle_temp))
    strategy = params.get("strategy", "MINIMIZE_VEHICLES")

    # Planned departure time (HH:MM string, default 06:00)
    planned_departure_time = params.get("planned_departure_time", "06:00")

    # Depot location
    depot_lat = float(params.get("depot_latitude", settings.default_depot_latitude))
    depot_lon = float(params.get("depot_longitude", settings.default_depot_longitude))
    depot_address = params.get("depot_address", settings.default_depot_address)

    with Session(sync_engine) as session:
        try:
            # Update job status to RUNNING with initial progress
            _update_job_status(session, job_id, "RUNNING", started_at=datetime.now(), progress=5)

            # Load vehicles
            vehicles = _load_vehicles(session, vehicle_ids)
            if not vehicles:
                raise ValueError("No available vehicles found")

            # Load shipments
            shipments = _load_shipments(session, shipment_ids)
            if not shipments:
                raise ValueError("No pending shipments found")

            logger.info(f"Loaded {len(vehicles)} vehicles and {len(shipments)} shipments")

            # Build VRP data model
            data_model = build_vrp_data_model(
                vehicles=vehicles,
                shipments=shipments,
                depot_lat=depot_lat,
                depot_lon=depot_lon,
                depot_address=depot_address,
                ambient_temperature=ambient_temp,
                initial_vehicle_temp=initial_temp,
                average_speed_kmh=settings.average_speed_kmh,
                time_limit_seconds=time_limit,
                strategy=strategy,
                planned_departure_time=planned_departure_time,
            )

            # Start progress updater thread
            stop_event = threading.Event()
            progress_thread = threading.Thread(
                target=_run_progress_updater,
                args=(sync_engine, job_id, time_limit, stop_event),
                daemon=True,
            )
            progress_thread.start()

            # Run solver
            try:
                solver = ColdChainVRPSolver(data_model, plan_date)
                result = solver.solve()
            finally:
                # Stop progress updater thread
                stop_event.set()
                progress_thread.join(timeout=2)

            # Save routes to database
            route_ids = _save_routes(session, job_id, plan_date, result, data_model)

            # Update shipment statuses
            _update_shipment_statuses(session, result, route_ids)

            # Build result summary
            result_summary = {
                "routes_created": len(result.routes),
                "shipments_assigned": result.shipments_assigned,
                "shipments_unassigned": len(result.unassigned_shipment_ids),
                "total_distance_km": result.total_distance_meters / 1000,
                "total_duration_minutes": result.total_duration_minutes,
                "total_cost": result.total_cost,
                "solver_status": result.status,
                "solver_time_seconds": result.solver_time_seconds,
            }

            # Update job as completed
            _update_job_completed(
                session,
                job_id,
                route_ids=route_ids,
                result_summary=result_summary,
                unassigned_ids=result.unassigned_shipment_ids,
            )

            session.commit()

            logger.info(f"Optimization completed for job {job_id}: {result_summary}")
            return result_summary

        except Exception as e:
            session.rollback()
            error_msg = str(e)
            error_tb = traceback.format_exc()

            logger.error(f"Optimization failed for job {job_id}: {error_msg}")

            # Update job as failed
            _update_job_failed(session, job_id, error_msg, error_tb)
            session.commit()

            # Re-raise for Celery retry mechanism
            raise


def _update_job_status(
    session: Session,
    job_id: str,
    status: str,
    started_at: Optional[datetime] = None,
    progress: Optional[int] = None,
):
    """Update optimization job status."""
    from app.models import OptimizationJob

    values = {"status": status, "updated_at": datetime.now()}
    if started_at:
        values["started_at"] = started_at
    if progress is not None:
        values["progress"] = progress

    stmt = (
        update(OptimizationJob)
        .where(OptimizationJob.id == UUID(job_id))
        .values(**values)
    )
    session.execute(stmt)
    session.commit()  # Commit immediately so API can see the update


def _update_job_completed(
    session: Session,
    job_id: str,
    route_ids: list[str],
    result_summary: dict,
    unassigned_ids: list[str],
):
    """Update job as completed with results."""
    from app.models import OptimizationJob

    stmt = (
        update(OptimizationJob)
        .where(OptimizationJob.id == UUID(job_id))
        .values(
            status="COMPLETED",
            progress=100,
            completed_at=datetime.now(),
            updated_at=datetime.now(),
            route_ids=[UUID(rid) for rid in route_ids],
            result_summary=result_summary,
            unassigned_shipment_ids=[UUID(sid) for sid in unassigned_ids] if unassigned_ids else None,
        )
    )
    session.execute(stmt)


def _update_job_failed(
    session: Session,
    job_id: str,
    error_message: str,
    error_traceback: str,
):
    """Update job as failed with error details."""
    from app.models import OptimizationJob

    stmt = (
        update(OptimizationJob)
        .where(OptimizationJob.id == UUID(job_id))
        .values(
            status="FAILED",
            completed_at=datetime.now(),
            updated_at=datetime.now(),
            error_message=error_message,
            error_traceback=error_traceback,
        )
    )
    session.execute(stmt)


def _load_vehicles(
    session: Session,
    vehicle_ids: Optional[list[str]] = None,
) -> list[dict]:
    """Load available vehicles from database."""
    from app.models import Vehicle, VehicleStatus

    query = select(Vehicle).where(Vehicle.status == VehicleStatus.AVAILABLE)

    if vehicle_ids:
        query = query.where(Vehicle.id.in_([UUID(vid) for vid in vehicle_ids]))

    result = session.execute(query)
    vehicles = result.scalars().all()

    return [
        {
            "id": str(v.id),
            "license_plate": v.license_plate,
            "driver_id": str(v.driver_id) if v.driver_id else None,
            "driver_name": v.driver_name,
            "capacity_weight": float(v.capacity_weight),
            "capacity_volume": float(v.capacity_volume),
            "k_value": float(v.k_value),
            "door_coefficient": float(v.door_coefficient),
            "has_strip_curtains": v.has_strip_curtains,
            "cooling_rate": float(v.cooling_rate),
        }
        for v in vehicles
    ]


def _load_shipments(
    session: Session,
    shipment_ids: Optional[list[str]] = None,
) -> list[dict]:
    """Load pending shipments from database."""
    from app.models import Shipment, ShipmentStatus

    query = select(Shipment).where(Shipment.status == ShipmentStatus.PENDING)

    if shipment_ids:
        query = query.where(Shipment.id.in_([UUID(sid) for sid in shipment_ids]))

    result = session.execute(query)
    shipments = result.scalars().all()

    return [
        {
            "id": str(s.id),
            "order_number": s.order_number,
            "customer_id": str(s.customer_id) if s.customer_id else None,
            "delivery_address": s.delivery_address,
            "latitude": float(s.latitude),
            "longitude": float(s.longitude),
            "time_windows": s.time_windows,
            "sla_tier": s.sla_tier.value,
            "temp_limit_upper": float(s.temp_limit_upper),
            "temp_limit_lower": float(s.temp_limit_lower) if s.temp_limit_lower else None,
            "service_duration": s.service_duration,
            "weight": float(s.weight),
            "volume": float(s.volume) if s.volume else 0,
            "priority": s.priority,
        }
        for s in shipments
    ]


def _save_routes(
    session: Session,
    job_id: str,
    plan_date: date,
    result: SolverResult,
    data_model,
) -> list[str]:
    """Save optimized routes to database."""
    from app.models import Route, RouteStop, RouteStatus
    from uuid import uuid4
    from geoalchemy2.elements import WKTElement

    route_ids = []

    for idx, route_result in enumerate(result.routes):
        # Create route with unique code (include job ID suffix to avoid conflicts)
        route_id = uuid4()
        job_suffix = job_id[-8:]  # Last 8 chars of job ID for uniqueness
        route_code = f"R-{plan_date.strftime('%Y%m%d')}-{route_result.license_plate}-{job_suffix}"

        # Get depot location
        depot = data_model.nodes[0]

        route = Route(
            id=route_id,
            route_code=route_code,
            plan_date=plan_date,
            vehicle_id=UUID(route_result.vehicle_id),
            driver_id=UUID(route_result.driver_id) if route_result.driver_id else None,
            driver_name=route_result.driver_name,
            status=RouteStatus.SCHEDULED,
            total_stops=route_result.num_stops,
            total_distance=Decimal(str(route_result.total_distance_meters / 1000)),
            total_duration=route_result.total_duration_minutes,
            total_weight=Decimal(str(route_result.total_weight_kg)),
            total_volume=Decimal(str(route_result.total_volume_m3)),
            initial_temperature=Decimal(str(route_result.initial_temp)),
            predicted_final_temp=Decimal(str(route_result.final_temp)),
            predicted_max_temp=Decimal(str(route_result.max_temp)),
            planned_departure_at=datetime.combine(
                plan_date,
                datetime.min.time()
            ) + timedelta(minutes=route_result.departure_time_minutes),
            planned_return_at=datetime.combine(
                plan_date,
                datetime.min.time()
            ) + timedelta(minutes=route_result.return_time_minutes),
            depot_address=depot.address,
            depot_location=WKTElement(f"POINT({depot.longitude} {depot.latitude})", srid=4326),
            optimization_job_id=UUID(job_id),
            optimization_cost=Decimal(str(result.total_cost)),
            algorithm_version="1.0.0",
        )
        session.add(route)

        # Create route stops
        for stop in route_result.stops:
            route_stop = RouteStop(
                id=uuid4(),
                route_id=route_id,
                shipment_id=UUID(stop.shipment_id),
                sequence_number=stop.sequence,
                location=WKTElement(f"POINT({stop.longitude} {stop.latitude})", srid=4326),
                address=stop.address,
                expected_arrival_at=datetime.combine(
                    plan_date,
                    datetime.min.time()
                ) + timedelta(minutes=stop.arrival_time_minutes),
                expected_departure_at=datetime.combine(
                    plan_date,
                    datetime.min.time()
                ) + timedelta(minutes=stop.departure_time_minutes),
                target_time_window_index=stop.target_time_window_index,
                slack_minutes=stop.slack_minutes,
                predicted_arrival_temp=Decimal(str(stop.arrival_temp)),
                transit_temp_rise=Decimal(str(stop.transit_temp_rise)),
                service_temp_rise=Decimal(str(stop.door_temp_rise)),
                cooling_applied=Decimal(str(stop.cooling_applied)),
                predicted_departure_temp=Decimal(str(stop.departure_temp)),
                is_temp_feasible=stop.is_temp_feasible,
                distance_from_prev=Decimal(str(stop.distance_from_prev_meters / 1000)),
                travel_time_from_prev=stop.travel_time_from_prev_minutes,
            )
            session.add(route_stop)

        route_ids.append(str(route_id))

    return route_ids


def _update_shipment_statuses(
    session: Session,
    result: SolverResult,
    route_ids: list[str],
):
    """Update shipment statuses based on optimization result."""
    from app.models import Shipment, ShipmentStatus

    # Map shipment IDs to routes
    shipment_route_map = {}
    for route_result, route_id in zip(result.routes, route_ids):
        for stop in route_result.stops:
            shipment_route_map[stop.shipment_id] = (route_id, stop.sequence)

    # Update assigned shipments
    for shipment_id, (route_id, sequence) in shipment_route_map.items():
        stmt = (
            update(Shipment)
            .where(Shipment.id == UUID(shipment_id))
            .values(
                status=ShipmentStatus.ASSIGNED,
                route_id=UUID(route_id),
                route_sequence=sequence,
                updated_at=datetime.now(),
            )
        )
        session.execute(stmt)
