# ICCDDS - Intelligent Cold-Chain Dynamic Dispatch System

**A VRPTW Vehicle Routing Optimization System with Thermodynamic Constraints**

## Table of Contents

- [System Features](#-system-features)
- [System Architecture](#️-system-architecture)
- [Database Design](#-database-design)
- [Quick Start](#-quick-start)
- [Excel Batch Import](#-excel-batch-import)
- [Route Map Visualization](#️-route-map-visualization)
- [API Examples](#-api-examples)
- [Completeness Check](#-completeness-check)
- [File Inventory](#-file-inventory)
- [Troubleshooting](#-troubleshooting)
- [Performance Metrics](#-performance-metrics)
- [Learning Resources](#-learning-resources)
- [Support](#-support)
- [License](#-license)

---

## 🎯 System Features

### Core Optimization Capabilities
- ✅ **VRPTW Solver**: Vehicle Routing Problem with Time Windows
- ✅ **Multiple Time Windows**: Single shipment supports multiple delivery time slots (OR relationship)
- ✅ **Thermodynamic Model**: Real-time temperature tracking (3 key formulas)
- ✅ **SLA Tiers**: STRICT (hard constraints) vs STANDARD (soft constraints)
- ✅ **Capacity Constraints**: Dual limits on weight and volume
- ✅ **Async Optimization**: Long-running task processing via Celery + Redis
- ✅ **Web UI**: React-based dashboard with real-time optimization monitoring
- ✅ **Docker Deployment**: One-command deployment with docker-compose

### Thermodynamic Formulas
```text
ΔT_drive = Time_travel × (T_ambient - T_current) × K_insulation
ΔT_door = Time_service × C_door_type × (1 - 0.5 × IsCurtain)
ΔT_cooling = Time_drive × Rate_cooling
```

### Optimization Objectives (Lexicographic Order)
1. **Level 0**: Satisfy hard constraints (STRICT SLA time windows, temperature limits)
2. **Level 1**: Minimize fleet size
3. **Level 2**: Minimize total distance and time
4. **Level 3**: Maximize buffer time (reduce emergency risks)

---

## 🏗️ System Architecture

### Technology Stack
```text
┌─────────────────────────────────────┐
│  Frontend: React + Vite + Tailwind  │
│  (Leaflet Maps + shadcn/ui)        │
└──────────────┬──────────────────────┘
               ↓
┌─────────────────────────────────────┐
│  Backend: FastAPI + SQLAlchemy      │
└──────────────┬──────────────────────┘
               ↓
┌─────────────────────────────────────┐
│  Database: PostgreSQL + PostGIS     │
│  Cache/Queue: Redis                 │
└──────────────┬──────────────────────┘
               ↓
┌─────────────────────────────────────┐
│  Optimizer: Google OR-Tools (VRP)   │
│  Task Queue: Celery Workers         │
└─────────────────────────────────────┘
```

### Core Modules

| Module | Files | Description |
|------|------|------|
| **Frontend UI** | `frontend/` | React + Vite + Tailwind CSS + shadcn/ui |
| **ORM Models** | `app/models/` | 9 domain models (Vehicle, Shipment, Route, etc.) |
| **API Schemas** | `app/schemas/` | 8 Pydantic request/response schemas |
| **OR-Tools** | `app/services/solver/` | VRP solver + thermodynamic calculations |
| **API Endpoints** | `app/api/v1/endpoints/` | 7 REST API modules |
| **Async Tasks** | `app/services/tasks.py` | Celery optimization tasks |
| **Configuration** | `app/core/` | Application config and Celery settings |

---

## 📊 Database Design

### Main Tables
- **vehicles**: Vehicles (includes thermodynamic parameters)
- **shipments**: Shipments (supports multiple time windows)
- **routes**: Optimized routes
- **route_stops**: Each stop in a route (includes temperature predictions)
- **optimization_jobs**: Async task tracking
- **temperature_logs**: IoT sensor data
- **alerts**: Alert records (temperature/SLA violations)

### Key Fields
```sql
-- Vehicle: Thermodynamic parameters
k_value              -- Insulation coefficient
door_coefficient     -- Door coefficient
has_strip_curtains   -- Strip curtains (reduce heat loss by 50%)
cooling_rate         -- Cooling rate (°C/min)

-- Shipment: Multiple time windows + temperature
time_windows         -- JSONB: [{"start":"08:00","end":"10:00"}, ...]
temp_limit_upper     -- Maximum acceptable temperature (hard constraint)
sla_tier             -- STRICT or STANDARD

-- RouteStop: Temperature prediction
predicted_arrival_temp    -- Critical constraint point
transit_temp_rise         -- ΔT_drive
service_temp_rise         -- ΔT_door
cooling_applied           -- ΔT_cooling
```

---

## 🚀 Quick Start

### Option 1: Docker Deployment (Recommended)

**Prerequisites:** Docker Desktop or Docker Engine + Docker Compose

```bash
# 1. Clone repository and navigate to project directory
cd Intelligent_Cold-Chain_Dispatch

# 2. Copy environment variables
cp .env.example .env

# 3. Start all services (Frontend + Backend + Database + Redis + Celery)
docker-compose up -d

# 4. Check service status
docker-compose ps

# 5. View logs
docker-compose logs -f
```

**Access Services:**
- 🌐 Frontend UI: http://localhost
- 📡 API Documentation: http://localhost:8000/docs
- 🔐 Login: `admin` / `admin123`

**Stop Services:**
```bash
# Stop and keep data
docker-compose down

# Stop and remove all data
docker-compose down -v
```

### Option 2: Development Environment

**Prerequisites:** Python 3.10+, Node.js 18+, PostgreSQL, Redis

```bash
# Terminal 1: Start databases only
docker-compose -f docker-compose.dev.yml up -d

# Terminal 2: Backend API
pip install -r requirements.txt
cp .env.example .env
# Initialize database (first time only)
psql -h localhost -p 5433 -U postgres -c "CREATE DATABASE iccdds;"
psql -h localhost -p 5433 -U postgres -d iccdds -c "CREATE EXTENSION IF NOT EXISTS postgis;"
psql -h localhost -p 5433 -U postgres -d iccdds -f app/db/schema.sql
alembic stamp 0001            # Mark baseline as applied
alembic upgrade head          # Apply v3.1 migrations
# For existing databases, just run: alembic upgrade head
uvicorn app.main:app --reload --port 8000

# Terminal 3: Celery Worker (Windows: add --pool=solo)
celery -A app.core.celery_app worker --loglevel=info -Q optimization,default --pool=solo

# Terminal 4: Frontend
cd frontend
npm install
npm run dev
```

**Access Services:**
- 🌐 Frontend: http://localhost:3000
- 📡 API Docs: http://localhost:8000/docs

---

## 📊 Excel Batch Import

The system provides Excel batch import functionality for quick setup of shipments and vehicle data.

### Quick Start
```bash
# 1. Generate Excel template
python generate_excel_template.py

# 2. Edit ICCDDS_Import_Template.xlsx with Excel (modify or add data)

# 3. Start API server
uvicorn app.main:app --reload --port 8000

# 4. Execute batch import
python import_from_excel.py ICCDDS_Import_Template.xlsx
```

### Excel Template Content
`ICCDDS_Import_Template.xlsx` contains 3 worksheets:

| Worksheet | Description |
|--------|------|
| **Instructions** | Field descriptions and notes |
| **Shipments** | Shipment examples: addresses, coordinates, time windows, temperature limits, SLA tiers, etc. |
| **Vehicles** | Vehicle examples: weight capacity, volume, insulation grade, door type, cooling rate, etc. |

### Key Field Descriptions

**Shipment Fields:**
- `time_window_1_start/end`: First time window (HH:MM format)
- `time_window_2_start/end`: Second time window (optional, supports multiple time windows)
- `sla_tier`: STRICT (must satisfy) or STANDARD (can delay)
- `temp_limit_upper_celsius`: Maximum acceptable temperature

**Vehicle Fields:**
- `insulation_grade`: PREMIUM (K=0.02) / STANDARD (K=0.05) / BASIC (K=0.10)
- `door_type`: ROLL (roll-up door) or SWING (swing doors)
- `has_strip_curtains`: TRUE/FALSE (strip curtains reduce heat loss by 50%)
- `cooling_rate_celsius_per_min`: Cooling rate (negative value, e.g., -2.5)

For detailed instructions, refer to `EXCEL_IMPORT_GUIDE.md`

---

## 🗺️ Route Map Visualization

The system supports visualizing optimized delivery routes on interactive maps, **with real road routing display**.

### Quick Start
```bash
# View demo map (with real road routing)
python demo_map_with_routing.py
# Open demo_routes_map_routing.html in browser

# Visualize actual optimization results (requires prior optimization)
python visualize_routes.py 2024-01-30

# Use straight-line routes (skip routing API, faster)
python visualize_routes.py 2024-01-30 --no-routing
```

### Map Features
| Feature | Description |
|------|------|
| 🛣️ **Real Road Routing** | Uses OSRM routing service, routes follow actual roads |
| 📍 **Multi-Vehicle Colors** | Different vehicles use different colors (up to 12 vehicles) |
| 🔢 **Stop Sequence** | Numeric labels show delivery order |
| 🌡️ **Temperature Status** | Green=normal, Red=exceeds limit |
| 📊 **Detailed Info** | Click markers to view shipment, temperature, time, etc. |
| 🎛️ **Layer Control** | Show/hide specific vehicle routes |
| 📏 **Measurement Tool** | Measure distance between any two points on map |
| 🔍 **Full Screen Mode** | Zoom in to view route details |

### Demo Maps
The system provides multiple demo maps for testing:

| File | Description |
|------|------|
| `demo_routes_map_routing.html` | Real road routing (recommended) |
| `demo_routes_map_fixed.html` | Straight-line routes |

For detailed instructions, refer to `MAP_VISUALIZATION_GUIDE.md`

---

## �️ Web UI Features

The system includes a full-featured React frontend with:

### Dashboard
- Real-time statistics (total vehicles, shipments, pending deliveries)
- Quick action buttons for key operations
- System status overview

### Vehicle Management
- ✅ Create, edit, delete vehicles
- ✅ Configure thermodynamic parameters (insulation grade, door type, cooling rate)
- ✅ Set capacity limits (weight, volume)
- ✅ Manage vehicle availability status

### Shipment Management
- ✅ Create, edit, delete shipments
- ✅ Set multiple time windows (OR relationship)
- ✅ Configure temperature limits and SLA tiers
- ✅ Batch operations support

### Route Optimization
- ✅ **Excel Import**: Upload XLSX files for batch data import
- ✅ **Optimization Parameters**: Configure depot location, ambient temperature, time limits
- ✅ **Async Execution**: Real-time progress tracking with status updates
- ✅ **Result Visualization**: View generated routes on interactive maps

### Interactive Map View
- 🗺️ **Leaflet Integration**: Interactive map with zoom and pan
- 🚗 **Multi-Vehicle Routes**: Different colors for each vehicle (up to 12)
- 📍 **Stop Markers**: Numbered markers showing delivery sequence
- 🌡️ **Temperature Indicators**: Color-coded temperature status (green=OK, red=violation)
- 🎛️ **Layer Control**: Toggle visibility of individual vehicle routes
- 📊 **Info Popups**: Click markers to view detailed shipment information

### Internationalization
- 🌍 English (en) / 繁體中文 (zh-TW) language toggle
- Fully localized UI labels and messages

### Responsive Design
- 📱 Mobile-friendly layout
- 💻 Desktop-optimized interface
- 🎨 Clean, modern UI with Tailwind CSS

---

## �📡 API Examples

### 1. Start Optimization Task
```http
POST /api/v1/optimization
```

**Request Body:**
```json
{
  "plan_date": "2024-01-30",
  "parameters": {
    "time_limit_seconds": 60,
    "strategy": "MINIMIZE_VEHICLES",
    "ambient_temperature": 30.0
  }
}
```

**Response (HTTP 202):**
```json
{
  "job_id": "abc123...",
  "status": "PENDING",
  "celery_task_id": "xyz789...",
  "shipment_count": 10,
  "vehicle_count": 4
}
```

### 2. Query Optimization Results
```http
GET /api/v1/optimization/{job_id}
```

**Response:**
```json
{
  "status": "COMPLETED",
  "result_summary": {
    "routes_created": 2,
    "shipments_assigned": 10,
    "total_distance_km": 45.2,
    "solver_time_seconds": 35.5
  },
  "route_ids": ["uuid1", "uuid2"],
  "unassigned_shipment_ids": []
}
```

### 3. View Route Temperature Analysis
```http
GET /api/v1/routes/{route_id}/temperature-analysis
```

**Response:**
```json
{
  "route_code": "R-20240130-ABC-1234",
  "initial_temperature": -5.0,
  "final_temperature": 3.2,
  "max_temperature": 4.8,
  "is_feasible": true,
  "stops": [
    {
      "sequence": 1,
      "shipment_id": "...",
      "temperature": {
        "arrival_temp": 0.5,
        "transit_rise": 5.5,
        "cooling_applied": -5.0,
        "departure_temp": 2.1
      },
      "constraints": {
        "temp_limit_upper": 5.0,
        "is_feasible": true
      }
    }
  ]
}
```

---

## 🧪 Completeness Check

### All Components Implemented ✅

```text
Frontend UI (React)
  ├── Dashboard with statistics     ✅
  ├── Vehicle management (CRUD)     ✅
  ├── Shipment management (CRUD)    ✅
  ├── Excel import interface        ✅
  ├── Optimization control panel    ✅
  ├── Interactive map (Leaflet)     ✅
  ├── Internationalization (i18n)   ✅
  └── Responsive design (RWD)       ✅

Database Layer
  ├── PostgreSQL Schema             ✅
  ├── SQLAlchemy ORM Models (9)     ✅
  ├── Pydantic Schemas (8)          ✅
  └── Async connection config       ✅

Optimization Engine (Solver)
  ├── VRP data model conversion     ✅
  ├── Distance/time matrix calc     ✅
  ├── Thermodynamic callbacks       ✅
  └── Complete VRP Solver           ✅

Async Tasks (Celery)
  ├── Celery app configuration      ✅
  ├── Optimization task impl        ✅
  ├── DB read/write operations      ✅
  └── Error handling and retry      ✅

API Endpoints (REST)
  ├── Vehicle management (CRUD)     ✅
  ├── Shipment management (CRUD + Batch) ✅
  ├── Route queries (+ temp analysis) ✅
  ├── Optimization API (async)      ✅
  ├── Depot management              ✅
  ├── Geocoding service             ✅
  └── Excel import endpoint         ✅

Deployment & Configuration
  ├── Docker Compose (production)   ✅
  ├── Docker Compose (development)  ✅
  ├── Frontend Dockerfile (Nginx)   ✅
  ├── Pydantic Settings             ✅
  ├── Environment variables         ✅
  └── .env.example                  ✅
```

---

## 📝 File Inventory

```text
frontend/                     # React Frontend
├── src/
│   ├── components/          # React components
│   │   ├── Layout/          # MainLayout, navigation
│   │   ├── Map/             # Leaflet map components
│   │   └── ui/              # shadcn/ui components
│   ├── pages/               # Page components
│   │   ├── DashboardPage.tsx
│   │   ├── VehiclesPage.tsx
│   │   ├── ShipmentsPage.tsx
│   │   ├── OptimizationPage.tsx
│   │   ├── MapPage.tsx
│   │   ├── ImportPage.tsx
│   │   └── LoginPage.tsx
│   ├── services/            # API client
│   │   └── api.ts
│   ├── stores/              # State management
│   │   ├── authStore.ts
│   │   └── optimizationStore.ts
│   ├── i18n/                # Internationalization
│   │   ├── en.json
│   │   ├── zh-TW.json
│   │   └── index.ts
│   └── App.tsx              # Main app component
├── index.html
├── package.json
├── vite.config.ts
└── Dockerfile               # Frontend container

app/                         # Backend
├── main.py                  # FastAPI application entry point
├── __init__.py
│
├── core/
│   ├── config.py           # Pydantic Settings
│   ├── celery_app.py       # Celery configuration
│   └── __init__.py
│
├── db/
│   ├── database.py         # SQLAlchemy async connection
│   ├── schema.sql          # PostgreSQL DDL + PostGIS
│   └── __init__.py
│
├── models/                 # ORM models (9 models)
│   ├── base.py
│   ├── enums.py
│   ├── driver.py
│   ├── vehicle.py
│   ├── customer.py
│   ├── shipment.py
│   ├── route.py
│   ├── optimization.py
│   ├── telemetry.py
│   └── depot.py
│
├── schemas/                # Pydantic Schemas (8 schemas)
│   ├── base.py
│   ├── driver.py
│   ├── vehicle.py
│   ├── customer.py
│   ├── shipment.py
│   ├── route.py
│   ├── optimization.py
│   └── depot.py
│
├── services/
│   ├── tasks.py            # Celery optimization tasks
│   ├── depot_import.py     # Depot data import
│   ├── geocoding.py        # Geocoding service
│   └── solver/             # OR-Tools solver
│       ├── solver.py
│       ├── data_model.py
│       └── callbacks.py
│
└── api/v1/
    └── endpoints/          # API endpoints (7 modules)
        ├── vehicles.py
        ├── shipments.py
        ├── routes.py
        ├── optimization.py
        ├── depots.py
        ├── geocoding.py
        └── import_excel.py

Configuration & Documentation:
├── requirements.txt          # Python dependencies
├── .env.example              # Environment variable template
├── docker-compose.yml        # Production deployment
├── docker-compose.dev.yml    # Development environment
├── README.md                 # This file (overview)
├── STARTUP_GUIDE.md          # Detailed startup instructions
├── AGENT.md                  # Architecture design (V3.0)
├── CLAUDE.md                 # Development guide
├── EXCEL_IMPORT_GUIDE.md     # Excel import tutorial
└── MAP_VISUALIZATION_GUIDE.md # Map visualization tutorial

Utility Scripts:
├── generate_excel_template.py    # Generate Excel template
├── import_from_excel.py          # Batch import from Excel
├── visualize_routes.py           # Visualize optimized routes (real roads)
├── demo_map_with_routing.py      # Generate demo map (with routing)
└── demo_map_fixed.py             # Generate demo map (straight lines)
```

---

## 🔧 Troubleshooting

### Docker Issues

**Services not starting:**
```bash
# Check Docker is running
docker --version
docker-compose --version

# View service logs
docker-compose logs -f [service-name]

# Restart specific service
docker-compose restart [service-name]

# Rebuild containers
docker-compose up -d --build
```

**Port conflicts:**
```bash
# Check if ports are in use
# Windows PowerShell:
Get-NetTCPConnection -LocalPort 80,8000,5432,6379

# Linux/Mac:
netstat -tuln | grep -E '(80|8000|5432|6379)'

# Solution: Modify ports in docker-compose.yml or stop conflicting services
```

**Cannot access frontend (http://localhost):**
```bash
# Check frontend container status
docker-compose ps frontend

# View frontend logs
docker-compose logs frontend

# Restart frontend
docker-compose restart frontend
```

### "ModuleNotFoundError"
```bash
pip install -r requirements.txt
```

### "PostgreSQL Connection Failed"
```bash
# Check PostgreSQL is running
psql -h localhost -U postgres -c "SELECT version();"

# Check PostGIS
psql -h localhost -U postgres -d iccdds -c "SELECT PostGIS_version();"
```

### "Redis Connection Failed"
```bash
# Check Redis is running
redis-cli ping
# Should return: PONG
```

### Celery Worker Not Executing Tasks
```bash
# Start Worker with all logs
celery -A app.core.celery_app worker --loglevel=debug

# Use Flower for monitoring (optional)
pip install flower
flower -A app.core.celery_app --port=5555
# Access: http://localhost:5555
```

---

## 📈 Performance Metrics

### Solving Time
- **Small Scale** (10 shipments, 3 vehicles): ~5 seconds
- **Medium Scale** (50 shipments, 10 vehicles): ~30 seconds
- **Large Scale** (100+ shipments): depends on `time_limit_seconds` parameter

### Accuracy
- **STRICT SLA**: 100% satisfaction or marked as infeasible
- **Temperature Prediction**: Based on precise thermodynamic models, comparable with actual measurements

### Scalability
- Supports hundreds of shipments and dozens of vehicles
- Can process multiple optimization tasks in parallel via Celery
- PostgreSQL + PostGIS supports geospatial query optimization

---

## 🎓 Learning Resources

### Key Code Locations
- **Thermodynamic Calculations**: `app/services/solver/callbacks.py` → `TemperatureTracker`
- **VRP Solver**: `app/services/solver/solver.py` → `ColdChainVRPSolver`
- **Multiple Time Windows**: `app/models/shipment.py` → `TimeWindow` class
- **Async Tasks**: `app/services/tasks.py` → `run_optimization` task

### Formulas and Derivations
Refer to the "Core Algorithm Logic" section in `AGENT.md`

---

## 📞 Support

- 📖 **Complete Documentation**: See `STARTUP_GUIDE.md` for detailed setup instructions
- 🐛 **Troubleshooting**: See the Troubleshooting section in this README
- 🐳 **Docker Issues**: Check `docker-compose.yml` and service logs
- 🌐 **Frontend Issues**: Check frontend logs at `docker-compose logs frontend`
- 🔍 **Code Exploration**: Use IDE search functionality to find key implementations
- 💬 **Default Login**: Username: `admin`, Password: `admin123`

---

## 📄 License

This project is designed for academic research and commercial applications.

---

**Ready to optimize your cold-chain logistics? 🚀**
