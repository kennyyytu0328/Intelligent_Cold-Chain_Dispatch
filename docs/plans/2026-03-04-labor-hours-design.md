# Step 5: Labor Hours Design

**Date:** 2026-03-04
**Status:** Approved
**Feature Flag:** `ENABLE_LABOR_DIMENSION` (default: `False`)

## Overview

Add optional labor hour tracking and compliance to the ICCDDS system. When enabled, the solver penalizes routes that would push drivers over weekly/daily limits (soft constraint), and the system tracks actual hours worked with compliance APIs.

When disabled, all labor components are no-ops — no solver impact, no logging, APIs return `{ enabled: false }`.

## Regulatory Limits (Configurable)

| Setting | Default | Source |
|---------|---------|--------|
| `DRIVER_WEEKLY_LIMIT_MINUTES` | 2880 (48h) | Taiwan Labor Standards Act |
| `DRIVER_DAILY_LIMIT_MINUTES` | 720 (12h) | Including overtime |
| `LABOR_WARNING_THRESHOLD` | 0.85 (85%) | Warning trigger |
| `ENABLE_LABOR_DIMENSION` | False | Feature flag |

## Feature Flag Behavior

| Component | Flag OFF | Flag ON |
|-----------|----------|---------|
| Solver | No LaborMinutes dimension | Full labor dimension + dynamic penalty |
| `record_dispatch()` | No-op | Creates labor log + updates accumulators |
| Compliance API | `{ enabled: false, data: null }` | Full compliance data |
| Reconciliation task | Early return | Full reconciliation |

## 1. Solver Integration

New `_add_labor_dimension()` method on `ColdChainVRPSolver`, gated by `ENABLE_LABOR_DIMENSION`:

- **Transit callback**: sums travel + service minutes per arc
- **Dimension**: `LaborMinutes`, hard cap 1440min (24h safety net), start at zero
- **Per-vehicle soft upper bound**: `min(remaining_daily, remaining_weekly)` for each driver
- **Dynamic penalty**: `MAX(vehicle_fixed_cost, max_distance_cost)` — scales with problem size, always > distance cost but < infeasible_cost

**Lexicographic hierarchy (updated):**

| Level | Constraint | Type | Mechanism |
|-------|-----------|------|-----------|
| 0 | Time windows (STRICT), capacity, temperature | Hard | SetRange, Dimension caps |
| 1 | Minimize fleet size | Soft | SetFixedCostOfVehicle |
| 2 | Minimize total distance | Soft | Arc cost evaluator |
| **2.5** | **Labor hours compliance** | **Soft** | **SetCumulVarSoftUpperBound on LaborMinutes** |
| 3 | Maximize slack time | Soft | SetGlobalSpanCostCoefficient |
| 4 | Drop STANDARD SLA shipments | Soft | Disjunction penalties |

**Pre-solve requirement**: Load driver accumulated minutes into a cache dict before solving. The Celery task (`run_optimization`) queries drivers table and passes the cache to the solver.

## 2. LaborHoursService

Location: `app/services/labor/labor_service.py`

Methods:
- `check_compliance(driver_id)` → `LaborComplianceStatus` (OK/WARNING/VIOLATION with utilization %)
- `check_all_compliance()` → list of all drivers' compliance status
- `record_dispatch(driver_id, route)` → increments driver accumulators + creates `DriverLaborLog` (no-op if disabled)
- `approve_with_override(driver_id, route_id, user_id, reason)` → creates `LaborViolation` with override audit trail

## 3. API Endpoints

Location: `app/api/v1/endpoints/labor.py`, mounted at `/labor`

- `GET /labor/compliance/{driver_id}` — single driver compliance status
- `GET /labor/compliance/summary` — all drivers summary
- `POST /labor/override` — override a violation (requires auth + reason)

All endpoints return `{ enabled: false, data: null }` when feature flag is off.

## 4. Nightly Reconciliation

Celery task: `reconcile_labor_hours`

- Aggregates from `driver_labor_logs` (ground truth)
- Corrects drift in `drivers.accumulated_weekly_minutes` / `accumulated_daily_minutes`
- Resets weekly counters on Monday boundary
- Early return if `ENABLE_LABOR_DIMENSION` is False

## 5. Existing Infrastructure (Already Built)

From Steps 1-2:
- `DriverLaborLog` ORM model (driver_labor_logs table)
- `LaborViolation` ORM model (labor_violations table)
- `Driver` model with `accumulated_weekly_minutes`, `accumulated_daily_minutes`, `weekly_reset_at`
- Alembic migration `002_features_v3` (tables exist in DB)

## 6. Testing Strategy

- **Unit**: LaborHoursService — compliance check, recording, override, feature-flag-off no-op
- **Unit**: Solver labor dimension — driver at 95% weekly limit gets fewer stops, all at limit still produces solution
- **Unit**: Penalty scaling — penalty > distance cost but < infeasible_cost
- **API**: Compliance and override endpoints (enabled + disabled states)
- **Integration**: Dispatch → labor log created → accumulated minutes updated
