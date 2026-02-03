"""
FastAPI application entry point for ICCDDS.

Intelligent Cold-Chain Dynamic Dispatch System API.
"""
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.db.database import init_db
from app.api.v1 import api_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """
    Application lifespan handler.

    Runs startup and shutdown logic.
    """
    # Startup
    # Note: In production, use Alembic migrations instead of init_db
    # await init_db()
    yield
    # Shutdown
    pass


def create_application() -> FastAPI:
    """Create and configure FastAPI application."""

    app = FastAPI(
        title=settings.app_name,
        description="""
        ## Intelligent Cold-Chain Dynamic Dispatch System (ICCDDS)

        A vehicle routing optimization system for cold-chain logistics with:

        - **VRPTW Optimization**: Vehicle Routing Problem with Time Windows
        - **Thermodynamic Constraints**: Temperature tracking during delivery
        - **Multiple Time Windows**: Support for complex delivery schedules
        - **SLA Management**: STRICT vs STANDARD constraint handling

        ### Key Features

        - 🚛 Fleet management with thermodynamic properties
        - 📦 Shipment management with temperature constraints
        - 🔄 Asynchronous optimization via Celery
        - 📊 Real-time route monitoring

        ### Thermodynamic Model

        The system uses three formulas to predict temperature:

        1. **Transit Rise**: `ΔT_drive = Time × (T_ambient - T_current) × K_insulation`
        2. **Door Rise**: `ΔT_door = Time × C_door × (1 - 0.5 × IsCurtain)`
        3. **Cooling**: `ΔT_cooling = Time × Rate_cooling`
        """,
        version=settings.app_version,
        openapi_url=f"{settings.api_v1_prefix}/openapi.json",
        docs_url=f"{settings.api_v1_prefix}/docs",
        redoc_url=f"{settings.api_v1_prefix}/redoc",
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure properly in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include API router
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    return app


# Create application instance
app = create_application()


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "app": settings.app_name,
        "version": settings.app_version,
    }


@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "docs": f"{settings.api_v1_prefix}/docs",
        "openapi": f"{settings.api_v1_prefix}/openapi.json",
    }
