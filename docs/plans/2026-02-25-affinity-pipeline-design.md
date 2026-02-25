# Production Affinity Pipeline Design

## Summary

Compute vehicle-cell affinity scores when a route is marked COMPLETED, enabling the Smart Assignment system to rank vehicles based on actual delivery performance history.

## Trigger

Inline in `PATCH /routes/{id}/status` when new status is `COMPLETED`. ~100ms overhead.

## New Service

`AffinityUpdateService` in `app/services/recommendation/affinity_update.py`

### Logic per completed route

1. Load route's `route_signature` (H3 cells), `vehicle_id`, and stops
2. Per stop: determine on-time status (actual_arrival vs time window) and temp compliance
3. Compute route success score: `(on_time_count + temp_ok_count) / (2 * total_stops)` (0.0-1.0)
4. Store as `route.actual_success_score`
5. Per H3 cell in signature, upsert `VehicleHexAffinity`:
   - Increment `sample_size`
   - Running weighted average: `new_score = (old * (n-1) + success_score) / n`
   - Update `avg_on_time_rate`, `avg_temp_compliance_rate`
   - Set `last_delivery_at = now`
6. Per H3 cell, upsert `RouteHexStat`:
   - Increment `total_deliveries`
   - Update `avg_service_time_minutes`, `avg_delay_minutes`

### Integration point

In `app/api/v1/endpoints/routes.py` `update_route_status()`, after setting status, call `AffinityUpdateService.process_completed_route()` if status == COMPLETED.

## Tests

- Unit: AffinityUpdateService with mocked session (upsert logic, running average, first delivery, no stops)
- Integration: complete delivery -> query recommendations -> verify scores changed
