"""
Tests for v3.1 ORM model definitions.

Validates that new columns and models are correctly defined
in the SQLAlchemy ORM layer. No database required — inspects
mapper metadata only.
"""
from decimal import Decimal

import pytest
from sqlalchemy import inspect as sa_inspect

from app.models.route import Route
from app.models.driver import Driver
from app.models.geo import RouteHexStat, VehicleHexAffinity
from app.models.insertion import InsertionAttempt
from app.models.labor import DriverLaborLog, LaborViolation


def _column_names(model_cls) -> set[str]:
    """Return the set of column names for an ORM model."""
    mapper = sa_inspect(model_cls)
    return {col.key for col in mapper.columns}


# ---------------------------------------------------------------------------
# Route model — v3.1 columns
# ---------------------------------------------------------------------------

class TestRouteV31Columns:

    def test_has_version(self):
        assert "version" in _column_names(Route)

    def test_has_route_signature(self):
        assert "route_signature" in _column_names(Route)

    def test_has_actual_success_score(self):
        assert "actual_success_score" in _column_names(Route)

    def test_version_default(self):
        col = Route.__table__.c.version
        assert col.default.arg == 1

    def test_route_signature_nullable(self):
        col = Route.__table__.c.route_signature
        assert col.nullable is True


# ---------------------------------------------------------------------------
# Driver model — v3.1 columns
# ---------------------------------------------------------------------------

class TestDriverV31Columns:

    def test_has_accumulated_weekly_minutes(self):
        assert "accumulated_weekly_minutes" in _column_names(Driver)

    def test_has_accumulated_daily_minutes(self):
        assert "accumulated_daily_minutes" in _column_names(Driver)

    def test_has_weekly_reset_at(self):
        assert "weekly_reset_at" in _column_names(Driver)

    def test_weekly_minutes_default(self):
        col = Driver.__table__.c.accumulated_weekly_minutes
        assert col.default.arg == 0

    def test_daily_minutes_default(self):
        col = Driver.__table__.c.accumulated_daily_minutes
        assert col.default.arg == 0


# ---------------------------------------------------------------------------
# RouteHexStat
# ---------------------------------------------------------------------------

class TestRouteHexStat:

    def test_tablename(self):
        assert RouteHexStat.__tablename__ == "route_hex_stats"

    def test_has_h3_index(self):
        assert "h3_index" in _column_names(RouteHexStat)

    def test_has_difficulty_factor(self):
        assert "difficulty_factor" in _column_names(RouteHexStat)

    def test_difficulty_factor_default(self):
        col = RouteHexStat.__table__.c.difficulty_factor
        assert col.default.arg == Decimal("0.5")

    def test_unique_constraint_on_h3_index(self):
        constraints = RouteHexStat.__table__.constraints
        unique_names = {
            c.name for c in constraints
            if hasattr(c, "columns") and "h3_index" in {col.name for col in c.columns}
        }
        assert "uq_route_hex_stats_h3" in unique_names


# ---------------------------------------------------------------------------
# VehicleHexAffinity
# ---------------------------------------------------------------------------

class TestVehicleHexAffinity:

    def test_tablename(self):
        assert VehicleHexAffinity.__tablename__ == "vehicle_hex_affinities"

    def test_has_vehicle_id(self):
        assert "vehicle_id" in _column_names(VehicleHexAffinity)

    def test_has_affinity_score(self):
        assert "affinity_score" in _column_names(VehicleHexAffinity)

    def test_unique_constraint_vehicle_h3(self):
        constraints = VehicleHexAffinity.__table__.constraints
        unique_names = {c.name for c in constraints}
        assert "uq_vehicle_hex_affinity" in unique_names


# ---------------------------------------------------------------------------
# InsertionAttempt
# ---------------------------------------------------------------------------

class TestInsertionAttempt:

    def test_tablename(self):
        assert InsertionAttempt.__tablename__ == "insertion_attempts"

    def test_has_required_columns(self):
        cols = _column_names(InsertionAttempt)
        for expected in ("route_id", "shipment_id", "target_route_version",
                         "proposed_position", "status"):
            assert expected in cols, f"Missing column: {expected}"

    def test_status_default(self):
        col = InsertionAttempt.__table__.c.status
        assert col.default.arg == "PENDING"


# ---------------------------------------------------------------------------
# DriverLaborLog
# ---------------------------------------------------------------------------

class TestDriverLaborLog:

    def test_tablename(self):
        assert DriverLaborLog.__tablename__ == "driver_labor_logs"

    def test_has_computed_total_minutes(self):
        col = DriverLaborLog.__table__.c.total_minutes
        assert col.computed is not None

    def test_unique_constraint(self):
        constraints = DriverLaborLog.__table__.constraints
        unique_names = {c.name for c in constraints}
        assert "uq_driver_labor_log" in unique_names

    def test_has_shift_columns(self):
        cols = _column_names(DriverLaborLog)
        assert "shift_start" in cols
        assert "shift_end" in cols


# ---------------------------------------------------------------------------
# LaborViolation
# ---------------------------------------------------------------------------

class TestLaborViolation:

    def test_tablename(self):
        assert LaborViolation.__tablename__ == "labor_violations"

    def test_has_required_columns(self):
        cols = _column_names(LaborViolation)
        for expected in ("driver_id", "violation_type", "severity",
                         "projected_minutes", "limit_minutes",
                         "overage_minutes", "was_overridden"):
            assert expected in cols, f"Missing column: {expected}"

    def test_severity_default(self):
        col = LaborViolation.__table__.c.severity
        assert col.default.arg == "WARNING"

    def test_was_overridden_default(self):
        col = LaborViolation.__table__.c.was_overridden
        assert col.default.arg is False
