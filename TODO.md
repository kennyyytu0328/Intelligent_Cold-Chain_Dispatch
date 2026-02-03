# ICCDDS TODO List

## Current Issue

### MapPage.tsx Shows Nothing
- **Status**: Not Started
- **Priority**: High
- **Description**: After optimization completes successfully, navigating to the Map page shows nothing/blank.

#### Investigation Needed:
1. Check if MapPage.tsx is receiving route data from the store
2. Verify the map component is properly initialized (Leaflet/MapLibre)
3. Check if route data structure matches what MapPage expects
4. Verify API endpoints for fetching route details with stops/coordinates

#### Possible Causes:
- Route data not being passed to map component
- Map tiles not loading (API key or network issue)
- Route coordinates not being fetched from backend
- Store state not persisting when navigating to map page

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
