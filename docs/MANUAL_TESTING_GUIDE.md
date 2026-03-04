# ICCDDS Manual Testing Guide

How to manually verify that v3.1 features are working end-to-end. Covers Steps 1–5.

**Default credentials:** `admin` / `admin123`
**API base:** `http://localhost:8000/api/v1`
**Swagger UI:** `http://localhost:8000/api/v1/docs`
**Frontend:** `http://localhost:3000`

---

## Prerequisites — Start All Services

```bash
# 1. Database + Redis
docker-compose -f docker-compose.dev.yml up -d

# 2. API (Terminal 1)
uvicorn app.main:app --reload --port 8000

# 3. Celery worker (Terminal 2, Windows)
celery -A app.core.celery_app worker --loglevel=info -Q optimization,default --pool=solo

# 4. Frontend (Terminal 3)
cd frontend && npm run dev
```

Health check: `curl http://localhost:8000/health` should return `{"status": "healthy"}`.

---

## Step 1 — Get a Token

All API calls require a Bearer token.

```bash
curl -X POST http://localhost:8000/api/v1/auth/token \
  -d "username=admin&password=admin123"
```

Response:
```json
{ "access_token": "eyJ...", "token_type": "bearer" }
```

Save the token:
```bash
TOKEN="eyJ..."
```

> In Swagger UI: click **Authorize** → enter `admin` / `admin123`.

---

## Step 2 — Import Data (if starting fresh)

### Option A: Excel import

```bash
python generate_excel_template.py          # creates template
# Fill in vehicles, depots, shipments in the Excel file
curl -X POST http://localhost:8000/api/v1/import/excel \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@ICCDDS_Import_Template.xlsx"
```

### Option B: Swagger UI

Use `POST /import/excel` in Swagger to upload the file.

### Verify data loaded

```bash
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/vehicles
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/shipments
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/depots
```

---

## Step 3 — Run Optimization (Core Flow)

### Trigger an optimization job

```bash
curl -X POST http://localhost:8000/api/v1/optimization \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "plan_date": "2024-02-01",
    "vehicle_ids": [],
    "shipment_ids": [],
    "time_limit_seconds": 30
  }'
```

Returns HTTP 202 with a `job_id`:
```json
{ "job_id": "abc-123...", "status": "PENDING" }
```

### Poll for completion

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/optimization/abc-123...
```

Wait until `"status": "COMPLETED"`. The response includes `routes` with assigned vehicles and stops.

### Verify routes were created

```bash
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/routes
```

Each route should have a `route_signature` field (list of H3 hex cell IDs). If it's empty, run the backfill script:

```bash
python scripts/backfill_route_signatures.py
```

### Verify on the frontend

1. Go to `http://localhost:3000/optimization`
2. Set date and click **Run Optimization**
3. Watch the progress bar fill to 100%
4. Navigate to the **Map** tab — routes should appear as coloured polylines

---

## Step 4 — Dynamic Insertion (Step 3 Feature)

Insert a new stop into an active route without re-running the full solver.

### Preview insertion (non-destructive)

```bash
ROUTE_ID="<route_id_from_step_3>"

curl -X POST "http://localhost:8000/api/v1/routes/$ROUTE_ID/insert/preview" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "shipment_id": "<shipment_id>",
    "requested_time": "2024-02-01T10:00:00Z"
  }'
```

Response shows:
- `feasible`: true/false
- `best_position`: stop index where insertion is cheapest
- `temperature_risk`: GREEN / YELLOW / RED
- `time_delta_seconds`: added travel time

### Confirm the insertion

```bash
curl -X POST "http://localhost:8000/api/v1/routes/$ROUTE_ID/insert" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "shipment_id": "<shipment_id>",
    "requested_time": "2024-02-01T10:00:00Z"
  }'
```

The route `version` field should increment by 1, and the new stop appears in the stop list.

### View insertion audit log

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/routes/$ROUTE_ID/insertion-history
```

### Test optimistic locking (concurrent conflict)

Send two simultaneous insert requests to the same route. The second one should return HTTP 409 with a version mismatch error.

---

## Step 5 — Smart Assignment / Recommendations (Step 4 Feature)

### Option A: Recommend by existing route

```bash
ROUTE_ID="<any_route_id>"

curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/recommendations/$ROUTE_ID
```

Response: ranked list of vehicles with `affinity_score`, `confidence`, `cold_start` flag.

### Option B: Preview by coordinates

```bash
curl -X POST http://localhost:8000/api/v1/recommendations/preview \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "coordinates": [
      {"lat": 25.033, "lng": 121.565},
      {"lat": 25.041, "lng": 121.571},
      {"lat": 25.021, "lng": 121.501}
    ]
  }'
```

### Option C: Frontend UI

1. Go to `http://localhost:3000/recommendations`
2. **Recommend tab**: enter a Route ID → click Recommend
3. **Preview tab**: type addresses → click **Geocode** per row → click Preview Rankings

### Accept a recommendation

```bash
curl -X POST "http://localhost:8000/api/v1/recommendations/$ROUTE_ID/accept" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{ "vehicle_id": "<vehicle_id>" }'
```

---

## Step 6 — Affinity Pipeline (Step 4 Feature)

The pipeline learns from completed routes and updates vehicle-hex affinity scores automatically.

### Automated test script (quickest)

```bash
python scripts/test_affinity_pipeline.py
```

This script:
1. Logs in
2. Finds a non-completed route
3. Patches stops with arrival times
4. Marks route COMPLETED (triggers the pipeline)
5. Queries the database and prints `VehicleHexAffinity` + `RouteHexStat` rows

Expected output:
```
[OK] Logged in as admin
[OK] Found N route(s) with status=SCHEDULED
[OK] Route RT-001 (abc12345...)
[OK] Route abc12345... -> status=COMPLETED

  Route.actual_success_score = 0.875

  VehicleHexAffinity rows for vehicle def67890...:
  H3 Cell               Score    N  OnTime  TempOK
  --------------------------------------------------
  872a100c7ffffff       0.875    1   0.900   0.850

  RouteHexStat rows (most recent):
  872a100c7ffffff      deliveries=1
```

### Manual via API

```bash
# Mark a route as COMPLETED
curl -X PATCH "http://localhost:8000/api/v1/routes/$ROUTE_ID/status?status=COMPLETED" \
  -H "Authorization: Bearer $TOKEN"
```

Then check the database directly:

```sql
-- Connect to: psql -h localhost -p 5433 -U iccdds -d iccdds

-- Affinity scores for a vehicle
SELECT h3_index, affinity_score, sample_size, avg_on_time_rate
FROM vehicle_hex_affinities
WHERE vehicle_id = '<vehicle_uuid>'
ORDER BY updated_at DESC;

-- Route performance stats per hex cell
SELECT h3_index, total_deliveries, avg_success_score
FROM route_hex_stats
ORDER BY updated_at DESC
LIMIT 20;

-- Success score written back to the route
SELECT route_code, actual_success_score, status
FROM routes
WHERE id = '<route_uuid>';
```

### Seed demo affinity data (if no completed routes yet)

```bash
python scripts/seed_affinity_data.py --dry-run   # preview
python scripts/seed_affinity_data.py              # write to DB
```

After seeding, the recommendation API will return meaningful affinity scores immediately.

---

## Step 7 — Labor Hours Compliance (Step 5 Feature)

The feature is gated by the `ENABLE_LABOR_DIMENSION` flag (default: `False`). Enable it first.

### Enable the flag

Add to your `.env` (or export before starting the API):

```bash
ENABLE_LABOR_DIMENSION=true
```

Restart the API after changing the flag.

### Check all-driver compliance summary

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/labor/compliance/summary
```

When enabled and drivers exist, each item in `data` shows:

```json
{
  "driver_id": "...",
  "driver_name": "Alice",
  "employee_id": "EMP001",
  "weekly_minutes": 1800,
  "weekly_limit": 2880,
  "weekly_utilization": 0.625,
  "daily_minutes": 360,
  "daily_limit": 720,
  "daily_utilization": 0.5,
  "status": "OK"
}
```

`status` values: `OK` | `WARNING` (≥ 85% of limit) | `VIOLATION` (≥ 100%).

When disabled: `{ "enabled": false, "data": null }`.

### Check a single driver

```bash
DRIVER_ID="<driver_uuid>"

curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/labor/compliance/$DRIVER_ID
```

Returns the same structure as a single `data` element above, or HTTP 404 if the driver doesn't exist.

### Override a labor violation

When a driver is at `VIOLATION` status but dispatch must proceed, record an authorised override with a reason:

```bash
curl -X POST http://localhost:8000/api/v1/labor/override \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "driver_id": "<driver_uuid>",
    "route_id":  "<route_uuid>",
    "reason":    "Emergency delivery required by client contract"
  }'
```

Success response:

```json
{
  "enabled": true,
  "violation_id": "<uuid>",
  "message": "Override recorded successfully"
}
```

The override is stored in the `LaborViolation` table as an audit trail (approved by the authenticated user).

### Verify in Swagger UI

Open `http://localhost:8000/api/v1/docs`, authorize, then use:
- `GET /labor/compliance/summary`
- `GET /labor/compliance/{driver_id}`
- `POST /labor/override`

### Nightly reconciliation (Celery task)

The `reconcile_labor_hours` task runs nightly to sync accumulated minutes. Trigger it manually to verify:

```python
# In a Python shell with the app environment active
from app.services.tasks import reconcile_labor_hours
result = reconcile_labor_hours.delay()
print(result.get(timeout=30))
```

Or via Flower UI at `http://localhost:5555` → Tasks → `reconcile_labor_hours`.

---

## Step 8 — Temperature Analysis

For any completed or active route, inspect per-stop temperature predictions:

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/routes/$ROUTE_ID/temperature-analysis
```

Response: predicted temperature at each stop, including transit drift, door-open impact, and cooling recovery. Flags stops exceeding the maximum allowed temperature.

---

## Common Troubleshooting

| Symptom | Fix |
|---------|-----|
| `401 Unauthorized` | Token expired — re-login with `/auth/token` |
| `404` on route/vehicle | Wrong ID or data not imported yet |
| Optimization stays PENDING | Celery worker not running — start it in a separate terminal |
| `route_signature` is empty | Run `python scripts/backfill_route_signatures.py` |
| No affinity rows after COMPLETED | Route has no `route_signature` — backfill first |
| `409 Conflict` on insert | Version mismatch (optimistic locking) — re-fetch route and retry |
| DB connect fails in test script | Wrong port — dev compose uses **5433**, not 5432 |
| Frontend shows no routes on Map | Navigate to Optimization page first, or check the plan date |
