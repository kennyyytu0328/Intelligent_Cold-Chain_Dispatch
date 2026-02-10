# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ICCDDS (Intelligent Cold-Chain Dynamic Dispatch System) is a vehicle routing optimization system that solves VRPTW (Vehicle Routing Problem with Time Windows) with thermodynamic constraints for cold-chain logistics.

## Common Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Start FastAPI server
uvicorn app.main:app --reload --port 8000

# Start Celery worker (required for optimization tasks)
# Linux/Mac:
celery -A app.core.celery_app worker --loglevel=info -Q optimization,default
# Windows (requires --pool=solo):
celery -A app.core.celery_app worker --loglevel=info -Q optimization,default --pool=solo

# Monitor Celery tasks (optional)
flower -A app.core.celery_app --port=5555

# Database initialization
psql -h localhost -U postgres -c "CREATE DATABASE iccdds;"
psql -h localhost -U postgres -d iccdds -c "CREATE EXTENSION IF NOT EXISTS postgis;"
psql -h localhost -U postgres -d iccdds -f app/db/schema.sql

# Excel import/export
python generate_excel_template.py
python import_from_excel.py ICCDDS_Import_Template.xlsx

# Map visualization
python visualize_routes.py 2024-01-30           # With road routing
python visualize_routes.py 2024-01-30 --no-routing  # Straight lines
python demo_map_with_routing.py                 # Demo map

# Linting and formatting
ruff check .
black .
mypy app/

# Run backend tests (no DB/Redis required -- all mocked)
pytest                           # All tests with coverage (configured in pyproject.toml)
pytest -v                        # Verbose output
pytest -k "test_solver"          # Run tests matching pattern
pytest -m "not slow"             # Skip slow tests
pytest tests/unit/test_security.py::TestPasswordHashing::test_verify_correct_password  # Single test

# Run frontend tests (from ./frontend directory)
npm test                         # Vitest run (all tests)
npm run test:watch               # Vitest watch mode
npm run test:coverage            # Vitest with V8 coverage

# Frontend dev (from ./frontend directory)
npm install
npm run dev      # Development server at localhost:3000
npm run build    # Runs tsc && vite build (type-check then bundle)
npm run lint     # ESLint
```

## Docker Commands

```bash
# Full stack deployment (PostgreSQL, Redis, API, Celery, Frontend)
docker-compose up -d

# Development: only database services (Postgres on port 5433, Redis on 6379)
docker-compose -f docker-compose.dev.yml up -d

# View logs
docker-compose logs -f

# Stop and remove volumes
docker-compose down -v
```

Note: Dev compose uses port **5433** for PostgreSQL (not 5432) to avoid conflicts with local installations.

## Architecture

### Tech Stack
- **API**: FastAPI (async) with Pydantic v2 schemas
- **Database**: PostgreSQL + PostGIS (async via asyncpg, sync via psycopg2 for Celery)
- **Task Queue**: Celery + Redis (optimization runs asynchronously)
- **Solver**: Google OR-Tools (ortools 9.8) for VRP optimization
- **Frontend**: React 18 + Vite + TypeScript + Tailwind CSS + shadcn/ui (Radix UI primitives)
- **Auth**: JWT (python-jose) + bcrypt password hashing, Bearer token scheme

### Key Architectural Decisions

1. **Async/Sync Split**: FastAPI uses async SQLAlchemy (asyncpg driver), but Celery workers use sync SQLAlchemy (psycopg2 driver) because Celery tasks cannot use async. See `settings.database_url` vs `settings.database_url_sync`. Each has separate connection pools.

2. **Optimization Flow**:
   - POST `/api/v1/optimization` creates job, queues Celery task, returns `job_id` immediately (HTTP 202)
   - Celery worker runs OR-Tools solver in background
   - A background thread in the Celery task updates progress every 10 seconds (capped at 95%)
   - Client polls GET `/api/v1/optimization/{job_id}` for results

3. **Temperature Tracking**: Temperature predictions are calculated post-solution (not during OR-Tools search) because callbacks don't have full route context. See `TemperatureTracker.calculate_route_temperatures()`.

4. **Frontend API Layer**: Axios client at `frontend/src/services/api.ts` uses relative base URL `/api/v1`. Vite dev server proxies to `localhost:8000`; in production, Nginx handles the proxy. Request interceptor injects Bearer token from Zustand auth store. Response interceptor catches 401s and redirects to `/login`.

5. **Celery Task Configuration**: Worker prefetch multiplier is 1 (one task at a time since optimization is compute-heavy). Concurrency: 2 processes. Soft time limit: 10 min, hard limit: 11 min. Two queues: `optimization` (solver tasks) and `default`.

### Core Modules

| Path | Purpose |
|------|---------|
| `app/main.py` | Module-level `app` instance (with `/health`, `/` routes) + `create_application()` factory (bare app, no health routes) |
| `app/services/solver/solver.py` | `ColdChainVRPSolver` - main OR-Tools wrapper |
| `app/services/solver/callbacks.py` | OR-Tools callbacks + `TemperatureTracker` |
| `app/services/solver/data_model.py` | `VRPDataModel`, `build_vrp_data_model()` |
| `app/services/tasks.py` | Celery task `run_optimization` + sync DB engine setup |
| `app/models/enums.py` | Domain enums with thermodynamic constants |
| `app/core/config.py` | Pydantic Settings (LRU cached via `get_settings()`) |
| `app/core/celery_app.py` | Celery app, task routing, serialization config |
| `app/core/security.py` | JWT token creation/verification, password hashing |
| `app/core/dependencies.py` | FastAPI dependency injection (auth, DB sessions) |
| `app/db/database.py` | Async SQLAlchemy engine, session factory, `get_async_session()` |
| `app/api/v1/endpoints/` | 8 REST API modules (auth, vehicles, shipments, routes, optimization, depots, geocoding, import_excel) |

### Frontend Architecture

| Path | Purpose |
|------|---------|
| `frontend/src/pages/` | Page components (Dashboard, Vehicles, Shipments, Optimization, Map, Import, Login, Depots) |
| `frontend/src/components/ui/` | shadcn/ui components (Radix UI + Tailwind) |
| `frontend/src/components/Layout/` | MainLayout with navigation |
| `frontend/src/stores/authStore.ts` | Zustand store for auth state (token, user, login/logout) |
| `frontend/src/stores/optimizationStore.ts` | Zustand store for job tracking (job_id, status, results) |
| `frontend/src/services/api.ts` | Axios client with interceptors + typed API modules |
| `frontend/src/i18n/` | i18next config with en.json and zh-TW.json |

Frontend uses path alias `@/` → `./src/` (configured in both tsconfig and vite.config.ts).

### Thermodynamic Model

Three formulas predict temperature changes along routes:

```
ΔT_drive = Time_travel_hours × (T_ambient - T_current) × K_insulation
ΔT_door  = Time_service_hours × C_door_type × (1 - 0.5 × IsCurtain)
ΔT_cooling = Time_drive_hours × Rate_cooling
```

**Important**: Time values must be in hours (not minutes) for realistic temperature calculations.

Constants are defined in `app/models/enums.py`:
- `InsulationGrade.k_value`: PREMIUM=0.02, STANDARD=0.05, BASIC=0.10
- `DoorType.coefficient`: ROLL=0.8, SWING=1.2

### Optimization Hierarchy (Lexicographic)

1. **Level 0**: Hard constraints (STRICT SLA time windows, temperature limits, capacity)
2. **Level 1**: Minimize fleet size (via `vehicle_fixed_cost`)
3. **Level 2**: Minimize total distance
4. **Level 3**: Maximize slack time

### SLA Handling

- **STRICT**: Hard constraint - shipment must be visited within time window
- **STANDARD**: Soft constraint - can be dropped with penalty based on priority

## API Endpoints

All endpoints are mounted under `/api/v1`. OpenAPI docs at `http://localhost:8000/api/v1/docs`.

- `POST /api/v1/auth/login` - JWT login (form data: username/password)
- `POST /api/v1/optimization` - Start async optimization job (returns HTTP 202)
- `GET /api/v1/optimization/{job_id}` - Get job status/results
- `GET /api/v1/routes/{route_id}/temperature-analysis` - Temperature predictions per stop
- CRUD endpoints for `/vehicles`, `/shipments`, `/routes`, `/depots`
- `POST /api/v1/import/excel` - Upload Excel for batch import
- `GET /api/v1/import/template` - Download Excel template
- `GET /health` - Health check (outside `/api/v1` prefix)

## Configuration

All settings in `app/core/config.py` (Pydantic v2 BaseSettings) can be overridden via environment variables or `.env` file. Settings are LRU-cached via `get_settings()`.

Key settings:

- `DATABASE_URL` (async, asyncpg) / `DATABASE_URL_SYNC` (sync, psycopg2 for Celery)
- `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`
- `SECRET_KEY`, `ACCESS_TOKEN_EXPIRE_MINUTES` (default: 1440 = 24h)
- `DEFAULT_SOLVER_TIME_LIMIT` (default: 300 seconds)
- `DEFAULT_AMBIENT_TEMPERATURE` (default: 30°C), `DEFAULT_INITIAL_VEHICLE_TEMP` (default: -5°C)
- `AVERAGE_SPEED_KMH` (default: 30)
- Penalty weights: `TEMP_VIOLATION_PENALTY`, `LATE_DELIVERY_PENALTY`, `VEHICLE_FIXED_COST`
- `INFEASIBLE_COST` (default: 10,000,000) - OR-Tools hard constraint violation penalty

## Database

- Async engine: pool_size=10, max_overflow=20, pool_pre_ping=True
- Sync engine (Celery): pool_size=5, max_overflow=10
- Session config: `expire_on_commit=False`, `autocommit=False`, `autoflush=False`
- Naming convention enforced for constraints: `ix_`, `uq_`, `ck_`, `fk_`, `pk_` prefixes
- PostGIS extension required for geospatial operations

## Development Workflow

### Running All Services (Development)

1. Start database services: `docker-compose -f docker-compose.dev.yml up -d`
2. Terminal 1 - Celery: `celery -A app.core.celery_app worker --loglevel=info -Q optimization,default --pool=solo`
3. Terminal 2 - API: `uvicorn app.main:app --reload --port 8000`
4. Terminal 3 - Frontend: `cd frontend && npm run dev`

Default login: `admin` / `admin123`

### Typical Development Flow

1. Import test data via Excel or API
2. Trigger optimization via POST `/api/v1/optimization`
3. Poll job status until COMPLETED
4. Visualize results via frontend map or `visualize_routes.py`

## Testing

### Backend Tests (pytest)

122 tests, 70% overall coverage (100% on critical modules). **No PostgreSQL or Redis required** -- all external dependencies are mocked.

Configuration in `pyproject.toml`: `asyncio_mode = "auto"`, coverage source is `app/` (excludes `app/db/*`, `app/core/celery_app.py`, `app/services/tasks.py`).

Test markers: `slow`, `solver` (uses real OR-Tools), `migration` (requires real PostgreSQL).

Key test infrastructure:

| File | Purpose |
|------|---------|
| `tests/conftest.py` | Root fixtures: mock DB session, mock user, auth tokens, `app` fixture (module-level `app`), `client`/`unauthenticated_client`, solver data factories |
| `tests/api/conftest.py` | API helpers: `make_mock_result()`, `make_mock_vehicle()`, `make_mock_shipment()` |
| `tests/unit/` | Unit tests for security, enums, data_model, callbacks, schemas |
| `tests/solver/` | Solver tests with **real OR-Tools** (no mocking -- pure computation) |
| `tests/api/` | API endpoint tests using `httpx.AsyncClient` + `ASGITransport` |

**Critical testing pitfalls:**
- `app` fixture must use module-level `app` from `app.main`, NOT `create_application()` (which creates a bare app without `/health` and `/` routes)
- Environment variables must be set BEFORE importing any `app.*` modules (Settings validates on import)
- `get_settings()` LRU cache must be cleared between tests (autouse fixture in conftest)
- Mock datetime fields with real `datetime` objects, not strings (for `.total_seconds()` calls)

### Frontend Tests (Vitest)

13 tests using Vitest + jsdom. Configuration in `frontend/vitest.config.ts`. Setup file at `frontend/src/test/setup.ts` (jest-dom matchers + localStorage mock for Zustand persist).

Zustand stores are tested via `getState()`/`setState()` without React rendering.

### Production Deployment

Docker Compose runs 5 services: PostgreSQL 15 (PostGIS), Redis 7, backend API, Celery worker, and frontend (Nginx). Frontend uses multi-stage build (Node 20 → Nginx alpine). Nginx proxies `/api` to the backend container, serves SPA with fallback to `index.html`, and adds security headers.
