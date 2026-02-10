"""Root conftest.py -- shared fixtures for all test modules."""
import os
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

# Set env vars BEFORE any app imports to prevent real DB/Redis connections
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test_db")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://test:test@localhost:5432/test_db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/15")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/15")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-jwt-signing-only")

from app.core.config import get_settings, Settings
from app.core.security import create_access_token, get_password_hash


# =========================================================================
# Settings
# =========================================================================
@pytest.fixture(autouse=True)
def _clear_settings_cache():
    """Clear LRU cache before each test to prevent stale settings."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def test_settings() -> Settings:
    return get_settings()


# =========================================================================
# Auth Fixtures
# =========================================================================
@pytest.fixture
def valid_token() -> str:
    return create_access_token(data={"sub": "testuser"})


@pytest.fixture
def expired_token() -> str:
    return create_access_token(
        data={"sub": "testuser"},
        expires_delta=timedelta(seconds=-1),
    )


@pytest.fixture
def admin_password_hash() -> str:
    return get_password_hash("admin123")


# =========================================================================
# Mock DB Session
# =========================================================================
@pytest.fixture
def mock_session() -> AsyncMock:
    """Mock async database session (no real DB needed)."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.scalar = AsyncMock(return_value=None)
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    session.delete = AsyncMock()
    return session


# =========================================================================
# Mock User
# =========================================================================
@pytest.fixture
def mock_user(admin_password_hash):
    user = MagicMock()
    user.id = uuid4()
    user.username = "testuser"
    user.hashed_password = admin_password_hash
    user.is_active = True
    return user


# =========================================================================
# FastAPI Test Client
# =========================================================================
@pytest.fixture
def app():
    from app.main import app as fastapi_app
    return fastapi_app


@pytest.fixture
async def client(app, mock_session, mock_user):
    """Authenticated httpx.AsyncClient with mocked DB session."""
    from httpx import AsyncClient, ASGITransport
    from app.db.database import get_async_session
    from app.core.dependencies import get_current_user

    async def override_session():
        yield mock_session

    async def override_user():
        return mock_user

    app.dependency_overrides[get_async_session] = override_session
    app.dependency_overrides[get_current_user] = override_user

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c

    app.dependency_overrides.clear()


@pytest.fixture
async def unauthenticated_client(app, mock_session):
    """Client without auth override -- for testing auth-required endpoints."""
    from httpx import AsyncClient, ASGITransport
    from app.db.database import get_async_session

    async def override_session():
        yield mock_session

    app.dependency_overrides[get_async_session] = override_session

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c

    app.dependency_overrides.clear()


# =========================================================================
# Solver Data Factories
# =========================================================================
@pytest.fixture
def make_vehicle_data():
    from app.services.solver.data_model import VehicleData

    def _make(
        index: int = 0,
        vehicle_id: str = None,
        license_plate: str = "TEST-001",
        capacity_weight: float = 1000.0,
        capacity_volume: float = 10.0,
        k_value: float = 0.05,
        door_coefficient: float = 0.8,
        has_strip_curtains: bool = False,
        cooling_rate: float = -2.5,
        initial_temp: float = -5.0,
        driver_id: str = None,
        driver_name: str = "Test Driver",
    ) -> VehicleData:
        return VehicleData(
            index=index,
            vehicle_id=vehicle_id or str(uuid4()),
            license_plate=license_plate,
            capacity_weight=capacity_weight,
            capacity_volume=capacity_volume,
            k_value=k_value,
            door_coefficient=door_coefficient,
            has_strip_curtains=has_strip_curtains,
            cooling_rate=cooling_rate,
            initial_temp=initial_temp,
            driver_id=driver_id,
            driver_name=driver_name,
        )

    return _make


@pytest.fixture
def make_location_node():
    from app.services.solver.data_model import LocationNode

    def _make(
        index: int = 0,
        latitude: float = 25.0330,
        longitude: float = 121.5654,
        address: str = "Test Address",
        shipment_id: str = None,
        time_windows: list = None,
        service_duration: int = 15,
        demand_weight: float = 50.0,
        demand_volume: float = 0.5,
        temp_limit_upper: float = 5.0,
        temp_limit_lower: float = None,
        is_strict_sla: bool = False,
        priority: int = 50,
    ) -> LocationNode:
        if time_windows is None:
            time_windows = [(480, 720)]  # 08:00-12:00
        return LocationNode(
            index=index,
            latitude=latitude,
            longitude=longitude,
            address=address,
            shipment_id=shipment_id or str(uuid4()),
            time_windows=time_windows,
            service_duration=service_duration,
            demand_weight=demand_weight,
            demand_volume=demand_volume,
            temp_limit_upper=temp_limit_upper,
            temp_limit_lower=temp_limit_lower,
            is_strict_sla=is_strict_sla,
            priority=priority,
        )

    return _make


@pytest.fixture
def make_depot_node():
    from app.services.solver.data_model import LocationNode

    def _make(
        latitude: float = 25.0330,
        longitude: float = 121.5654,
        address: str = "Depot",
    ) -> LocationNode:
        return LocationNode(
            index=0,
            latitude=latitude,
            longitude=longitude,
            address=address,
            time_windows=[(0, 1440)],
            service_duration=0,
        )

    return _make


@pytest.fixture
def simple_vrp_data(make_depot_node, make_location_node, make_vehicle_data):
    """Simple VRP: 1 vehicle, 2 deliveries in Taipei. Good for solver smoke tests."""
    from app.services.solver.data_model import (
        VRPDataModel,
        compute_distance_matrix,
        compute_time_matrix,
    )

    depot = make_depot_node()
    node1 = make_location_node(
        index=1, latitude=25.0478, longitude=121.5170,
        address="Delivery 1", demand_weight=50.0, demand_volume=0.5,
    )
    node2 = make_location_node(
        index=2, latitude=25.0200, longitude=121.5400,
        address="Delivery 2", demand_weight=30.0, demand_volume=0.3,
    )

    nodes = [depot, node1, node2]
    vehicle = make_vehicle_data(index=0)

    distance_matrix = compute_distance_matrix(nodes)
    time_matrix = compute_time_matrix(nodes, distance_matrix)

    return VRPDataModel(
        nodes=nodes,
        vehicles=[vehicle],
        distance_matrix=distance_matrix,
        time_matrix=time_matrix,
        ambient_temperature=30.0,
        time_limit_seconds=10,
        earliest_departure_minutes=360,
    )
