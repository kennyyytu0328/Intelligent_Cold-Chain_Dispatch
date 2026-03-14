# ICCDDS TODO List

## Current Focus: Step 6 — Integration and Polish ✅

> Step 6 complete (2026-03-05). All 6 integration tasks implemented: Impossible Day solver tests, chaos/load tests (50 concurrent insertions), Redis affinity caching, reconciliation drift correction tests, full E2E API flow test, and load test. Total: 37 new tests. Suite: 305 passing.

---

## v3.1 Feature Implementation (Smart Assignment, Dynamic Insertion, Labor Hours)

> Reference: `IMPLEMENTATION_PLAN_THREE_FEATURES.md` for full specs.

### Step 0 — Baseline Test Suite (Pre-requisite) ✅

- [x] Set up `tests/` directory structure with `conftest.py` (async DB fixtures, test factories)
- [x] Solver tests: given known inputs, verify expected routes and assignments
- [x] API endpoint tests: CRUD for vehicles, shipments, routes, depots
- [x] Temperature calculation tests: `TemperatureTracker` produces realistic values
- [x] Celery task tests: `run_optimization` flow (submit, progress, complete) *(partial — GET job status tested)*
- [x] Frontend: configure Vitest + React Testing Library, basic smoke tests
- [x] Target: 80%+ coverage on existing critical paths before any feature work *(70% overall, 97-100% on solver/domain)*

### Step 1 — Set Up Alembic Migration System ✅

- [x] Initialize Alembic with current schema as baseline (`001_baseline`)
- [x] Verify `upgrade` and `downgrade` work on a fresh database
- [x] Create `002_features_v3` as an Alembic migration (with rollback)
- [x] Migration tests: 13 tests (structural + functional upgrade/downgrade/round-trip)

### Step 2 — Foundation (GeoProvider + v3.1 ORM Models) ✅

- [x] Add `h3>=4.0.0` and `pygeohash>=0.8.5` dependencies
- [x] Add `h3_resolution` setting to config (default 7, range 0-15)
- [x] Update Route model: `version`, `route_signature`, `actual_success_score` columns
- [x] Update Driver model: `accumulated_weekly_minutes`, `accumulated_daily_minutes`, `weekly_reset_at` columns
- [x] Create 5 new ORM models: `RouteHexStat`, `VehicleHexAffinity`, `InsertionAttempt`, `DriverLaborLog`, `LaborViolation`
- [x] Implement `GeoProvider` ABC with `H3Provider` and `GeohashProvider` fallback + factory
- [x] 64 new tests (35 GeoProvider + 29 model tests), all passing (186 total)
- [x] Update STARTUP_GUIDE.md and README.md with Alembic migration steps

### Step 3 — Dynamic Insertion (Weeks 3-4) ✅

- [x] Implement `IncrementalInsertionService` with optimistic locking (CAS)
- [x] Lightweight Temperature Proxy Model with risk scoring
- [x] API: `POST /routes/{id}/insert`, `POST /routes/{id}/insert/preview`, `GET /routes/{id}/insertion-history`
- [x] Concurrency tests: CAS conflict detection (StaleRouteException on version mismatch)
- [x] Temperature proxy accuracy test (risk score zones GREEN/YELLOW/RED, insulation comparison)
- [x] Integration test: insert → resequence stops → verify version bump
- [x] 33 new tests (15 temperature proxy + 11 service + 7 API), all passing (219 total)

### Step 4 — Smart Assignment (Weeks 5-6)

**Backend Service & API (done):**
- [x] Implement `PatternAnalysisService` with H3 decomposition & weighted average
- [x] Cold Start inheritance algorithm + confidence scoring
- [x] API: `GET /recommendations/{route_id}`, `POST /recommendations/preview`, `POST /recommendations/{route_id}/accept`
- [x] `RecommendationService` orchestration (rank vehicles, accept assignment)

**Frontend UI (done):**
- [x] `RecommendationPage.tsx` — two-tab UI (Recommend by Route, Preview by Addresses)
- [x] `recommendationAPI` + `geocodingAPI` in `api.ts` (forRoute, preview, accept, geocode)
- [x] Nav item + route + i18n (en + zh-TW)
- [x] **Preview tab redesigned**: replaced raw lat/lng inputs with address entry + per-row Geocode button (Nominatim), shows resolved coordinates inline, Enter key triggers geocode

**Data Pipeline (done):**

- [x] **Fix `decompose_route_to_cells` fallback**: replaced stub with actual ST_Y/ST_X → H3 conversion in `pattern_analysis.py`
- [x] **Compute `route_signature`** during optimization: in `tasks.py` `_save_routes()`, after creating RouteStops, converts stop lat/lng to H3 cells via `GeoProvider` and saves as `route.route_signature`
- [x] **Seed script for demo data**: `scripts/seed_affinity_data.py` reads existing routes + vehicles and generates realistic `VehicleHexAffinity` + `RouteHexStat` rows (supports `--dry-run`, `--clear`)
- [x] **Backfill existing routes**: `scripts/backfill_route_signatures.py` reads RouteStop PostGIS locations → H3 cells → updates `route_signature` (supports `--dry-run`, `--batch-size`)
- [x] **Production affinity pipeline**: `AffinityUpdateService` triggers on route COMPLETED status, computes success score via running average, upserts `VehicleHexAffinity` + `RouteHexStat` per H3 cell — 14 new tests (10 unit + 2 integration + 2 API trigger)

**Tests:**
- [x] Unit tests for affinity formula (known inputs → expected scores) — `TestCalculateVehicleAffinity` (4 tests)
- [x] Cold start test (new vehicle → inherits parent cell scores via blending) — `TestColdStartFallback` (5 tests)
- [x] Confidence scoring tests — `TestConfidence` (4 tests)
- [x] Decompose coordinates tests — `TestDecomposeCoordinatesToCells` (3 tests)
- [x] Decompose route DB path tests — `TestDecomposeRouteToCells` (5 tests)
- [x] Test `route_signature` is populated after optimization — `TestRouteSignature` (4 tests)
- [x] Recommendation service orchestration tests — 17 tests in `test_recommendation_service.py`
- [x] Recommendation API tests — 10 tests in `test_recommendation_api.py`
- [x] Integration test: complete delivery → affinity update → ranking changes — `test_affinity_integration.py` (2 tests) + `test_affinity_trigger.py` (2 tests)

### Step 4 Status: ✅ COMPLETE (293 backend tests, 76% coverage)

---

### Step 5 — Labor Hours (Weeks 7-8) ✅

- [x] Add `ENABLE_LABOR_DIMENSION` feature flag to `config.py` (default: off)
- [x] Add Pydantic schemas for labor compliance (`app/schemas/labor.py`)
- [x] Implement `LaborHoursService` — compliance checks, dispatch recording, override with audit trail
- [x] Implement `LaborMinutes` soft dimension in OR-Tools solver with per-driver caps
- [x] Dynamic penalty formula calibration (500/min — redistributes work without causing shipment drops)
- [x] API: `GET /labor/compliance/summary`, `GET /labor/compliance/{driver_id}`, `POST /labor/override`
- [x] Wire labor caches into Celery optimization task
- [x] Nightly reconciliation Celery task (`reconcile_labor_hours`)
- [x] Solver test: all drivers at limit → solver still produces solution (soft constraint)
- [x] Penalty scaling test: verify penalty < infeasible_cost
- [x] 19 new tests (8 service + 4 API + 5 solver + 2 reconciliation)

### Step 5 Status: ✅ COMPLETE (312 backend tests, 76% coverage)

### Step 6 — Integration and Polish (Weeks 9-10)

- [x] "Impossible Day" scenario test (all drivers overworked, routes full, STRICT SLA) — `tests/solver/test_impossible_day.py` (5 tests)
- [x] Chaos test: concurrent insertions + optimization + affinity recalculation — `tests/unit/test_chaos_concurrent.py` (5 tests)
- [x] Redis caching for affinity scores — `app/services/recommendation/pattern_analysis.py` + `tests/unit/test_affinity_cache.py` (13 tests)
- [x] Verify nightly reconciliation corrects accumulated drift — `tests/unit/test_labor_reconciliation.py` extended (4 new tests)
- [x] Full E2E: import -> optimize -> insert ad-hoc -> check labor -> complete -> verify affinities — `tests/api/test_e2e_flow.py` (10 tests)
- [x] Load test: 50 concurrent insertion attempts on same route — included in `test_chaos_concurrent.py`

### Step 6 Status: ✅ COMPLETE (349 backend tests, 305 passing non-solver/non-migration)

---

## Completed Issues

### MapPage Shows Nothing After Optimization ✅

- **Root Cause**: Silent API failure in OptimizationPage + MapPage had zero independent data fetching
- **Fix**: Added `planDate` to Zustand store, MapPage now re-fetches routes independently, added empty/error/loading states
- **Files changed**: `optimizationStore.ts`, `OptimizationPage.tsx`, `MapPage.tsx`, `en.json`, `zh-TW.json`

### Optimization Issues (Fixed) ✅

- [x] Progress bar stuck at 0% — Fixed by adding `session.commit()` in `_update_job_status`
- [x] Shipments being dropped unnecessarily — Fixed by changing to `PARALLEL_CHEAPEST_INSERTION` strategy and increasing drop penalty
- [x] Temperature calculations unrealistic (20-50°C) — Fixed by converting minutes to hours in thermodynamic formulas
- [x] Violations disappear on navigation — Fixed by moving to Zustand global store
- [x] Vehicles Used showing 0 — Fixed mapping in OptimizationPage.tsx
- [x] Feasibility always showing Infeasible — Fixed by calculating from violations data
- [x] Excessive Celery logging — Reduced update interval and log frequency

---

## Recent Changes

### Time Windows Made Optional ✅ (2026-03-14)
- [x] `ShipmentCreate.time_windows` changed from required to optional (defaults to empty list)
- [x] Empty time windows = "deliver anytime" (solver defaults to full-day window 00:00–24:00)
- [x] ORM model helper methods (`is_time_valid`, `get_earliest_start`, `get_latest_end`) handle empty gracefully
- [x] Excel import allows blank time window columns (removed validation error)
- [x] Template instructions updated to reflect optional time windows

## Future Enhancements

- [ ] Add "No violations" success message when optimization succeeds without issues
- [ ] Add route details panel showing each vehicle's stops
- [ ] Export optimization results to Excel/PDF
- [ ] Real-time vehicle tracking simulation
