# AI-Powered Vehicle-to-Route Matching: How It Works

This document explains the affinity-based smart assignment system (v3.1) — how vehicles build performance profiles over time and how those profiles are used to recommend the best vehicle for a new route.

---

## Overview

The system has three cooperating layers:

1. **Geography** — convert routes into hex cell signatures
2. **Learning** — update vehicle performance scores after each completed route
3. **Scoring** — rank candidate vehicles for a new route using weighted affinities

---

## Layer 1 — Geography: Turning Routes into Hex Cells

Every delivery stop has a GPS coordinate. We convert those coordinates into **H3 hexagon cell IDs** (Uber's spatial indexing library) at resolution 7 (each hex ≈ 5 km²).

```
Stop at (25.033, 121.565)  →  H3 cell "872a100c7ffffff"
Stop at (25.041, 121.571)  →  H3 cell "872a100c7ffffff"  (same hex, deduplicated)
Stop at (25.021, 121.501)  →  H3 cell "872a1072fffffff"
```

A route becomes a **route signature** — an ordered list of unique hex cells it passes through. This is stored on the `Route` model (`route.route_signature`).

**Key files:**
- `app/services/recommendation/pattern_analysis.py` — `decompose_route_to_cells()`, `decompose_coordinates_to_cells()`
- `app/services/geo/provider.py` — `H3Provider.lat_lng_to_cell()`

---

## Layer 2 — Learning: Updating Affinities After Each Completed Route

When a driver marks a route complete, `AffinityUpdateService.process_completed_route()` runs automatically (triggered from the route completion API endpoint).

### Step 1: Score the Delivery

For each stop, check if it was on-time AND temperature-compliant:

```
success_score = (on_time_count + temp_ok_count) / (2 × total_stops)
```

- A perfect route (all on-time, all in-temp) scores **1.0**
- A route where everything was late and warm scores **0.0**

Two sub-metrics are also tracked separately:
- `on_time_rate` — fraction of stops that arrived before `expected_departure_at`
- `temp_compliance_rate` — fraction of stops where `is_temp_feasible = True`

### Step 2: Update the Database

For each hex cell in the route signature, two tables are upserted:

#### `VehicleHexAffinity` — "how well does vehicle V perform in hex cell C?"

Uses an **incremental running average** so old data is never thrown away:

```
new_avg = (old_avg × old_n + new_score) / (old_n + 1)
```

Stores: `affinity_score`, `sample_size`, `avg_on_time_rate`, `avg_temp_compliance_rate`, `last_delivery_at`

#### `RouteHexStat` — "how busy is this hex cell overall?"

Tracks `total_deliveries` ever recorded in that cell. Used as a weight in scoring (busier cells matter more).

Over many completed routes, each vehicle builds a geographic performance profile.

**Key files:**
- `app/services/recommendation/affinity_update.py` — `AffinityUpdateService`
- `app/models/geo.py` — `VehicleHexAffinity`, `RouteHexStat` ORM models
- `app/api/v1/endpoints/routes.py` — route completion endpoint triggers the pipeline

---

## Layer 3 — Scoring: Ranking Vehicles for a New Route

When you ask "which vehicle should handle this route?", `PatternAnalysisService.calculate_vehicle_affinity()` runs for every candidate vehicle.

### Step 1: Decompose the New Route

Convert the new route's stops (or preview coordinates) into hex cells — same process as Layer 1.

### Step 2: Look Up Affinity Per Cell (with Cold-Start Fallback)

For each hex cell, the fallback chain is:

```
Has ≥10 samples for this exact cell?
    → use affinity directly (HIGH confidence)

Has <10 samples for this cell?
    → blend with parent cell (resolution 6, larger area):
      blended = (n/10) × direct_affinity + (1 - n/10) × parent_affinity

No data for cell or parent cell?
    → use vehicle's global average across all cells

No data at all for this vehicle?
    → default to 0.5 (neutral)
```

The threshold of 10 samples is defined as `COLD_START_THRESHOLD = 10`.

### Step 3: Weight by Cell Traffic

Cells where more deliveries happen historically count more in the final score:

```
final_score = Σ (cell_weight × affinity_score) / Σ cell_weight

where cell_weight = RouteHexStat.total_deliveries (default 1 if no data)
```

### Step 4: Report Confidence

Based on what % of route cells had ≥10 samples:

| Confidence | Condition |
|---|---|
| HIGH | ≥ 70% of cells have ≥10 samples |
| MEDIUM | 30–70% of cells have ≥10 samples |
| LOW | < 30% of cells have ≥10 samples |

The vehicle with the **highest weighted affinity score** gets recommended first.

**Key files:**
- `app/services/recommendation/pattern_analysis.py` — `PatternAnalysisService`
- `app/api/v1/endpoints/recommendations.py` — `/recommendations/preview` and `/recommendations/{route_id}` endpoints

---

## Design Decisions

| Choice | Reason |
|---|---|
| H3 hexagons instead of exact coordinates | Groups nearby stops into the same cell — a vehicle that performed well in an area generalises to nearby addresses |
| Running average (not full history) | O(1) storage per cell; no need to replay history — each new route smoothly updates the score |
| Cold-start blending with parent cell | Prevents routes to unfamiliar areas from defaulting to a useless 0.5 score — borrows signal from wider-area data |
| Weighted by cell traffic | Busy delivery zones should influence the final score more than a cell visited once |
| Confidence levels | Lets the UI warn the user when the recommendation is based on thin data |

---

## Data Flow Diagram

```
Route completed
      │
      ▼
AffinityUpdateService.process_completed_route()
      │
      ├─ _compute_success_score()     → 0.0–1.0 per route
      ├─ _compute_on_time_rate()
      ├─ _compute_temp_compliance_rate()
      │
      └─ for each H3 cell in route_signature:
            ├─ _upsert_vehicle_affinity()   → VehicleHexAffinity (running avg)
            └─ _upsert_route_hex_stat()     → RouteHexStat (total_deliveries++)


New route requested
      │
      ▼
PatternAnalysisService.calculate_vehicle_affinity()
      │
      ├─ decompose_route_to_cells()   → [hex_cell_1, hex_cell_2, ...]
      │
      └─ for each candidate vehicle:
            for each cell:
              ├─ _get_cell_affinity_with_fallback()   (cold-start chain)
              └─ _get_cell_weight()                   (from RouteHexStat)
            → weighted_score = Σ(weight × affinity) / Σ(weight)
            → confidence = HIGH / MEDIUM / LOW

      ▼
Ranked vehicle list returned to frontend
```

---

## Related Tests

| File | What It Tests |
|---|---|
| `tests/unit/test_affinity_pipeline.py` | `AffinityUpdateService` unit tests (running average, score computation) |
| `tests/unit/test_affinity_integration.py` | End-to-end: delivery outcome → score change |
| `tests/api/test_affinity_trigger.py` | Route completion API triggers the pipeline |
| `tests/unit/test_smart_assignment.py` | `PatternAnalysisService` affinity + cold-start + confidence |
| `tests/api/test_recommendation_api.py` | Recommendation endpoints |
