這是一份經過最終技術審查與架構優化的 **Implementation Plan v3.1**。

這份文件整合了所有關於 **OR-Tools 建模細節**、**資料一致性**、**Windows 相容性** 以及 **開發順序調整** 的決策，並補齊了 v3.0 中缺失的公式、API 合約、整合細節與遷移策略。這將是給開發團隊的**最終定案規格書 (Final Production Specification)**。

---

# Implementation Plan v3.1: Final Production Spec for ICCDDS

## 1. Executive Summary & Architectural Strategy

**Objective:** Implement three intelligent features (Smart Assignment, Labor Compliance, Dynamic Insertion) with commercial-grade resilience and "Always Feasible" design principles.

**Key Architectural Decisions (ADR):**

1. **Weighted Route Signatures:** Replaced simple clustering with multi-cell **H3/Geohash Weighted Average** to capture complex route characteristics.
2. **Soft Constraints with Dynamic Penalties:** Labor limits use a dynamic penalty formula relative to distance/time costs to prevent "No Solution" scenarios.
3. **Optimistic Locking (CAS):** Concurrency control relies strictly on `version` checking (Compare-And-Swap), removing redundant boolean locks.
4. **Hybrid Data Consistency:** Labor hours use transactional updates for real-time reads, backed by a nightly reconciliation job for absolute accuracy.

---

## 2. Feature 1: Smart Route/Sequence Assignment (Refined)

*Goal: Recommend optimal vehicle-route pairings based on "Route Signatures" and historical success.*

### Architecture Refinement

* **Logic:** A route is defined by a **"Signature"** (a collection of visited H3 cells).
* **Scoring:** The affinity score is a weighted average of the driver's performance in *all* cells covered by the route.

### Database Schema Changes

**New Tables:**

```sql
-- Performance metrics per hex zone (aggregated from historical deliveries)
CREATE TABLE route_hex_stats (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    h3_index VARCHAR(20) NOT NULL,          -- H3 cell index (Resolution 7)
    total_deliveries INTEGER DEFAULT 0,      -- Total deliveries in this cell
    avg_service_time_minutes INTEGER,         -- Average actual service time
    avg_delay_minutes DECIMAL(6,2) DEFAULT 0, -- Avg delay (negative = early)
    difficulty_factor DECIMAL(4,3) DEFAULT 0.5, -- 0.0 (easy) to 1.0 (hard)
    updated_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT uq_route_hex_stats_h3 UNIQUE (h3_index)
);
CREATE INDEX idx_route_hex_stats_h3 ON route_hex_stats (h3_index);

-- Driver/Vehicle performance per zone (the core affinity data)
CREATE TABLE vehicle_hex_affinities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    vehicle_id UUID NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    driver_id UUID REFERENCES drivers(id) ON DELETE SET NULL,
    h3_index VARCHAR(20) NOT NULL,
    affinity_score DECIMAL(4,3) DEFAULT 0.5, -- 0.000 to 1.000
    sample_size INTEGER DEFAULT 0,            -- Number of deliveries scored
    avg_on_time_rate DECIMAL(4,3),            -- 0.0 to 1.0
    avg_temp_compliance_rate DECIMAL(4,3),     -- 0.0 to 1.0
    last_delivery_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT uq_vehicle_hex_affinity UNIQUE (vehicle_id, h3_index)
);
CREATE INDEX idx_vha_vehicle ON vehicle_hex_affinities (vehicle_id);
CREATE INDEX idx_vha_h3 ON vehicle_hex_affinities (h3_index);
CREATE INDEX idx_vha_score ON vehicle_hex_affinities (affinity_score DESC);
```

**Table Modifications (`routes`):**

```sql
ALTER TABLE routes ADD COLUMN route_signature JSONB DEFAULT '[]'::jsonb;
  -- Array of H3 indices: ["872830828ffffff", "872830829ffffff", ...]
ALTER TABLE routes ADD COLUMN actual_success_score DECIMAL(4,3);
  -- Post-delivery score: weighted average of on_time + temp_compliant across all stops
```

### Core Services Logic

* **`PatternAnalysisService`:**

1. **Decomposition:** Breakdown route stops into a set of H3 cells (Resolution 7 ~1.2km).

```python
# Uses h3-py with geohash fallback (see Risk Mitigation)
def decompose_route(stops: list[RouteStop]) -> list[str]:
    """Convert stop coordinates to H3 cell indices."""
    cells = set()
    for stop in stops:
        cell = geo_provider.lat_lng_to_cell(stop.latitude, stop.longitude, resolution=7)
        cells.add(cell)
    return sorted(cells)
```

2. **Affinity Calculation (Weighted Average):**

```
AffinityScore(vehicle_v, route_R) =
    Σ(cell_c ∈ R) [ w(c) × affinity(v, c) ]
    ─────────────────────────────────────────
              Σ(cell_c ∈ R) [ w(c) ]

Where:
  w(c)          = route_hex_stats[c].total_deliveries  (busier cells weigh more)
  affinity(v,c) = vehicle_hex_affinities[v, c].affinity_score

  If affinity(v,c) is missing → use Cold Start value (see below)
```

The **individual cell affinity** is updated after each completed delivery:

```
affinity(v, c) =
    α × on_time_rate(v, c) +
    β × temp_compliance_rate(v, c) +
    γ × (1 - normalized_service_time(v, c))

Where:
  α = 0.4  (on-time weight)
  β = 0.4  (temperature compliance weight)
  γ = 0.2  (service efficiency weight)

  normalized_service_time = actual_service_time / avg_service_time_for_cell
  (clamped to [0, 2] to avoid outlier distortion)
```

3. **Cold Start Strategy (Inheritance):**

When a vehicle/driver has insufficient data for a cell (`sample_size < 10`):

```
affinity_cold(v, c) =
    λ × affinity_parent(v, c)  +  (1 - λ) × affinity_global(c)

Where:
  λ = sample_size / 10   (linear ramp from 0 → 1 as data accumulates)

  affinity_parent(v, c):
    1. Check the vehicle's affinity in the parent H3 cell (Resolution 6, ~4.5km)
    2. If also missing → use the vehicle's global average affinity across all cells
    3. If no data at all → 0.5 (neutral default)

  affinity_global(c):
    Average affinity of ALL vehicles in cell c
    If no vehicles have visited cell c → 0.5
```

* **`RecommendationService`:**

```python
async def recommend_vehicles(
    route_signature: list[str],
    available_vehicles: list[Vehicle],
    top_k: int = 5
) -> list[VehicleRecommendation]:
    """Rank vehicles by weighted affinity score for a given route signature."""
    rankings = []
    for vehicle in available_vehicles:
        score = await self.pattern_service.calculate_affinity(
            vehicle_id=vehicle.id,
            route_cells=route_signature
        )
        confidence = await self._calculate_confidence(vehicle.id, route_signature)
        rankings.append(VehicleRecommendation(
            vehicle_id=vehicle.id,
            license_plate=vehicle.license_plate,
            driver_name=vehicle.driver_name,
            affinity_score=score,         # 0.0 - 1.0
            confidence_level=confidence,  # LOW / MEDIUM / HIGH
            sample_coverage=...,          # % of route cells with data
        ))

    return sorted(rankings, key=lambda r: r.affinity_score, reverse=True)[:top_k]
```

**Confidence Levels:**
- **HIGH:** ≥70% of route cells have `sample_size ≥ 10` for this vehicle
- **MEDIUM:** 30-70% coverage
- **LOW:** <30% coverage (mostly cold-start estimates)

### API Endpoints

```
GET  /api/v1/recommendations/{route_id}
  Description: Get ranked vehicle recommendations for an existing route
  Query params: top_k (int, default 5)
  Response: {
    "route_id": "uuid",
    "route_signature": ["872830828ffffff", ...],
    "recommendations": [
      {
        "vehicle_id": "uuid",
        "license_plate": "ABC-1234",
        "driver_name": "王小明",
        "affinity_score": 0.847,
        "confidence_level": "HIGH",
        "sample_coverage": 0.85,
        "cell_details": [
          {"h3_index": "872830828ffffff", "affinity": 0.92, "sample_size": 47},
          ...
        ]
      }
    ]
  }

POST /api/v1/recommendations/preview
  Description: Preview recommendations for a proposed set of stops (before route creation)
  Body: {
    "stop_coordinates": [{"latitude": 25.033, "longitude": 121.565}, ...],
    "available_vehicle_ids": ["uuid", ...] (optional, defaults to all AVAILABLE)
  }
  Response: Same as above

POST /api/v1/recommendations/{route_id}/accept
  Description: Accept a recommendation and assign the vehicle to the route
  Body: {"vehicle_id": "uuid"}
  Response: RouteResponse (updated route with assigned vehicle)

POST /api/v1/admin/affinities/recalculate
  Description: Trigger full recalculation of all affinity scores from historical data
  Response: HTTP 202 {"task_id": "uuid", "status": "QUEUED"}
```

---

## 3. Feature 2: Dynamic Schedule Adjustment (Moved to Phase 2)

*Goal: Incremental insertion with strict concurrency protection.*

### Architecture Refinement

* **Locking:** Pure **Optimistic Locking**. No explicit "lock" flags.
* **Temperature Model:** Use a **Lightweight Proxy Model** for speed (<1s response), not full simulation.

### Database Schema Changes

**Table Modifications (`routes`):**

```sql
ALTER TABLE routes ADD COLUMN version INTEGER NOT NULL DEFAULT 1;
  -- Incremented on every update, used for optimistic locking (CAS)
```

**New Table (`insertion_attempts`):**

```sql
CREATE TABLE insertion_attempts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    route_id UUID NOT NULL REFERENCES routes(id) ON DELETE CASCADE,
    shipment_id UUID NOT NULL REFERENCES shipments(id),
    target_route_version INTEGER NOT NULL,       -- Route version at time of attempt
    proposed_position INTEGER NOT NULL,          -- Insertion index in stop sequence
    temp_risk_score DECIMAL(5,3),                -- 0.0 (safe) to 1.0+ (risky)
    delay_impact_minutes INTEGER,                -- Added delay to subsequent stops
    extra_distance_meters INTEGER,               -- Additional distance from detour
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
      -- PENDING, ACCEPTED, REJECTED, CONFLICT
    rejection_reason TEXT,                        -- Why it was rejected
    attempted_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT now(),
    resolved_at TIMESTAMPTZ
);
CREATE INDEX idx_insertion_route ON insertion_attempts (route_id);
CREATE INDEX idx_insertion_status ON insertion_attempts (status) WHERE status = 'PENDING';
```

### Core Services Logic

* **`IncrementalInsertionService`:**

1. **Snapshot:** Read Route X with current version.

```python
async def attempt_insertion(
    self, route_id: UUID, shipment_id: UUID, user_id: UUID
) -> InsertionResult:
    # Step 1: Read current route state
    route = await self.session.get(Route, route_id)
    snapshot_version = route.version
    stops = route.get_stops_ordered()
```

2. **Find Best Position:** Evaluate all possible insertion positions.

```python
    # Step 2: Evaluate each candidate position
    candidates = []
    for position in range(1, len(stops) + 1):  # After each existing stop
        cost = self._evaluate_insertion(route, shipment, position)
        candidates.append(InsertionCandidate(
            position=position,
            extra_distance_meters=cost.extra_distance,
            delay_impact_minutes=cost.delay_impact,
            temp_risk_score=cost.temp_risk,
        ))

    # Pick lowest-cost feasible candidate
    best = min(
        [c for c in candidates if c.temp_risk_score < TEMP_RISK_THRESHOLD],
        key=lambda c: c.extra_distance_meters,
        default=None
    )
    if best is None:
        return InsertionResult(status="REJECTED", reason="No feasible position")
```

3. **Proxy Temperature Check:**

The proxy model uses constants already defined in `app/models/enums.py` to provide a fast risk estimate without running the full `TemperatureTracker`:

```
TempRiskScore =
    (ExtraDistance_km / AverageSpeed_kmh) × (T_ambient - T_current_estimate) × K_value
    ─────────────────────────────────────────────────────────────────────────────────────
                            ΔT_budget

Where:
  ExtraDistance_km    = detour distance (going to new stop and back to sequence)
  AverageSpeed_kmh   = settings.average_speed_kmh (default: 30)
  T_ambient           = settings.default_ambient_temperature (default: 30°C)
  T_current_estimate = route.initial_temperature + cumulative_rise_to_insertion_point
  K_value             = vehicle.k_value (from InsulationGrade: 0.02 / 0.05 / 0.10)
  ΔT_budget           = shipment.temp_limit_upper - T_current_estimate
                        (remaining temperature headroom)

Thresholds:
  TempRiskScore < 0.5  → GREEN  (safe to insert)
  TempRiskScore 0.5-0.8 → YELLOW (warn dispatcher, allow with confirmation)
  TempRiskScore > 0.8  → RED    (reject insertion, recommend full re-optimization)
```

4. **Apply with Optimistic Lock (CAS):**

```python
    # Step 4: Atomic update with version check
    result = await self.session.execute(
        update(Route)
        .where(Route.id == route_id, Route.version == snapshot_version)
        .values(
            version=Route.version + 1,
            total_stops=Route.total_stops + 1,
            total_distance=Route.total_distance + best.extra_distance_meters / 1000,
            updated_at=func.now(),
        )
        .returning(Route.version)
    )

    if result.rowcount == 0:
        # Another user modified this route concurrently
        raise StaleRouteException(
            route_id=route_id,
            expected_version=snapshot_version,
            message="Route was modified by another user. Please refresh and retry."
        )

    # Step 5: Insert new RouteStop and resequence subsequent stops
    await self._insert_stop_at_position(route_id, shipment, best.position)
    await self._resequence_stops(route_id, from_position=best.position + 1)
```

5. **Concurrency Handler:** If `rows_affected == 0`, throw `StaleRouteException` → Frontend prompts user to refresh.

### API Endpoints

```
POST /api/v1/routes/{route_id}/insert
  Description: Insert a new shipment into an existing route
  Body: {
    "shipment_id": "uuid",
    "preferred_position": null  (optional, auto-picks best if null)
  }
  Response (200): {
    "insertion_id": "uuid",
    "status": "ACCEPTED",
    "position": 3,
    "temp_risk_score": 0.32,
    "temp_risk_level": "GREEN",
    "delay_impact_minutes": 12,
    "extra_distance_meters": 2400,
    "updated_route_version": 6
  }
  Error (409 Conflict): {
    "error": "STALE_ROUTE",
    "message": "Route was modified. Current version: 7, your version: 5",
    "current_version": 7
  }
  Error (422): {
    "error": "INSERTION_REJECTED",
    "reason": "Temperature risk too high (score: 0.92)",
    "temp_risk_score": 0.92
  }

POST /api/v1/routes/{route_id}/insert/preview
  Description: Preview insertion impact without applying changes
  Body: {"shipment_id": "uuid"}
  Response: {
    "candidates": [
      {
        "position": 2,
        "temp_risk_score": 0.32,
        "temp_risk_level": "GREEN",
        "delay_impact_minutes": 8,
        "extra_distance_meters": 1800
      },
      {
        "position": 3,
        "temp_risk_score": 0.55,
        "temp_risk_level": "YELLOW",
        "delay_impact_minutes": 15,
        "extra_distance_meters": 3200
      }
    ],
    "recommended_position": 2,
    "route_version": 5
  }

GET /api/v1/routes/{route_id}/insertion-history
  Description: View past insertion attempts for a route
  Response: list[InsertionAttempt]
```

---

## 4. Feature 3: Labor Hours Distribution (Moved to Phase 3)

*Goal: Enforce regulations using Soft Constraints with penalty logic.*

### Architecture Refinement

* **Soft Constraints:** Solver *must* return a solution. Violations are penalized.
* **Data Sync:** Transactional write on dispatch + Nightly heavy recalculation.

### Database Schema Changes

**New Tables:**

```sql
-- Granular labor log per driver per shift
CREATE TABLE driver_labor_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    driver_id UUID NOT NULL REFERENCES drivers(id) ON DELETE CASCADE,
    route_id UUID REFERENCES routes(id) ON DELETE SET NULL,
    log_date DATE NOT NULL,
    shift_start TIMESTAMPTZ NOT NULL,
    shift_end TIMESTAMPTZ,                       -- NULL if shift is ongoing
    drive_time_minutes INTEGER DEFAULT 0,
    service_time_minutes INTEGER DEFAULT 0,
    break_time_minutes INTEGER DEFAULT 0,
    total_minutes INTEGER GENERATED ALWAYS AS
        (drive_time_minutes + service_time_minutes) STORED,
    source VARCHAR(20) DEFAULT 'SYSTEM',          -- SYSTEM, MANUAL, RECONCILIATION
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT uq_driver_labor_log UNIQUE (driver_id, route_id, log_date)
);
CREATE INDEX idx_labor_driver_date ON driver_labor_logs (driver_id, log_date);
CREATE INDEX idx_labor_week ON driver_labor_logs (driver_id, log_date)
    WHERE log_date >= CURRENT_DATE - INTERVAL '7 days';

-- Audit trail for labor violation overrides
CREATE TABLE labor_violations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    driver_id UUID NOT NULL REFERENCES drivers(id),
    route_id UUID REFERENCES routes(id),
    violation_type VARCHAR(30) NOT NULL,
      -- WEEKLY_LIMIT_EXCEEDED, DAILY_LIMIT_EXCEEDED, CONSECUTIVE_DAYS
    severity VARCHAR(10) NOT NULL DEFAULT 'WARNING',
      -- WARNING, VIOLATION, CRITICAL
    projected_minutes INTEGER NOT NULL,           -- Projected total if assigned
    limit_minutes INTEGER NOT NULL,               -- The limit being exceeded
    overage_minutes INTEGER NOT NULL,             -- projected - limit
    was_overridden BOOLEAN DEFAULT FALSE,
    overridden_by UUID REFERENCES users(id),
    override_reason TEXT,
    override_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_violation_driver ON labor_violations (driver_id);
CREATE INDEX idx_violation_unresolved ON labor_violations (was_overridden)
    WHERE was_overridden = FALSE;
```

**Table Modifications (`drivers`):**

```sql
ALTER TABLE drivers ADD COLUMN accumulated_weekly_minutes INTEGER DEFAULT 0;
  -- Denormalized: fast read for solver. Updated transactionally on dispatch.
  -- Ground truth: nightly reconciliation from driver_labor_logs.

ALTER TABLE drivers ADD COLUMN accumulated_daily_minutes INTEGER DEFAULT 0;
  -- Today's accumulated minutes.

ALTER TABLE drivers ADD COLUMN weekly_reset_at TIMESTAMPTZ;
  -- When accumulated_weekly_minutes was last reset (Monday 00:00).
```

### Regulatory Limits (Configurable in `config.py`)

```python
# Labor compliance settings (add to Settings class)
DRIVER_WEEKLY_LIMIT_MINUTES: int = 2880       # 48 hours (Taiwan Labor Standards Act)
DRIVER_DAILY_LIMIT_MINUTES: int = 720         # 12 hours (including overtime)
DRIVER_DAILY_DRIVE_LIMIT_MINUTES: int = 600   # 10 hours driving only
LABOR_WARNING_THRESHOLD: float = 0.85          # Warn at 85% of limit
```

### Core Services Logic

* **`LaborConstraintsService` (OR-Tools Integration):**

**Dynamic Penalty Formula:**

```
LaborPenalty(driver_d, route_R) =
    MAX(vehicle_fixed_cost, max_route_distance_cost) × OverageFactor

Where:
  vehicle_fixed_cost     = settings.vehicle_fixed_cost (default: 50,000)
  max_route_distance_cost = max distance in meters across all routes in this solution
  OverageFactor          = (projected_weekly_minutes - weekly_limit) / 60
                           (overage expressed in hours, min 1.0)

Example:
  vehicle_fixed_cost      = 50,000
  max_route_distance_cost = 45,000 (45km route)
  projected_weekly         = 3060 minutes (51 hours)
  weekly_limit             = 2880 minutes (48 hours)
  OverageFactor            = (3060 - 2880) / 60 = 3.0

  LaborPenalty = MAX(50000, 45000) × 3.0 = 150,000

This ensures:
  - Penalty SCALES with overage (not flat)
  - Penalty is ALWAYS higher than just adding distance (solver won't ignore it)
  - Penalty is LOWER than infeasible_cost (solver won't refuse to produce a solution)
  - Solver prefers "On-time but Overworked" over "Late Delivery"
  - Solver prefers "Efficient Route" over "Overworked" if possible
```

**Integration with Existing ColdChainVRPSolver:**

The labor constraint is added as a **new dimension** in the solver, sitting at **Level 2.5** in the lexicographic hierarchy (between distance and slack):

```python
# In solver.py: _add_labor_dimension() — NEW METHOD

def _add_labor_dimension(self):
    """Add labor hours as a soft-capped dimension to the routing model."""

    def labor_transit_callback(from_index, to_index):
        """Returns estimated work minutes for traveling from_index → to_index."""
        from_node = self.manager.IndexToNode(from_index)
        to_node = self.manager.IndexToNode(to_index)
        travel_minutes = self.data.time_matrix[from_node][to_node]
        service_minutes = self.data.nodes[from_node].service_duration if from_node != 0 else 0
        return travel_minutes + service_minutes

    transit_callback_index = self.routing.RegisterTransitCallback(labor_transit_callback)

    # Add dimension: tracks cumulative work minutes per vehicle
    self.routing.AddDimension(
        transit_callback_index,
        0,           # no slack (work time is always counted)
        1440,        # max 24h hard cap per route (safety net)
        True,        # start cumul to zero
        "LaborMinutes"
    )

    labor_dimension = self.routing.GetDimensionOrDie("LaborMinutes")

    # Apply per-vehicle soft upper bound based on remaining weekly capacity
    for vehicle_idx, vehicle_data in enumerate(self.data.vehicles):
        remaining_daily = self._get_remaining_daily_minutes(vehicle_data.driver_id)
        remaining_weekly = self._get_remaining_weekly_minutes(vehicle_data.driver_id)
        effective_limit = min(remaining_daily, remaining_weekly)

        end_index = self.routing.End(vehicle_idx)

        # Soft upper bound: allowed to exceed, but penalized
        labor_dimension.SetCumulVarSoftUpperBound(
            end_index,
            int(effective_limit),
            self._calculate_labor_penalty(vehicle_data)
        )

def _calculate_labor_penalty(self, vehicle_data: VehicleData) -> int:
    """Dynamic penalty that scales with problem size."""
    return max(
        self.data.vehicle_fixed_cost,
        self._get_max_route_distance_estimate()
    )

def _get_remaining_weekly_minutes(self, driver_id: str) -> int:
    """Weekly limit minus accumulated minutes (from drivers table)."""
    accumulated = self.driver_labor_cache.get(driver_id, 0)
    return max(0, self.weekly_limit - accumulated)

def _get_remaining_daily_minutes(self, driver_id: str) -> int:
    """Daily limit minus today's accumulated minutes."""
    accumulated = self.driver_daily_cache.get(driver_id, 0)
    return max(0, self.daily_limit - accumulated)
```

**Updated Lexicographic Hierarchy:**

| Level | Constraint | Type | Mechanism |
|-------|-----------|------|-----------|
| 0 | Time windows (STRICT), capacity, temperature | Hard | SetRange, Dimension caps |
| 1 | Minimize fleet size | Soft | `SetFixedCostOfVehicle` |
| 2 | Minimize total distance | Soft | Arc cost evaluator |
| **2.5** | **Labor hours compliance** | **Soft** | **`SetCumulVarSoftUpperBound` on LaborMinutes dimension** |
| 3 | Maximize slack time | Soft | `SetGlobalSpanCostCoefficient` |
| 4 | Drop STANDARD SLA shipments | Soft | Disjunction penalties |

* **`LaborHoursService`:**

```python
class LaborHoursService:
    """Manages driver labor hour tracking and compliance checks."""

    async def check_compliance(self, driver_id: UUID) -> LaborComplianceStatus:
        """Check current compliance status for a driver."""
        driver = await self.session.get(Driver, driver_id)
        weekly_pct = driver.accumulated_weekly_minutes / WEEKLY_LIMIT
        daily_pct = driver.accumulated_daily_minutes / DAILY_LIMIT
        return LaborComplianceStatus(
            driver_id=driver_id,
            weekly_minutes=driver.accumulated_weekly_minutes,
            weekly_limit=WEEKLY_LIMIT,
            weekly_utilization=weekly_pct,
            daily_minutes=driver.accumulated_daily_minutes,
            daily_limit=DAILY_LIMIT,
            daily_utilization=daily_pct,
            status="OK" if weekly_pct < 0.85 else "WARNING" if weekly_pct < 1.0 else "VIOLATION",
        )

    async def record_dispatch(self, driver_id: UUID, route: Route) -> None:
        """Write Path: Increment accumulated minutes when route is approved."""
        estimated_minutes = route.total_duration or 0
        await self.session.execute(
            update(Driver)
            .where(Driver.id == driver_id)
            .values(
                accumulated_weekly_minutes=Driver.accumulated_weekly_minutes + estimated_minutes,
                accumulated_daily_minutes=Driver.accumulated_daily_minutes + estimated_minutes,
            )
        )

        # Create labor log entry
        log = DriverLaborLog(
            driver_id=driver_id,
            route_id=route.id,
            log_date=route.plan_date,
            shift_start=route.planned_departure_at,
            drive_time_minutes=estimated_minutes,  # refined later from actuals
            source="SYSTEM",
        )
        self.session.add(log)

    async def approve_with_override(
        self, driver_id: UUID, route: Route, user_id: UUID, reason: str
    ) -> None:
        """Override labor violation with audit trail."""
        violation = LaborViolation(
            driver_id=driver_id,
            route_id=route.id,
            violation_type="WEEKLY_LIMIT_EXCEEDED",
            severity="VIOLATION",
            projected_minutes=driver.accumulated_weekly_minutes + route.total_duration,
            limit_minutes=WEEKLY_LIMIT,
            overage_minutes=projected - WEEKLY_LIMIT,
            was_overridden=True,
            overridden_by=user_id,
            override_reason=reason,
            override_at=func.now(),
        )
        self.session.add(violation)
        await self.record_dispatch(driver_id, route)
```

* **Nightly Reconciliation Celery Task:**

```python
@celery_app.task(
    bind=True,
    name="app.services.tasks.reconcile_labor_hours",
    queue="default",
    soft_time_limit=1200,
)
def reconcile_labor_hours(self):
    """
    Nightly job: Recalculate accumulated_weekly_minutes from ground truth
    (driver_labor_logs) and fix any drift from transactional updates.
    Scheduled via Celery Beat at 02:00 daily.
    """
    with Session(sync_engine) as session:
        # Get current ISO week boundaries
        today = date.today()
        week_start = today - timedelta(days=today.weekday())  # Monday

        # Aggregate actual hours from labor logs
        results = session.execute(text("""
            UPDATE drivers d
            SET accumulated_weekly_minutes = COALESCE(agg.total, 0),
                accumulated_daily_minutes = COALESCE(daily.total, 0),
                weekly_reset_at = :week_start,
                updated_at = now()
            FROM (
                SELECT driver_id, SUM(total_minutes) as total
                FROM driver_labor_logs
                WHERE log_date >= :week_start
                GROUP BY driver_id
            ) agg
            LEFT JOIN (
                SELECT driver_id, SUM(total_minutes) as total
                FROM driver_labor_logs
                WHERE log_date = :today
                GROUP BY driver_id
            ) daily ON agg.driver_id = daily.driver_id
            WHERE d.id = agg.driver_id
        """), {"week_start": week_start, "today": today})

        session.commit()
        return {"reconciled_drivers": results.rowcount}
```

### API Endpoints

```
GET  /api/v1/labor/compliance/{driver_id}
  Description: Get current labor compliance status for a driver
  Response: {
    "driver_id": "uuid",
    "driver_name": "王小明",
    "weekly": {
      "accumulated_minutes": 2400,
      "limit_minutes": 2880,
      "utilization": 0.833,
      "remaining_minutes": 480,
      "status": "OK"                     -- OK / WARNING / VIOLATION
    },
    "daily": {
      "accumulated_minutes": 480,
      "limit_minutes": 720,
      "utilization": 0.667,
      "remaining_minutes": 240,
      "status": "OK"
    },
    "recent_logs": [
      {
        "date": "2024-01-29",
        "route_code": "R-20240129-003",
        "total_minutes": 420,
        "source": "SYSTEM"
      }
    ]
  }

GET  /api/v1/labor/compliance/summary
  Description: Dashboard overview of all drivers' compliance
  Response: {
    "total_drivers": 15,
    "ok_count": 10,
    "warning_count": 3,
    "violation_count": 2,
    "drivers": [
      {
        "driver_id": "uuid",
        "driver_name": "王小明",
        "weekly_utilization": 0.833,
        "daily_utilization": 0.667,
        "status": "OK"
      }
    ]
  }

POST /api/v1/labor/override
  Description: Override a labor violation (requires auth + reason)
  Body: {
    "driver_id": "uuid",
    "route_id": "uuid",
    "reason": "Urgent delivery, customer SLA requirement"
  }
  Response: {
    "violation_id": "uuid",
    "status": "OVERRIDDEN",
    "projected_weekly_minutes": 3060,
    "overage_minutes": 180
  }

GET  /api/v1/labor/violations
  Description: List labor violations with optional filters
  Query params: driver_id, was_overridden (bool), severity, skip, limit
  Response: PaginatedResponse[LaborViolation]

POST /api/v1/admin/labor/reconcile
  Description: Manually trigger nightly reconciliation
  Response: HTTP 202 {"task_id": "uuid", "status": "QUEUED"}
```

---

## 5. Data Migration Strategy

### Migration File: `002_features_v3.sql`

**Execution order matters — respect foreign key dependencies.**

```sql
-- ============================================
-- Phase 1: Foundation (routes.version)
-- ============================================

-- 1a. Add version column with default for existing rows
ALTER TABLE routes ADD COLUMN version INTEGER NOT NULL DEFAULT 1;

-- ============================================
-- Phase 2: Dynamic Insertion
-- ============================================

-- 2a. Create insertion_attempts table
-- (see schema in Section 3 above)

-- ============================================
-- Phase 3: Smart Assignment
-- ============================================

-- 3a. Add route_signature and success_score to routes
ALTER TABLE routes ADD COLUMN route_signature JSONB DEFAULT '[]'::jsonb;
ALTER TABLE routes ADD COLUMN actual_success_score DECIMAL(4,3);

-- 3b. Create route_hex_stats and vehicle_hex_affinities tables
-- (see schema in Section 2 above)

-- 3c. Backfill route_signature for existing COMPLETED routes
--     (run as a one-time Celery task, not in migration)
--     PatternAnalysisService.backfill_signatures() →
--       For each completed route: decompose stops → save signature

-- ============================================
-- Phase 4: Labor Hours
-- ============================================

-- 4a. Add labor columns to drivers
ALTER TABLE drivers ADD COLUMN accumulated_weekly_minutes INTEGER DEFAULT 0;
ALTER TABLE drivers ADD COLUMN accumulated_daily_minutes INTEGER DEFAULT 0;
ALTER TABLE drivers ADD COLUMN weekly_reset_at TIMESTAMPTZ;

-- 4b. Create driver_labor_logs and labor_violations tables
-- (see schema in Section 4 above)

-- 4c. Backfill labor logs from existing completed routes
--     (run as one-time Celery task)
--     For each completed route with actual_departure_at and actual_return_at:
--       Create driver_labor_log entry
--       Then run reconciliation to set accumulated_weekly_minutes
```

### Backfill Tasks (run once after migration)

```python
@celery_app.task(name="app.services.tasks.backfill_route_signatures", queue="default")
def backfill_route_signatures():
    """One-time: compute route_signature for all existing completed routes."""
    with Session(sync_engine) as session:
        routes = session.execute(
            select(Route)
            .where(Route.status == "COMPLETED", Route.route_signature == "[]")
            .options(selectinload(Route.stops))
        ).scalars().all()

        for route in routes:
            signature = geo_provider.decompose_stops(route.stops)
            route.route_signature = signature
        session.commit()

@celery_app.task(name="app.services.tasks.backfill_labor_logs", queue="default")
def backfill_labor_logs():
    """One-time: create labor logs from historical completed routes."""
    with Session(sync_engine) as session:
        routes = session.execute(
            select(Route)
            .where(
                Route.status == "COMPLETED",
                Route.actual_departure_at.isnot(None),
                Route.driver_id.isnot(None),
            )
        ).scalars().all()

        for route in routes:
            duration = (route.actual_return_at - route.actual_departure_at).total_seconds() / 60
            log = DriverLaborLog(
                driver_id=route.driver_id,
                route_id=route.id,
                log_date=route.plan_date,
                shift_start=route.actual_departure_at,
                shift_end=route.actual_return_at,
                drive_time_minutes=int(duration),
                source="RECONCILIATION",
            )
            session.add(log)
        session.commit()
```

---

## 6. H3/Geohash Abstraction Layer

To handle Windows compatibility, wrap geo-hashing behind an interface:

```python
# app/services/geo/provider.py

from abc import ABC, abstractmethod

class GeoProvider(ABC):
    @abstractmethod
    def lat_lng_to_cell(self, lat: float, lng: float, resolution: int) -> str: ...

    @abstractmethod
    def cell_to_parent(self, cell: str, parent_resolution: int) -> str: ...

    @abstractmethod
    def cell_to_lat_lng(self, cell: str) -> tuple[float, float]: ...

class H3Provider(GeoProvider):
    """Primary: uses h3-py for hexagonal cells."""
    def __init__(self):
        import h3
        self._h3 = h3

    def lat_lng_to_cell(self, lat, lng, resolution=7):
        return self._h3.latlng_to_cell(lat, lng, resolution)

    def cell_to_parent(self, cell, parent_resolution):
        return self._h3.cell_to_parent(cell, parent_resolution)

    def cell_to_lat_lng(self, cell):
        return self._h3.cell_to_latlng(cell)

class GeohashProvider(GeoProvider):
    """Fallback: pure-python geohash (no C compilation required)."""
    def __init__(self):
        import geohash2
        self._gh = geohash2

    def lat_lng_to_cell(self, lat, lng, resolution=7):
        # resolution 7 → geohash precision 5 (~4.9km × 4.9km, close to H3 res 6)
        precision = {6: 4, 7: 5, 8: 6}.get(resolution, 5)
        return self._gh.encode(lat, lng, precision=precision)

    def cell_to_parent(self, cell, parent_resolution):
        # Geohash parent = truncate by 1 character
        return cell[:-1]

    def cell_to_lat_lng(self, cell):
        decoded = self._gh.decode(cell)
        return (float(decoded[0]), float(decoded[1]))

def get_geo_provider() -> GeoProvider:
    """Factory: try H3, fallback to geohash."""
    try:
        return H3Provider()
    except ImportError:
        import logging
        logging.warning("h3-py not available, falling back to geohash2")
        return GeohashProvider()

# Singleton instance
geo_provider = get_geo_provider()
```

---

## 7. Risk Assessment & Mitigation

| Risk | Impact | Mitigation Strategy |
| --- | --- | --- |
| **Windows H3 Compatibility** | High | `h3-py` compilation often fails on Windows. **Mitigation:** `GeoProvider` interface with automatic fallback to `geohash2`. See Section 6. |
| **Penalty Weight Imbalance** | High | Solver ignores labor laws if penalty is too low. **Mitigation:** Dynamic formula `MAX(fixed_cost, max_distance) × OverageFactor`. See Section 4. |
| **Data Drift** | Medium | `accumulated_weekly_minutes` getting out of sync. **Mitigation:** Nightly reconciliation Celery task as "Source of Truth". |
| **Optimistic Lock Contention** | Medium | Multiple dispatchers editing same route simultaneously. **Mitigation:** Frontend shows "route modified" toast with one-click refresh. Low contention expected (few dispatchers per route). |
| **Cold Start Accuracy** | Low | New drivers get mediocre recommendations. **Mitigation:** Hierarchical inheritance (parent cell → global average) with confidence indicators so dispatchers know when to trust scores. |

---

## 8. Revised Roadmap (10 Weeks)

*Note: Swapped Dynamic Insertion and Labor Hours to establish Locking Infrastructure first. Each phase includes its own test milestones.*

### Phase 1: Foundation (Weeks 1-2)

* **Infrastructure:** Run migration `002_features_v3.sql` (version column, new tables).
* **DevEnv:** Setup Docker/WSL2 environment for H3 compatibility.
* **GeoProvider:** Implement `H3Provider` + `GeohashProvider` + factory.
* **Test Milestone:**
  - Unit tests for GeoProvider (both implementations)
  - Migration rollback test
  - Verify `version` column default on existing routes

### Phase 2: Dynamic Insertion (Weeks 3-4)

* **Core:** Implement `IncrementalInsertionService` with `version` check.
* **Logic:** Lightweight Temperature Proxy Model with risk scoring.
* **API:** `POST /routes/{id}/insert`, `POST /routes/{id}/insert/preview`.
* **Test Milestone:**
  - Concurrency unit tests (simulate 2 concurrent insertions, verify one gets 409)
  - Temperature proxy accuracy test (compare proxy risk vs full TemperatureTracker)
  - Integration test: insert → verify stop resequencing → verify route version bump

### Phase 3: Smart Assignment (Weeks 5-6)

* **Core:** `PatternAnalysisService` with H3 decomposition & Weighted Average.
* **Logic:** Cold Start inheritance algorithm, confidence scoring.
* **API:** `GET /recommendations/{route_id}`, `POST /recommendations/preview`.
* **Backfill:** Run `backfill_route_signatures` task on existing data.
* **Test Milestone:**
  - Unit tests for affinity formula (known inputs → expected scores)
  - Cold start test (new driver → inherits parent cell scores)
  - Integration test: complete delivery → verify affinity update → verify recommendation ranking changes

### Phase 4: Labor Hours (Weeks 7-8)

* **Core:** `LaborConstraintsService` — new `LaborMinutes` dimension in OR-Tools solver.
* **Tuning:** Implement dynamic penalty formula, calibrate with test scenarios.
* **API:** `GET /labor/compliance/{driver_id}`, `POST /labor/override`.
* **UI:** Compliance Widget & Override flow.
* **Test Milestone:**
  - Solver test: driver at 95% weekly limit → solver assigns fewer stops
  - Solver test: all drivers at limit → solver still produces solution (soft constraint)
  - Penalty scaling test: verify penalty > distance cost but < infeasible_cost
  - Override flow E2E test

### Phase 5: Integration & Polish (Weeks 9-10)

* **Testing:** "Impossible Day" Scenario (all drivers overworked, all routes full, STRICT SLA shipments).
* **Chaos Testing:** Concurrent insertions + optimization running + affinity recalculation.
* **Perf:** Redis caching for affinity scores (cache per vehicle, invalidate on delivery completion).
* **Reconciliation:** Verify nightly Celery Beat job corrects accumulated drift.
* **Test Milestone:**
  - Full E2E: import shipments → optimize → insert ad-hoc → check labor → complete deliveries → verify affinities updated
  - Load test: 50 concurrent insertion attempts on same route
  - Nightly reconciliation accuracy: inject drift → run reconcile → verify correction

---

## 9. Next Steps for Developer

1. **Environment Setup:** Since you are on Windows, I strongly recommend setting up **WSL2 (Ubuntu)** or a **Docker Dev Container** now. This will make installing `h3-py` and running Redis significantly easier.
2. **Schema Migration:** Create the `002_features_v3.sql` migration file. Start with just the `version` column on `routes` — this is the dependency for everything else.
3. **Prototype:** Write a small script to test `h3-py` (or geohash fallback) on your machine to ensure the "Smart Assignment" foundation is viable.
4. **Review API Contracts:** Share the endpoint specs (Sections 2-4) with frontend team so UI work can proceed in parallel.
5. **Config Update:** Add labor compliance settings to `app/core/config.py` early so all services can reference them.
