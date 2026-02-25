#!/usr/bin/env python
"""
Seed VehicleHexAffinity and RouteHexStat data from existing routes.

Reads all routes with route_signature populated, then generates realistic
affinity scores per vehicle-cell pair and delivery stats per cell.

Usage:
    python scripts/seed_affinity_data.py
    python scripts/seed_affinity_data.py --dry-run
    python scripts/seed_affinity_data.py --clear   # delete existing data first
"""
import argparse
import asyncio
import logging
import random
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.models.geo import RouteHexStat, VehicleHexAffinity
from app.models.route import Route
from app.models.vehicle import Vehicle

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def seed(dry_run: bool = False, clear: bool = False) -> dict:
    """Generate affinity and hex stat data from existing routes.

    Strategy:
    - Collect all H3 cells from route_signatures across all routes.
    - For each vehicle, assign affinities to cells it has been routed through
      (high score 0.7-0.95) and some neighboring cells (lower score 0.3-0.6).
    - For each cell, create a RouteHexStat with delivery counts derived from
      how many routes pass through it.

    Args:
        dry_run: If True, don't commit changes.
        clear: If True, delete existing affinity/stat data first.

    Returns:
        Dict with counts of created records.
    """
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url), echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    affinities_created = 0
    stats_created = 0

    async with async_session() as session:
        if clear and not dry_run:
            await session.execute(delete(VehicleHexAffinity))
            await session.execute(delete(RouteHexStat))
            logger.info("Cleared existing affinity and hex stat data")

        # Load all routes with signatures
        result = await session.execute(
            select(Route.id, Route.vehicle_id, Route.route_signature)
            .where(Route.route_signature.isnot(None))
        )
        routes = result.all()

        if not routes:
            logger.warning("No routes with route_signature found. Run backfill first.")
            await engine.dispose()
            return {"affinities_created": 0, "stats_created": 0}

        logger.info(f"Found {len(routes)} routes with signatures")

        # Load all vehicles
        vehicle_result = await session.execute(select(Vehicle.id, Vehicle.driver_id))
        vehicles = vehicle_result.all()
        vehicle_ids = [v.id for v in vehicles]

        if not vehicle_ids:
            logger.warning("No vehicles found in database")
            await engine.dispose()
            return {"affinities_created": 0, "stats_created": 0}

        logger.info(f"Found {len(vehicle_ids)} vehicles")

        # Build vehicle -> cells mapping from routes
        vehicle_cells: dict[str, set[str]] = {str(vid): set() for vid in vehicle_ids}
        cell_delivery_count: dict[str, int] = {}
        vehicle_driver_map: dict[str, str | None] = {
            str(v.id): str(v.driver_id) if v.driver_id else None
            for v in vehicles
        }

        for route in routes:
            vid = str(route.vehicle_id)
            cells = route.route_signature or []
            if vid in vehicle_cells:
                vehicle_cells[vid].update(cells)
            for cell in cells:
                cell_delivery_count[cell] = cell_delivery_count.get(cell, 0) + 1

        # Collect all unique cells
        all_cells = list(cell_delivery_count.keys())

        if not all_cells:
            logger.warning("No H3 cells found in route signatures")
            await engine.dispose()
            return {"affinities_created": 0, "stats_created": 0}

        logger.info(f"Found {len(all_cells)} unique H3 cells across all routes")

        # Check existing affinities to avoid duplicates
        existing_result = await session.execute(
            select(VehicleHexAffinity.vehicle_id, VehicleHexAffinity.h3_index)
        )
        existing_pairs = {(str(r[0]), r[1]) for r in existing_result.all()}

        # Create VehicleHexAffinity records
        now = datetime.now(timezone.utc)

        for vid_str in vehicle_cells:
            own_cells = vehicle_cells[vid_str]
            driver_id = vehicle_driver_map.get(vid_str)

            # High affinity for cells this vehicle has actually served
            for cell in own_cells:
                if (vid_str, cell) in existing_pairs:
                    continue
                deliveries = cell_delivery_count.get(cell, 1)
                sample = min(deliveries * random.randint(2, 5), 50)
                affinity = VehicleHexAffinity(
                    id=uuid4(),
                    vehicle_id=vid_str,
                    driver_id=driver_id,
                    h3_index=cell,
                    affinity_score=Decimal(str(round(random.uniform(0.70, 0.95), 3))),
                    sample_size=sample,
                    avg_on_time_rate=Decimal(str(round(random.uniform(0.80, 0.99), 3))),
                    avg_temp_compliance_rate=Decimal(str(round(random.uniform(0.85, 0.99), 3))),
                    last_delivery_at=now,
                    updated_at=now,
                )
                session.add(affinity)
                affinities_created += 1

            # Lower affinity for some cells this vehicle hasn't served
            other_cells = [c for c in all_cells if c not in own_cells]
            sample_others = random.sample(other_cells, min(len(other_cells), 3))
            for cell in sample_others:
                if (vid_str, cell) in existing_pairs:
                    continue
                affinity = VehicleHexAffinity(
                    id=uuid4(),
                    vehicle_id=vid_str,
                    driver_id=driver_id,
                    h3_index=cell,
                    affinity_score=Decimal(str(round(random.uniform(0.30, 0.60), 3))),
                    sample_size=random.randint(1, 5),
                    avg_on_time_rate=Decimal(str(round(random.uniform(0.60, 0.85), 3))),
                    avg_temp_compliance_rate=Decimal(str(round(random.uniform(0.65, 0.90), 3))),
                    last_delivery_at=now,
                    updated_at=now,
                )
                session.add(affinity)
                affinities_created += 1

        # Check existing hex stats to avoid duplicates
        existing_stats = await session.execute(
            select(RouteHexStat.h3_index)
        )
        existing_stat_cells = {r[0] for r in existing_stats.all()}

        # Create RouteHexStat records
        for cell, delivery_count in cell_delivery_count.items():
            if cell in existing_stat_cells:
                continue
            stat = RouteHexStat(
                id=uuid4(),
                h3_index=cell,
                total_deliveries=delivery_count * random.randint(3, 8),
                avg_service_time_minutes=random.randint(5, 20),
                avg_delay_minutes=Decimal(str(round(random.uniform(0, 10), 2))),
                difficulty_factor=Decimal(str(round(random.uniform(0.3, 0.8), 3))),
                updated_at=now,
            )
            session.add(stat)
            stats_created += 1

        if not dry_run:
            await session.commit()
            logger.info(f"Committed {affinities_created} affinities, {stats_created} hex stats")
        else:
            logger.info(
                f"DRY RUN: would create {affinities_created} affinities, "
                f"{stats_created} hex stats"
            )

    await engine.dispose()
    return {"affinities_created": affinities_created, "stats_created": stats_created}


def main():
    parser = argparse.ArgumentParser(
        description="Seed VehicleHexAffinity and RouteHexStat from existing routes"
    )
    parser.add_argument("--dry-run", action="store_true", help="Don't commit changes")
    parser.add_argument("--clear", action="store_true", help="Delete existing data first")
    args = parser.parse_args()

    result = asyncio.run(seed(dry_run=args.dry_run, clear=args.clear))
    logger.info(f"Done: {result}")


if __name__ == "__main__":
    main()
