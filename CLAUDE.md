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

# Run tests
pytest                           # All tests
pytest -v                        # Verbose output
pytest -k "test_solver"          # Run tests matching pattern
pytest --cov=app                 # With coverage report

# Frontend (from ./frontend directory)
npm install
npm run dev      # Development server at localhost:3000
npm run build    # Production build
npm run lint     # ESLint
```

## Docker Commands

```bash
# Full stack deployment (PostgreSQL, Redis, API, Celery, Frontend)
docker-compose up -d

# Development: only database services
docker-compose -f docker-compose.dev.yml up -d

# View logs
docker-compose logs -f

# Stop and remove volumes
docker-compose down -v
```

## Architecture

### Tech Stack
- **API**: FastAPI (async) with Pydantic v2 schemas
- **Database**: PostgreSQL + PostGIS (async via asyncpg, sync via psycopg2 for Celery)
- **Task Queue**: Celery + Redis (optimization runs asynchronously)
- **Solver**: Google OR-Tools for VRP optimization
- **Frontend**: React + Vite + TypeScript + Tailwind CSS + shadcn/ui components

### Key Architectural Decisions

1. **Async/Sync Split**: FastAPI uses async SQLAlchemy (asyncpg driver), but Celery workers use sync SQLAlchemy (psycopg2 driver) because Celery tasks cannot use async. See `settings.database_url` vs `settings.database_url_sync`.

2. **Optimization Flow**:
   - POST `/api/v1/optimization` creates job, queues Celery task, returns `job_id` immediately (HTTP 202)
   - Celery worker runs OR-Tools solver in background
   - Client polls GET `/api/v1/optimization/{job_id}` for results

3. **Temperature Tracking**: Temperature predictions are calculated post-solution (not during OR-Tools search) because callbacks don't have full route context. See `TemperatureTracker.calculate_route_temperatures()`.

### Core Modules

| Path | Purpose |
|------|---------|
| `app/services/solver/solver.py` | `ColdChainVRPSolver` - main OR-Tools wrapper |
| `app/services/solver/callbacks.py` | OR-Tools callbacks + `TemperatureTracker` |
| `app/services/solver/data_model.py` | `VRPDataModel`, `build_vrp_data_model()` |
| `app/services/tasks.py` | Celery task `run_optimization` |
| `app/models/enums.py` | Domain enums with thermodynamic constants |
| `app/core/config.py` | Pydantic Settings with all configurable parameters |

### Frontend Structure

| Path | Purpose |
|------|---------|
| `frontend/src/pages/` | Page components (Dashboard, Vehicles, Shipments, Optimization, Map) |
| `frontend/src/components/` | Reusable UI components |
| `frontend/src/stores/` | Zustand state management |
| `frontend/src/services/` | API client (axios) |
| `frontend/src/i18n/` | Internationalization (Chinese/English) |

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

- `POST /api/v1/optimization` - Start async optimization job
- `GET /api/v1/optimization/{job_id}` - Get job status/results
- `GET /api/v1/routes/{route_id}/temperature-analysis` - Temperature predictions per stop
- CRUD endpoints for `/vehicles`, `/shipments`, `/routes`, `/depots`

API docs available at `http://localhost:8000/api/v1/docs`

## Configuration

All settings in `app/core/config.py` can be overridden via environment variables or `.env` file. Key settings:

- `DATABASE_URL` / `DATABASE_URL_SYNC`
- `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`
- `DEFAULT_SOLVER_TIME_LIMIT` (seconds)
- `DEFAULT_AMBIENT_TEMPERATURE`, `DEFAULT_INITIAL_VEHICLE_TEMP`
- Penalty weights: `TEMP_VIOLATION_PENALTY`, `LATE_DELIVERY_PENALTY`, `VEHICLE_FIXED_COST`

## Development Workflow

### Running All Services (Development)

1. Start database services: `docker-compose -f docker-compose.dev.yml up -d`
2. Terminal 1 - Celery: `celery -A app.core.celery_app worker --loglevel=info -Q optimization,default --pool=solo`
3. Terminal 2 - API: `uvicorn app.main:app --reload --port 8000`
4. Terminal 3 - Frontend: `cd frontend && npm run dev`

### Typical Development Flow

1. Import test data via Excel or API
2. Trigger optimization via POST `/api/v1/optimization`
3. Poll job status until COMPLETED
4. Visualize results via frontend map or `visualize_routes.py`
