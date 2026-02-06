# ICCDDS TODO List

## Current Issue

### MapPage.tsx Shows Nothing

- **Status**: Not Started
- **Priority**: High (fix before or in parallel with v3.1 work)
- **Description**: After optimization completes successfully, navigating to the Map page shows nothing/blank.

#### Investigation Needed

1. Check if MapPage.tsx is receiving route data from the store
2. Verify the map component is properly initialized (Leaflet/MapLibre)
3. Check if route data structure matches what MapPage expects
4. Verify API endpoints for fetching route details with stops/coordinates

#### Possible Causes

- Route data not being passed to map component
- Map tiles not loading (API key or network issue)
- Route coordinates not being fetched from backend
- Store state not persisting when navigating to map page

---

## v3.1 Feature Implementation (Smart Assignment, Dynamic Insertion, Labor Hours)

> Reference: `IMPLEMENTATION_PLAN_THREE_FEATURES.md` for full specs.

### Step 0 — Baseline Test Suite (Pre-requisite)

- [ ] Set up `tests/` directory structure with `conftest.py` (async DB fixtures, test factories)
- [ ] Solver tests: given known inputs, verify expected routes and assignments
- [ ] API endpoint tests: CRUD for vehicles, shipments, routes, depots
- [ ] Temperature calculation tests: `TemperatureTracker` produces realistic values
- [ ] Celery task tests: `run_optimization` flow (submit, progress, complete)
- [ ] Frontend: configure Vitest + React Testing Library, basic smoke tests
- [ ] Target: 80%+ coverage on existing critical paths before any feature work

### Step 1 — Set Up Alembic Migration System

- [ ] Initialize Alembic with current schema as baseline (`001_baseline`)
- [ ] Verify `upgrade` and `downgrade` work on a fresh database
- [ ] Create `002_features_v3.sql` as an Alembic migration (with rollback)

### Step 2 — Foundation (Weeks 1-2)

- [ ] Run migration: `version` column on `routes`, new tables
- [ ] Implement `GeoProvider` abstraction (H3 + Geohash fallback)
- [ ] Unit tests for GeoProvider (both implementations)
- [ ] Verify `version` column default on existing routes
- [ ] Docker/WSL2 environment setup for H3 compatibility

### Step 3 — Dynamic Insertion (Weeks 3-4)

- [ ] Implement `IncrementalInsertionService` with optimistic locking (CAS)
- [ ] Lightweight Temperature Proxy Model with risk scoring
- [ ] API: `POST /routes/{id}/insert`, `POST /routes/{id}/insert/preview`
- [ ] Concurrency tests: simulate 2 concurrent insertions, verify one gets 409
- [ ] Temperature proxy accuracy test (compare proxy vs full TemperatureTracker)
- [ ] Integration test: insert -> resequence stops -> verify version bump

### Step 4 — Smart Assignment (Weeks 5-6)

- [ ] Implement `PatternAnalysisService` with H3 decomposition & weighted average
- [ ] Cold Start inheritance algorithm + confidence scoring
- [ ] API: `GET /recommendations/{route_id}`, `POST /recommendations/preview`
- [ ] Run `backfill_route_signatures` on existing data
- [ ] Unit tests for affinity formula (known inputs -> expected scores)
- [ ] Cold start test (new driver -> inherits parent cell scores)
- [ ] Integration test: complete delivery -> affinity update -> ranking changes

### Step 5 — Labor Hours (Weeks 7-8) [HIGHEST RISK]

- [ ] Add `ENABLE_LABOR_DIMENSION` feature flag to `config.py` (default: off)
- [ ] Implement `LaborConstraintsService` — new `LaborMinutes` dimension in solver
- [ ] Dynamic penalty formula calibration with test scenarios
- [ ] API: `GET /labor/compliance/{driver_id}`, `POST /labor/override`
- [ ] Nightly reconciliation Celery task
- [ ] Solver test: driver at 95% weekly limit -> fewer stops assigned
- [ ] Solver test: all drivers at limit -> solver still produces solution (soft constraint)
- [ ] Penalty scaling test: verify penalty > distance cost but < infeasible_cost
- [ ] Remove feature flag after validation

### Step 6 — Integration and Polish (Weeks 9-10)

- [ ] "Impossible Day" scenario test (all drivers overworked, routes full, STRICT SLA)
- [ ] Chaos test: concurrent insertions + optimization + affinity recalculation
- [ ] Redis caching for affinity scores
- [ ] Verify nightly reconciliation corrects accumulated drift
- [ ] Full E2E: import -> optimize -> insert ad-hoc -> check labor -> complete -> verify affinities
- [ ] Load test: 50 concurrent insertion attempts on same route

---

## Recently Completed

### Optimization Issues (Fixed)

- [x] Progress bar stuck at 0% - Fixed by adding `session.commit()` in `_update_job_status`
- [x] Shipments being dropped unnecessarily - Fixed by changing to `PARALLEL_CHEAPEST_INSERTION` strategy and increasing drop penalty
- [x] Temperature calculations unrealistic (20-50°C) - Fixed by converting minutes to hours in thermodynamic formulas
- [x] Violations disappear on navigation - Fixed by moving to zustand global store
- [x] Vehicles Used showing 0 - Fixed mapping in OptimizationPage.tsx
- [x] Feasibility always showing Infeasible - Fixed by calculating from violations data
- [x] Excessive Celery logging - Reduced update interval and log frequency

---

## Future Enhancements

### Nice to Have

- [ ] Add "No violations" success message when optimization succeeds without issues
- [ ] Add route details panel showing each vehicle's stops
- [ ] Export optimization results to Excel/PDF
- [ ] Real-time vehicle tracking simulation
