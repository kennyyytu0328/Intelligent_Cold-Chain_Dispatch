"""
Tests for Alembic migrations.

Requires a PostgreSQL database. Uses the Docker test DB on port 5434 by default.
Set MIGRATION_TEST_DB_URL env var to override.

Run:
    pytest tests/test_migrations.py -v -m migration
"""
import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MIGRATION_DB_URL = os.environ.get(
    "MIGRATION_TEST_DB_URL",
    "postgresql://postgres:postgres@127.0.0.1:5434/iccdds_migration_test",
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _can_connect(url: str) -> bool:
    """Check if we can connect to the migration test database."""
    try:
        engine = create_engine(url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return True
    except Exception:
        return False


skip_no_db = pytest.mark.skipif(
    not _can_connect(MIGRATION_DB_URL),
    reason=f"Migration test DB not available at {MIGRATION_DB_URL}",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def alembic_cfg():
    """Create Alembic config pointing to the test database."""
    cfg = Config(os.path.join(PROJECT_ROOT, "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", MIGRATION_DB_URL)
    cfg.set_main_option("script_location", os.path.join(PROJECT_ROOT, "alembic"))
    return cfg


@pytest.fixture(scope="module")
def engine():
    """Create SQLAlchemy engine for the test database."""
    eng = create_engine(MIGRATION_DB_URL)
    yield eng
    eng.dispose()


@pytest.fixture(autouse=True)
def _clean_db(engine, alembic_cfg):
    """Ensure DB starts clean before each test."""
    command.downgrade(alembic_cfg, "base")
    yield
    command.downgrade(alembic_cfg, "base")


# ---------------------------------------------------------------------------
# Structural tests (no DB needed)
# ---------------------------------------------------------------------------
class TestMigrationStructure:
    """Tests that verify migration file structure without a database."""

    def test_migration_files_exist(self):
        versions_dir = os.path.join(PROJECT_ROOT, "alembic", "versions")
        files = os.listdir(versions_dir)
        assert "001_baseline.py" in files
        assert "002_features_v3.py" in files

    def test_revision_chain(self):
        import importlib.util

        versions_dir = os.path.join(PROJECT_ROOT, "alembic", "versions")

        spec1 = importlib.util.spec_from_file_location(
            "baseline", os.path.join(versions_dir, "001_baseline.py")
        )
        mod1 = importlib.util.module_from_spec(spec1)
        spec1.loader.exec_module(mod1)

        spec2 = importlib.util.spec_from_file_location(
            "features_v3", os.path.join(versions_dir, "002_features_v3.py")
        )
        mod2 = importlib.util.module_from_spec(spec2)
        spec2.loader.exec_module(mod2)

        assert mod1.revision == "0001"
        assert mod1.down_revision is None
        assert mod2.revision == "0002"
        assert mod2.down_revision == "0001"


# ---------------------------------------------------------------------------
# Functional tests (require DB)
# ---------------------------------------------------------------------------
@pytest.mark.migration
@skip_no_db
class TestBaselineMigration:
    """Test 001_baseline upgrade creates all base tables."""

    BASE_TABLES = {
        "alerts",
        "customers",
        "depots",
        "drivers",
        "optimization_jobs",
        "route_stops",
        "routes",
        "shipments",
        "temperature_logs",
        "users",
        "vehicles",
    }

    def test_upgrade_creates_all_tables(self, engine, alembic_cfg):
        command.upgrade(alembic_cfg, "0001")
        insp = inspect(engine)
        tables = set(insp.get_table_names())
        assert self.BASE_TABLES.issubset(tables)

    def test_upgrade_creates_enum_types(self, engine, alembic_cfg):
        command.upgrade(alembic_cfg, "0001")
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT typname FROM pg_type WHERE typname IN "
                    "('insulation_grade', 'door_type', 'sla_tier', "
                    "'shipment_status', 'route_status', 'vehicle_status') "
                    "ORDER BY typname"
                )
            )
            enums = {row[0] for row in result}
        expected = {
            "insulation_grade",
            "door_type",
            "sla_tier",
            "shipment_status",
            "route_status",
            "vehicle_status",
        }
        assert enums == expected

    def test_upgrade_creates_trigger_function(self, engine, alembic_cfg):
        command.upgrade(alembic_cfg, "0001")
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT proname FROM pg_proc "
                    "WHERE proname = 'update_updated_at_column'"
                )
            )
            assert result.fetchone() is not None

    def test_upgrade_creates_validate_function(self, engine, alembic_cfg):
        command.upgrade(alembic_cfg, "0001")
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT proname FROM pg_proc "
                    "WHERE proname = 'validate_time_windows'"
                )
            )
            assert result.fetchone() is not None

    def test_downgrade_removes_all_tables(self, engine, alembic_cfg):
        command.upgrade(alembic_cfg, "0001")
        command.downgrade(alembic_cfg, "base")
        insp = inspect(engine)
        tables = set(insp.get_table_names()) - {"spatial_ref_sys", "alembic_version"}
        assert tables == set()


@pytest.mark.migration
@skip_no_db
class TestFeaturesV3Migration:
    """Test 002_features_v3 adds v3.1 tables and columns."""

    V3_TABLES = {
        "route_hex_stats",
        "vehicle_hex_affinities",
        "insertion_attempts",
        "driver_labor_logs",
        "labor_violations",
    }

    ROUTES_NEW_COLUMNS = {"version", "route_signature", "actual_success_score"}
    DRIVERS_NEW_COLUMNS = {
        "accumulated_weekly_minutes",
        "accumulated_daily_minutes",
        "weekly_reset_at",
    }

    def test_upgrade_creates_v3_tables(self, engine, alembic_cfg):
        command.upgrade(alembic_cfg, "head")
        insp = inspect(engine)
        tables = set(insp.get_table_names())
        assert self.V3_TABLES.issubset(tables)

    def test_upgrade_adds_routes_columns(self, engine, alembic_cfg):
        command.upgrade(alembic_cfg, "head")
        insp = inspect(engine)
        columns = {c["name"] for c in insp.get_columns("routes")}
        assert self.ROUTES_NEW_COLUMNS.issubset(columns)

    def test_upgrade_adds_drivers_columns(self, engine, alembic_cfg):
        command.upgrade(alembic_cfg, "head")
        insp = inspect(engine)
        columns = {c["name"] for c in insp.get_columns("drivers")}
        assert self.DRIVERS_NEW_COLUMNS.issubset(columns)

    def test_downgrade_removes_v3_tables(self, engine, alembic_cfg):
        command.upgrade(alembic_cfg, "head")
        command.downgrade(alembic_cfg, "0001")
        insp = inspect(engine)
        tables = set(insp.get_table_names())
        for table in self.V3_TABLES:
            assert table not in tables

    def test_downgrade_removes_new_columns(self, engine, alembic_cfg):
        command.upgrade(alembic_cfg, "head")
        command.downgrade(alembic_cfg, "0001")
        insp = inspect(engine)
        route_cols = {c["name"] for c in insp.get_columns("routes")}
        driver_cols = {c["name"] for c in insp.get_columns("drivers")}
        assert self.ROUTES_NEW_COLUMNS.isdisjoint(route_cols)
        assert self.DRIVERS_NEW_COLUMNS.isdisjoint(driver_cols)


@pytest.mark.migration
@skip_no_db
class TestMigrationRoundTrip:
    """Test full upgrade -> downgrade -> upgrade cycle."""

    def test_full_round_trip(self, engine, alembic_cfg):
        # Upgrade to head
        command.upgrade(alembic_cfg, "head")
        insp = inspect(engine)
        tables_after_up = set(insp.get_table_names())
        assert "routes" in tables_after_up
        assert "route_hex_stats" in tables_after_up

        # Downgrade to base
        command.downgrade(alembic_cfg, "base")
        insp = inspect(engine)
        tables_after_down = set(insp.get_table_names()) - {
            "spatial_ref_sys",
            "alembic_version",
        }
        assert tables_after_down == set()

        # Upgrade to head again
        command.upgrade(alembic_cfg, "head")
        insp = inspect(engine)
        tables_after_reup = set(insp.get_table_names())
        assert tables_after_up == tables_after_reup
