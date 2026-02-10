"""002_features_v3

Schema additions for v3.1 features:
- Smart Assignment (route_hex_stats, vehicle_hex_affinities)
- Dynamic Insertion (insertion_attempts, routes.version)
- Labor Hours (driver_labor_logs, labor_violations, drivers columns)

Revision ID: 0002
Revises: 0001
Create Date: 2026-02-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ==================================================================
    # ALTER existing tables
    # ==================================================================

    # --- routes: optimistic locking + smart assignment ---
    op.execute(
        "ALTER TABLE routes ADD COLUMN version INTEGER NOT NULL DEFAULT 1"
    )
    op.execute(
        "ALTER TABLE routes ADD COLUMN route_signature JSONB DEFAULT '[]'::jsonb"
    )
    op.execute(
        "ALTER TABLE routes ADD COLUMN actual_success_score DECIMAL(4,3)"
    )

    # --- drivers: labor hour tracking (denormalized for fast solver reads) ---
    op.execute(
        "ALTER TABLE drivers ADD COLUMN accumulated_weekly_minutes "
        "INTEGER DEFAULT 0"
    )
    op.execute(
        "ALTER TABLE drivers ADD COLUMN accumulated_daily_minutes "
        "INTEGER DEFAULT 0"
    )
    op.execute(
        "ALTER TABLE drivers ADD COLUMN weekly_reset_at "
        "TIMESTAMP WITH TIME ZONE"
    )

    # ==================================================================
    # New tables: Smart Assignment
    # ==================================================================

    # --- route_hex_stats: H3 cell performance metrics ---
    op.execute("""
        CREATE TABLE route_hex_stats (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            h3_index VARCHAR(20) NOT NULL,
            total_deliveries INTEGER DEFAULT 0,
            avg_service_time_minutes INTEGER,
            avg_delay_minutes DECIMAL(6,2) DEFAULT 0,
            difficulty_factor DECIMAL(4,3) DEFAULT 0.5,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_route_hex_stats_h3 UNIQUE (h3_index)
        )
    """)
    op.execute(
        "CREATE INDEX idx_route_hex_stats_h3 ON route_hex_stats (h3_index)"
    )

    # --- vehicle_hex_affinities: driver/vehicle zone affinity scores ---
    op.execute("""
        CREATE TABLE vehicle_hex_affinities (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            vehicle_id UUID NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
            driver_id UUID REFERENCES drivers(id) ON DELETE SET NULL,
            h3_index VARCHAR(20) NOT NULL,
            affinity_score DECIMAL(4,3) DEFAULT 0.5,
            sample_size INTEGER DEFAULT 0,
            avg_on_time_rate DECIMAL(4,3),
            avg_temp_compliance_rate DECIMAL(4,3),
            last_delivery_at TIMESTAMP WITH TIME ZONE,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_vehicle_hex_affinity UNIQUE (vehicle_id, h3_index)
        )
    """)
    op.execute(
        "CREATE INDEX idx_vha_vehicle ON vehicle_hex_affinities (vehicle_id)"
    )
    op.execute(
        "CREATE INDEX idx_vha_h3 ON vehicle_hex_affinities (h3_index)"
    )
    op.execute(
        "CREATE INDEX idx_vha_score ON vehicle_hex_affinities "
        "(affinity_score DESC)"
    )

    # ==================================================================
    # New tables: Dynamic Insertion
    # ==================================================================

    # --- insertion_attempts: audit trail for dynamic route insertions ---
    op.execute("""
        CREATE TABLE insertion_attempts (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            route_id UUID NOT NULL REFERENCES routes(id) ON DELETE CASCADE,
            shipment_id UUID NOT NULL REFERENCES shipments(id),
            target_route_version INTEGER NOT NULL,
            proposed_position INTEGER NOT NULL,
            temp_risk_score DECIMAL(5,3),
            delay_impact_minutes INTEGER,
            extra_distance_meters INTEGER,
            status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
            rejection_reason TEXT,
            attempted_by UUID REFERENCES users(id),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            resolved_at TIMESTAMP WITH TIME ZONE
        )
    """)
    op.execute(
        "CREATE INDEX idx_insertion_route ON insertion_attempts (route_id)"
    )
    op.execute(
        "CREATE INDEX idx_insertion_status ON insertion_attempts (status) "
        "WHERE status = 'PENDING'"
    )

    # ==================================================================
    # New tables: Labor Hours
    # ==================================================================

    # --- driver_labor_logs: granular labor hour tracking ---
    op.execute("""
        CREATE TABLE driver_labor_logs (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            driver_id UUID NOT NULL REFERENCES drivers(id) ON DELETE CASCADE,
            route_id UUID REFERENCES routes(id) ON DELETE SET NULL,
            log_date DATE NOT NULL,
            shift_start TIMESTAMP WITH TIME ZONE NOT NULL,
            shift_end TIMESTAMP WITH TIME ZONE,
            drive_time_minutes INTEGER DEFAULT 0,
            service_time_minutes INTEGER DEFAULT 0,
            break_time_minutes INTEGER DEFAULT 0,
            total_minutes INTEGER GENERATED ALWAYS AS
                (drive_time_minutes + service_time_minutes) STORED,
            source VARCHAR(20) DEFAULT 'SYSTEM',
            notes TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_driver_labor_log UNIQUE (driver_id, route_id, log_date)
        )
    """)
    op.execute(
        "CREATE INDEX idx_labor_driver_date ON driver_labor_logs "
        "(driver_id, log_date)"
    )

    # --- labor_violations: violation and override records ---
    op.execute("""
        CREATE TABLE labor_violations (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            driver_id UUID NOT NULL REFERENCES drivers(id),
            route_id UUID REFERENCES routes(id),
            violation_type VARCHAR(30) NOT NULL,
            severity VARCHAR(10) NOT NULL DEFAULT 'WARNING',
            projected_minutes INTEGER NOT NULL,
            limit_minutes INTEGER NOT NULL,
            overage_minutes INTEGER NOT NULL,
            was_overridden BOOLEAN DEFAULT FALSE,
            overridden_by UUID REFERENCES users(id),
            override_reason TEXT,
            override_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
    """)
    op.execute(
        "CREATE INDEX idx_violation_driver ON labor_violations (driver_id)"
    )
    op.execute(
        "CREATE INDEX idx_violation_unresolved ON labor_violations "
        "(was_overridden) WHERE was_overridden = FALSE"
    )

    # ==================================================================
    # Triggers for new tables with updated_at
    # ==================================================================
    for table in ("route_hex_stats", "vehicle_hex_affinities"):
        op.execute(
            f"CREATE TRIGGER update_{table}_updated_at "
            f"BEFORE UPDATE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()"
        )


def downgrade() -> None:
    # Drop triggers on new tables
    for table in ("route_hex_stats", "vehicle_hex_affinities"):
        op.execute(f"DROP TRIGGER IF EXISTS update_{table}_updated_at ON {table}")

    # Drop new tables (reverse dependency order)
    op.execute("DROP TABLE IF EXISTS labor_violations CASCADE")
    op.execute("DROP TABLE IF EXISTS driver_labor_logs CASCADE")
    op.execute("DROP TABLE IF EXISTS insertion_attempts CASCADE")
    op.execute("DROP TABLE IF EXISTS vehicle_hex_affinities CASCADE")
    op.execute("DROP TABLE IF EXISTS route_hex_stats CASCADE")

    # Remove added columns from drivers
    op.execute("ALTER TABLE drivers DROP COLUMN IF EXISTS weekly_reset_at")
    op.execute("ALTER TABLE drivers DROP COLUMN IF EXISTS accumulated_daily_minutes")
    op.execute("ALTER TABLE drivers DROP COLUMN IF EXISTS accumulated_weekly_minutes")

    # Remove added columns from routes
    op.execute("ALTER TABLE routes DROP COLUMN IF EXISTS actual_success_score")
    op.execute("ALTER TABLE routes DROP COLUMN IF EXISTS route_signature")
    op.execute("ALTER TABLE routes DROP COLUMN IF EXISTS version")
