#!/usr/bin/env python
"""
Backfill route_signature for existing routes.

Scans routes with null/empty route_signature, decomposes their stops
into H3 cells using GeoProvider, and updates the signature.

Usage:
    python scripts/backfill_route_signatures.py
    python scripts/backfill_route_signatures.py --dry-run
    python scripts/backfill_route_signatures.py --batch-size 50
"""
import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, update, or_, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.models.route import Route, RouteStop
from app.services.geo.provider import get_geo_provider

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def backfill(dry_run: bool = False, batch_size: int = 100) -> dict:
    """Backfill route_signature for routes missing it.

    Args:
        dry_run: If True, don't commit changes.
        batch_size: Number of routes to process per batch.

    Returns:
        Dict with processed count and updated count.
    """
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url), echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    geo = get_geo_provider()
    resolution = settings.h3_resolution

    processed = 0
    updated = 0

    async with async_session() as session:
        # Find routes with null or empty signature
        query = (
            select(Route.id)
            .where(
                or_(
                    Route.route_signature.is_(None),
                    Route.route_signature == text("'[]'::jsonb"),
                )
            )
            .limit(batch_size)
        )

        result = await session.execute(query)
        route_ids = [row[0] for row in result.all()]

        logger.info(f"Found {len(route_ids)} routes to process (batch_size={batch_size})")

        for route_id in route_ids:
            processed += 1

            # Load stops for this route
            stops_result = await session.execute(
                select(RouteStop)
                .where(RouteStop.route_id == route_id)
                .order_by(RouteStop.sequence_number)
            )
            stops = stops_result.scalars().all()

            if not stops:
                logger.warning(f"Route {route_id}: no stops, skipping")
                continue

            # Decompose stop locations to H3 cells
            cells: list[str] = []
            seen: set[str] = set()

            for stop in stops:
                # stop.location is a PostGIS geometry; extract lat/lng via ST_Y/ST_X
                try:
                    coord_result = await session.execute(
                        text(
                            "SELECT ST_Y(location::geometry) as lat, "
                            "ST_X(location::geometry) as lng "
                            "FROM route_stops WHERE id = :stop_id"
                        ).bindparams(stop_id=stop.id)
                    )
                    coord_row = coord_result.first()
                    if coord_row and coord_row[0] is not None:
                        cell = geo.lat_lng_to_cell(coord_row[0], coord_row[1], resolution)
                        if cell not in seen:
                            seen.add(cell)
                            cells.append(cell)
                except Exception as e:
                    logger.warning(f"Route {route_id}, stop {stop.id}: failed to geocode: {e}")
                    continue

            if cells:
                if not dry_run:
                    await session.execute(
                        update(Route)
                        .where(Route.id == route_id)
                        .values(route_signature=cells)
                    )
                updated += 1
                logger.info(f"Route {route_id}: set signature with {len(cells)} cells")
            else:
                logger.warning(f"Route {route_id}: no cells derived from {len(stops)} stops")

        if not dry_run:
            await session.commit()
            logger.info(f"Committed {updated} route updates")
        else:
            logger.info(f"DRY RUN: would have updated {updated} routes")

    await engine.dispose()

    return {"processed": processed, "updated": updated}


def main():
    parser = argparse.ArgumentParser(description="Backfill route_signature for existing routes")
    parser.add_argument("--dry-run", action="store_true", help="Don't commit changes")
    parser.add_argument("--batch-size", type=int, default=100, help="Routes per batch")
    args = parser.parse_args()

    result = asyncio.run(backfill(dry_run=args.dry_run, batch_size=args.batch_size))
    logger.info(f"Done: processed={result['processed']}, updated={result['updated']}")


if __name__ == "__main__":
    main()
