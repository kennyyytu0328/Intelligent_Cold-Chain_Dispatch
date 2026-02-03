"""
API v1 router aggregation.
"""
from fastapi import APIRouter

from app.api.v1.endpoints import auth, depots, vehicles, shipments, routes, optimization, geocoding, import_excel

api_router = APIRouter()

# Include all endpoint routers
api_router.include_router(auth.router)

api_router.include_router(
    depots.router,
    prefix="/depots",
    tags=["Depots"],
)

api_router.include_router(
    vehicles.router,
    prefix="/vehicles",
    tags=["Vehicles"],
)

api_router.include_router(
    shipments.router,
    prefix="/shipments",
    tags=["Shipments"],
)

api_router.include_router(
    routes.router,
    prefix="/routes",
    tags=["Routes"],
)

api_router.include_router(
    optimization.router,
    prefix="/optimization",
    tags=["Optimization"],
)

api_router.include_router(
    geocoding.router,
    prefix="",
    tags=["Geocoding"],
)

api_router.include_router(
    import_excel.router,
    prefix="/import",
    tags=["Excel Import"],
)
