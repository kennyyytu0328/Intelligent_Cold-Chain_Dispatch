# ICCDDS TODO List

## Current Focus: Step 4 — Smart Assignment

> Next actionable step in the v3.1 roadmap.

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
- [x] `RecommendationPage.tsx` — two-tab UI (Recommend by Route, Preview by Coordinates)
- [x] `recommendationAPI` in `api.ts` (forRoute, preview, accept)
- [x] Nav item + route + i18n (en + zh-TW)

**Data Pipeline (NOT done — blocks end-to-end testing):**

> **Why it's broken now:** The "Recommend" tab returns 422 because `route_signature` is never populated.
> The "Preview" tab (coordinates) bypasses route_signature but all vehicles return 0.500/LOW
> because `vehicle_hex_affinities` table is empty. Without history, the cold-start fallback
> chain bottoms out at 0.500 for every vehicle — no differentiation.
>
> **Quickest path to a working demo (do these two first):**
> 1. Compute `route_signature` in `tasks.py` (~5 lines) — fixes the 422
> 2. Write a seed script for fake `VehicleHexAffinity` data — gives meaningful rankings

- [x] **Fix `decompose_route_to_cells` fallback**: replaced stub with actual ST_Y/ST_X → H3 conversion in `pattern_analysis.py`
- [x] **Compute `route_signature`** during optimization: in `tasks.py` `_save_routes()`, after creating RouteStops, converts stop lat/lng to H3 cells via `GeoProvider` and saves as `route.route_signature`
- [x] **Seed script for demo data**: `scripts/seed_affinity_data.py` reads existing routes + vehicles and generates realistic `VehicleHexAffinity` + `RouteHexStat` rows (supports `--dry-run`, `--clear`)
- [x] **Backfill existing routes**: `scripts/backfill_route_signatures.py` reads RouteStop PostGIS locations → H3 cells → updates `route_signature` (supports `--dry-run`, `--batch-size`)
- [ ] **Production affinity pipeline** (long-term): after deliveries are marked complete, compute per-vehicle per-cell affinity scores and write to `vehicle_hex_affinities`; aggregate delivery counts per cell into `route_hex_stats`

**Tests:**
- [x] Unit tests for affinity formula (known inputs → expected scores) — `TestCalculateVehicleAffinity` (4 tests)
- [x] Cold start test (new vehicle → inherits parent cell scores via blending) — `TestColdStartFallback` (5 tests)
- [x] Confidence scoring tests — `TestConfidence` (4 tests)
- [x] Decompose coordinates tests — `TestDecomposeCoordinatesToCells` (3 tests)
- [x] Decompose route DB path tests — `TestDecomposeRouteToCells` (5 tests)
- [x] Test `route_signature` is populated after optimization — `TestRouteSignature` (4 tests)
- [x] Recommendation service orchestration tests — 17 tests in `test_recommendation_service.py`
- [x] Recommendation API tests — 10 tests in `test_recommendation_api.py`
- [ ] Integration test: complete delivery → affinity update → ranking changes *(deferred — requires production affinity pipeline)*

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

## Future Enhancements

- [ ] Add "No violations" success message when optimization succeeds without issues
- [ ] Add route details panel showing each vehicle's stops
- [ ] Export optimization results to Excel/PDF
- [ ] Real-time vehicle tracking simulation
