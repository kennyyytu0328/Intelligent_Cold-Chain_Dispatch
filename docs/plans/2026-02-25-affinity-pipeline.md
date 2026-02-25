# Affinity Pipeline Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Automatically compute vehicle-cell affinity scores when routes are marked COMPLETED, enabling Smart Assignment to rank vehicles based on real delivery history.

**Architecture:** New `AffinityUpdateService` in `app/services/recommendation/affinity_update.py` computes per-cell success metrics from completed route stops, then upserts `VehicleHexAffinity` and `RouteHexStat` rows. Triggered inline from `PATCH /routes/{id}/status` when status transitions to COMPLETED.

**Tech Stack:** Python, SQLAlchemy async, existing `VehicleHexAffinity`/`RouteHexStat` ORM models, H3 geo provider.

---

### Task 1: Write AffinityUpdateService unit tests

**Files:**
- Create: `tests/unit/test_affinity_pipeline.py`

**Step 1: Write the failing tests**

```python
"""Unit tests for AffinityUpdateService."""
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.recommendation.affinity_update import AffinityUpdateService


VEHICLE_ID = uuid4()
ROUTE_ID = uuid4()
SHIPMENT_ID = uuid4()


def _make_stop(
    seq: int,
    *,
    on_time: bool = True,
    temp_ok: bool = True,
    arrival_temp: float = -2.0,
    lat: float = 25.033,
    lng: float = 121.565,
):
    """Create a mock RouteStop."""
    stop = MagicMock()
    stop.sequence_number = seq
    stop.shipment_id = SHIPMENT_ID
    stop.is_temp_feasible = temp_ok
    stop.predicted_arrival_temp = Decimal(str(arrival_temp))
    stop.actual_arrival_at = datetime(2026, 1, 15, 9, 0, tzinfo=timezone.utc) if on_time else None
    stop.expected_arrival_at = datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)
    stop.expected_departure_at = datetime(2026, 1, 15, 10, 15, tzinfo=timezone.utc)
    stop.delivery_status = MagicMock(value="COMPLETED") if on_time else MagicMock(value="FAILED")
    stop.actual_temperature = Decimal(str(arrival_temp))

    # Shipment with time window and temp limit
    stop.shipment = MagicMock()
    stop.shipment.temp_limit_upper = Decimal("5.0")

    return stop


def _make_route(stops, signature=None):
    route = MagicMock()
    route.id = ROUTE_ID
    route.vehicle_id = VEHICLE_ID
    route.route_signature = signature or ["87283472bffffff", "87283472affffff"]
    route.stops = stops
    route.total_stops = len(stops)
    route.actual_success_score = None
    return route


class TestComputeSuccessScore:
    """Test success score calculation from stop outcomes."""

    def test_all_stops_perfect(self):
        svc = AffinityUpdateService.__new__(AffinityUpdateService)
        stops = [_make_stop(1), _make_stop(2)]
        score = svc._compute_success_score(stops)
        assert score == Decimal("1.000")

    def test_all_stops_failed(self):
        svc = AffinityUpdateService.__new__(AffinityUpdateService)
        stops = [
            _make_stop(1, on_time=False, temp_ok=False),
            _make_stop(2, on_time=False, temp_ok=False),
        ]
        score = svc._compute_success_score(stops)
        assert score == Decimal("0.000")

    def test_mixed_results(self):
        svc = AffinityUpdateService.__new__(AffinityUpdateService)
        stops = [
            _make_stop(1, on_time=True, temp_ok=True),   # 2/2
            _make_stop(2, on_time=False, temp_ok=True),   # 1/2
        ]
        # (2 + 1) / (2 * 2) = 0.750
        score = svc._compute_success_score(stops)
        assert score == Decimal("0.750")

    def test_empty_stops_returns_zero(self):
        svc = AffinityUpdateService.__new__(AffinityUpdateService)
        score = svc._compute_success_score([])
        assert score == Decimal("0.000")


class TestRunningAverage:
    """Test the running weighted average formula for affinity updates."""

    def test_first_delivery(self):
        """First delivery: new_score = success_score (no prior data)."""
        svc = AffinityUpdateService.__new__(AffinityUpdateService)
        result = svc._running_average(
            old_score=Decimal("0.500"),
            old_sample_size=0,
            new_value=Decimal("0.800"),
        )
        assert result == Decimal("0.800")

    def test_second_delivery(self):
        """Second delivery: average of old and new."""
        svc = AffinityUpdateService.__new__(AffinityUpdateService)
        result = svc._running_average(
            old_score=Decimal("0.800"),
            old_sample_size=1,
            new_value=Decimal("0.600"),
        )
        # (0.800 * 1 + 0.600) / 2 = 0.700
        assert result == Decimal("0.700")

    def test_large_sample(self):
        """Large sample: new value has small effect."""
        svc = AffinityUpdateService.__new__(AffinityUpdateService)
        result = svc._running_average(
            old_score=Decimal("0.900"),
            old_sample_size=99,
            new_value=Decimal("0.000"),
        )
        # (0.900 * 99 + 0.000) / 100 = 0.891
        assert result == Decimal("0.891")


class TestProcessCompletedRoute:
    """Integration-level tests for the full pipeline with mocked DB."""

    @pytest.mark.asyncio
    async def test_updates_success_score_on_route(self):
        """Route.actual_success_score should be set."""
        session = AsyncMock()
        svc = AffinityUpdateService(session)

        route = _make_route([_make_stop(1), _make_stop(2)])

        # Mock DB queries to return no existing affinity/stat rows
        session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))

        await svc.process_completed_route(route)

        assert route.actual_success_score == Decimal("1.000")

    @pytest.mark.asyncio
    async def test_skips_route_without_signature(self):
        """Route with no signature should be skipped gracefully."""
        session = AsyncMock()
        svc = AffinityUpdateService(session)

        route = _make_route([_make_stop(1)], signature=[])

        await svc.process_completed_route(route)

        # Should set success score but not upsert affinities
        assert route.actual_success_score == Decimal("1.000")
        session.merge.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_route_without_stops(self):
        """Route with no stops should be skipped."""
        session = AsyncMock()
        svc = AffinityUpdateService(session)

        route = _make_route([], signature=["cell_a"])

        await svc.process_completed_route(route)

        assert route.actual_success_score == Decimal("0.000")
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_affinity_pipeline.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.recommendation.affinity_update'`

**Step 3: Commit test file**

```bash
git add tests/unit/test_affinity_pipeline.py
git commit -m "test: add AffinityUpdateService unit tests (RED)"
```

---

### Task 2: Implement AffinityUpdateService

**Files:**
- Create: `app/services/recommendation/affinity_update.py`

**Step 1: Write the implementation**

```python
"""
Affinity Update Service for production affinity pipeline (v3.1).

Computes vehicle-cell affinity scores when a route is marked COMPLETED.
Updates VehicleHexAffinity and RouteHexStat tables with delivery outcomes.
"""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.geo import RouteHexStat, VehicleHexAffinity


class AffinityUpdateService:
    """Processes completed routes to update affinity scores."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def process_completed_route(self, route) -> None:
        """Main entry point: compute and persist affinity updates.

        Args:
            route: Route ORM object with stops eagerly loaded.
        """
        stops = route.stops or []
        success_score = self._compute_success_score(stops)
        route.actual_success_score = success_score

        cells = route.route_signature or []
        if not cells or not stops:
            return

        on_time_rate = self._compute_on_time_rate(stops)
        temp_compliance = self._compute_temp_compliance_rate(stops)

        for cell in cells:
            await self._upsert_vehicle_affinity(
                vehicle_id=route.vehicle_id,
                h3_index=cell,
                success_score=success_score,
                on_time_rate=on_time_rate,
                temp_compliance=temp_compliance,
            )
            await self._upsert_route_hex_stat(
                h3_index=cell,
                stops=stops,
            )

    def _compute_success_score(self, stops: list) -> Decimal:
        """Compute route success: (on_time + temp_ok) / (2 * total).

        Returns 0.000-1.000.
        """
        if not stops:
            return Decimal("0.000")

        on_time = sum(1 for s in stops if self._is_on_time(s))
        temp_ok = sum(1 for s in stops if s.is_temp_feasible)
        total = len(stops)

        score = Decimal(str(on_time + temp_ok)) / Decimal(str(2 * total))
        return round(score, 3)

    def _compute_on_time_rate(self, stops: list) -> Decimal:
        if not stops:
            return Decimal("0.000")
        on_time = sum(1 for s in stops if self._is_on_time(s))
        return round(Decimal(str(on_time)) / Decimal(str(len(stops))), 3)

    def _compute_temp_compliance_rate(self, stops: list) -> Decimal:
        if not stops:
            return Decimal("0.000")
        ok = sum(1 for s in stops if s.is_temp_feasible)
        return round(Decimal(str(ok)) / Decimal(str(len(stops))), 3)

    @staticmethod
    def _is_on_time(stop) -> bool:
        """Check if stop was delivered on time."""
        if stop.actual_arrival_at is None:
            return False
        return stop.actual_arrival_at <= stop.expected_departure_at

    @staticmethod
    def _running_average(
        old_score: Decimal,
        old_sample_size: int,
        new_value: Decimal,
    ) -> Decimal:
        """Compute incremental running average.

        new = (old * n + new_value) / (n + 1)
        For n=0 (first delivery), returns new_value directly.
        """
        n = old_sample_size
        if n == 0:
            return round(new_value, 3)
        result = (old_score * Decimal(str(n)) + new_value) / Decimal(str(n + 1))
        return round(result, 3)

    async def _upsert_vehicle_affinity(
        self,
        vehicle_id: UUID,
        h3_index: str,
        success_score: Decimal,
        on_time_rate: Decimal,
        temp_compliance: Decimal,
    ) -> None:
        """Upsert VehicleHexAffinity row with running averages."""
        result = await self._session.execute(
            select(VehicleHexAffinity).where(
                VehicleHexAffinity.vehicle_id == vehicle_id,
                VehicleHexAffinity.h3_index == h3_index,
            )
        )
        existing = result.scalar_one_or_none()

        now = datetime.now(timezone.utc)

        if existing:
            n = existing.sample_size
            existing.affinity_score = self._running_average(
                existing.affinity_score, n, success_score
            )
            existing.avg_on_time_rate = self._running_average(
                existing.avg_on_time_rate or Decimal("0.500"), n, on_time_rate
            )
            existing.avg_temp_compliance_rate = self._running_average(
                existing.avg_temp_compliance_rate or Decimal("0.500"), n, temp_compliance
            )
            existing.sample_size = n + 1
            existing.last_delivery_at = now
            existing.updated_at = now
        else:
            new_row = VehicleHexAffinity(
                vehicle_id=vehicle_id,
                h3_index=h3_index,
                affinity_score=success_score,
                sample_size=1,
                avg_on_time_rate=on_time_rate,
                avg_temp_compliance_rate=temp_compliance,
                last_delivery_at=now,
                updated_at=now,
            )
            self._session.add(new_row)

    async def _upsert_route_hex_stat(
        self,
        h3_index: str,
        stops: list,
    ) -> None:
        """Upsert RouteHexStat row with delivery count and averages."""
        result = await self._session.execute(
            select(RouteHexStat).where(RouteHexStat.h3_index == h3_index)
        )
        existing = result.scalar_one_or_none()

        now = datetime.now(timezone.utc)
        delivery_count = len(stops)

        if existing:
            existing.total_deliveries = existing.total_deliveries + delivery_count
            existing.updated_at = now
        else:
            new_row = RouteHexStat(
                h3_index=h3_index,
                total_deliveries=delivery_count,
                updated_at=now,
            )
            self._session.add(new_row)
```

**Step 2: Run tests to verify they pass**

Run: `pytest tests/unit/test_affinity_pipeline.py -v`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add app/services/recommendation/affinity_update.py
git commit -m "feat: add AffinityUpdateService with running average affinity computation"
```

---

### Task 3: Hook into route completion endpoint

**Files:**
- Modify: `app/api/v1/endpoints/routes.py:304-322`

**Step 1: Write failing API test**

Add to `tests/api/test_recommendation_api.py` (or create `tests/api/test_affinity_trigger.py`):

```python
"""Test that route completion triggers affinity updates."""
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4
from decimal import Decimal

import pytest


ROUTE_ID = uuid4()


class TestAffinityTriggerOnCompletion:
    """PATCH /routes/{id}/status with COMPLETED triggers affinity pipeline."""

    @pytest.mark.asyncio
    async def test_completion_calls_affinity_service(self, client):
        """Setting status=COMPLETED should invoke AffinityUpdateService."""
        mock_route = MagicMock()
        mock_route.id = ROUTE_ID
        mock_route.vehicle_id = uuid4()
        mock_route.route_signature = ["cell_a"]
        mock_route.stops = []
        mock_route.total_stops = 0
        mock_route.actual_success_score = None
        mock_route.status = MagicMock(value="COMPLETED")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_route)

        with patch("app.api.v1.endpoints.routes.get_async_session") as mock_sess_dep:
            mock_session = AsyncMock()
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_session.flush = AsyncMock()
            mock_sess_dep.return_value = mock_session

            with patch(
                "app.api.v1.endpoints.routes.AffinityUpdateService"
            ) as MockSvc:
                mock_svc_instance = AsyncMock()
                MockSvc.return_value = mock_svc_instance

                resp = await client.patch(
                    f"/api/v1/routes/{ROUTE_ID}/status",
                    params={"status": "COMPLETED"},
                )

                assert resp.status_code == 200
                MockSvc.assert_called_once_with(mock_session)
                mock_svc_instance.process_completed_route.assert_awaited_once_with(mock_route)

    @pytest.mark.asyncio
    async def test_non_completion_skips_affinity(self, client):
        """Setting status to IN_PROGRESS should NOT trigger affinity."""
        mock_route = MagicMock()
        mock_route.id = ROUTE_ID
        mock_route.status = MagicMock(value="IN_PROGRESS")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_route)

        with patch("app.api.v1.endpoints.routes.get_async_session") as mock_sess_dep:
            mock_session = AsyncMock()
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_session.flush = AsyncMock()
            mock_sess_dep.return_value = mock_session

            with patch(
                "app.api.v1.endpoints.routes.AffinityUpdateService"
            ) as MockSvc:
                resp = await client.patch(
                    f"/api/v1/routes/{ROUTE_ID}/status",
                    params={"status": "IN_PROGRESS"},
                )

                assert resp.status_code == 200
                MockSvc.assert_not_called()
```

**Step 2: Modify the route status endpoint**

In `app/api/v1/endpoints/routes.py`, update `update_route_status()`:

```python
# Add import at top of file:
from app.services.recommendation.affinity_update import AffinityUpdateService

# Replace the update_route_status function (lines 304-322):
@router.patch("/{route_id}/status")
async def update_route_status(
    route_id: UUID,
    status: RouteStatus,
    session: AsyncSession = Depends(get_async_session),
):
    """Update route status. Triggers affinity pipeline on COMPLETED."""
    result = await session.execute(
        select(Route).where(Route.id == route_id)
    )
    route = result.scalar_one_or_none()

    if not route:
        raise HTTPException(status_code=404, detail="Route not found")

    route.status = status

    if status == RouteStatus.COMPLETED:
        svc = AffinityUpdateService(session)
        await svc.process_completed_route(route)

    await session.flush()

    return {"id": str(route.id), "status": route.status.value}
```

**Step 3: Run all tests**

Run: `pytest tests/ -v -k "affinity or recommendation"`
Expected: All PASS

**Step 4: Commit**

```bash
git add app/api/v1/endpoints/routes.py tests/api/test_affinity_trigger.py
git commit -m "feat: trigger affinity pipeline on route completion"
```

---

### Task 4: Integration test (delivery -> affinity -> ranking)

**Files:**
- Create: `tests/unit/test_affinity_integration.py`

**Step 1: Write integration test**

```python
"""Integration test: delivery completion changes recommendation rankings."""
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.recommendation.affinity_update import AffinityUpdateService
from app.services.recommendation.pattern_analysis import PatternAnalysisService


VEHICLE_A = uuid4()
VEHICLE_B = uuid4()
ROUTE_ID = uuid4()
CELL = "87283472bffffff"


def _make_stop(on_time=True, temp_ok=True):
    stop = MagicMock()
    stop.is_temp_feasible = temp_ok
    stop.actual_arrival_at = datetime(2026, 1, 15, 9, 0, tzinfo=timezone.utc)
    stop.expected_departure_at = datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)
    stop.delivery_status = MagicMock(value="COMPLETED")
    stop.actual_temperature = Decimal("-2.0")
    stop.shipment = MagicMock()
    stop.shipment.temp_limit_upper = Decimal("5.0")
    return stop


class TestAffinityPipelineIntegration:
    """End-to-end: complete route -> affinities updated -> rankings change."""

    @pytest.mark.asyncio
    async def test_good_delivery_raises_affinity(self):
        """A perfect delivery should increase affinity from default 0.500."""
        session = AsyncMock()

        # No existing affinity row
        no_result = MagicMock()
        no_result.scalar_one_or_none = MagicMock(return_value=None)
        session.execute = AsyncMock(return_value=no_result)

        route = MagicMock()
        route.id = ROUTE_ID
        route.vehicle_id = VEHICLE_A
        route.route_signature = [CELL]
        route.stops = [_make_stop(), _make_stop()]
        route.total_stops = 2
        route.actual_success_score = None

        svc = AffinityUpdateService(session)
        await svc.process_completed_route(route)

        # Success score should be 1.0 (perfect delivery)
        assert route.actual_success_score == Decimal("1.000")

        # Should have called session.add for new VehicleHexAffinity
        add_calls = session.add.call_args_list
        assert len(add_calls) >= 1

        # Check the affinity row that was added
        affinity_row = add_calls[0][0][0]
        assert affinity_row.affinity_score == Decimal("1.000")
        assert affinity_row.sample_size == 1

    @pytest.mark.asyncio
    async def test_bad_delivery_lowers_existing_affinity(self):
        """A failed delivery should lower an existing high affinity."""
        session = AsyncMock()

        # Existing affinity row with high score
        existing = MagicMock()
        existing.affinity_score = Decimal("0.900")
        existing.sample_size = 9
        existing.avg_on_time_rate = Decimal("0.900")
        existing.avg_temp_compliance_rate = Decimal("0.900")

        existing_result = MagicMock()
        existing_result.scalar_one_or_none = MagicMock(return_value=existing)

        # For RouteHexStat query, return None (new cell)
        no_result = MagicMock()
        no_result.scalar_one_or_none = MagicMock(return_value=None)

        call_count = 0
        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            # First call: VehicleHexAffinity lookup, second: RouteHexStat
            if call_count == 1:
                return existing_result
            return no_result

        session.execute = mock_execute

        route = MagicMock()
        route.id = ROUTE_ID
        route.vehicle_id = VEHICLE_A
        route.route_signature = [CELL]
        route.stops = [_make_stop(on_time=False, temp_ok=False)]
        route.total_stops = 1
        route.actual_success_score = None

        svc = AffinityUpdateService(session)
        await svc.process_completed_route(route)

        # Success score: 0 on_time + 0 temp_ok / (2 * 1) = 0.000
        assert route.actual_success_score == Decimal("0.000")

        # Affinity should decrease: (0.900 * 9 + 0.000) / 10 = 0.810
        assert existing.affinity_score == Decimal("0.810")
        assert existing.sample_size == 10
```

**Step 2: Run all tests**

Run: `pytest tests/unit/test_affinity_integration.py tests/unit/test_affinity_pipeline.py -v`
Expected: All PASS

**Step 3: Commit**

```bash
git add tests/unit/test_affinity_integration.py
git commit -m "test: add affinity pipeline integration tests (delivery -> score change)"
```

---

### Task 5: Update TODO.md and run full test suite

**Files:**
- Modify: `TODO.md`

**Step 1: Run full test suite**

Run: `pytest tests/ -v --tb=short`
Expected: All existing + new tests PASS

**Step 2: Update TODO.md**

Mark remaining Step 4 items as complete:
- [x] Production affinity pipeline
- [x] Integration test: complete delivery -> affinity update -> ranking changes

**Step 3: Commit**

```bash
git add TODO.md
git commit -m "docs: mark Step 4 affinity pipeline as complete"
```
