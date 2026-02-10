"""001_baseline

Baseline migration capturing the full ICCDDS schema.
Matches app/db/schema.sql exactly (minus sample data).

Revision ID: 0001
Revises: (none)
Create Date: 2026-02-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Extensions
    # ------------------------------------------------------------------
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "postgis"')

    # ------------------------------------------------------------------
    # Enum types
    # ------------------------------------------------------------------
    op.execute(
        "CREATE TYPE insulation_grade AS ENUM ('PREMIUM', 'STANDARD', 'BASIC')"
    )
    op.execute("CREATE TYPE door_type AS ENUM ('ROLL', 'SWING')")
    op.execute("CREATE TYPE sla_tier AS ENUM ('STRICT', 'STANDARD')")
    op.execute(
        "CREATE TYPE shipment_status AS ENUM "
        "('PENDING', 'ASSIGNED', 'IN_TRANSIT', 'DELIVERED', 'FAILED', 'CANCELLED')"
    )
    op.execute(
        "CREATE TYPE route_status AS ENUM "
        "('PLANNING', 'SCHEDULED', 'IN_PROGRESS', 'COMPLETED', 'ABORTED')"
    )
    op.execute(
        "CREATE TYPE vehicle_status AS ENUM "
        "('AVAILABLE', 'IN_USE', 'MAINTENANCE', 'OFFLINE')"
    )

    # ------------------------------------------------------------------
    # Tables (dependency order)
    # ------------------------------------------------------------------

    # --- drivers ---
    op.execute("""
        CREATE TABLE drivers (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            employee_id VARCHAR(50) UNIQUE NOT NULL,
            name VARCHAR(100) NOT NULL,
            phone VARCHAR(20),
            email VARCHAR(100),
            license_number VARCHAR(50) NOT NULL,
            license_expiry DATE NOT NULL,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # --- depots ---
    op.execute("""
        CREATE TABLE depots (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            name VARCHAR(100) NOT NULL,
            code VARCHAR(50) UNIQUE,
            address TEXT,
            latitude DECIMAL(10, 8) NOT NULL,
            longitude DECIMAL(11, 8) NOT NULL,
            location GEOGRAPHY(POINT, 4326),
            is_active BOOLEAN DEFAULT TRUE,
            contact_person VARCHAR(100),
            contact_phone VARCHAR(20),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT valid_latitude CHECK (latitude BETWEEN -90 AND 90),
            CONSTRAINT valid_longitude CHECK (longitude BETWEEN -180 AND 180)
        )
    """)

    # --- users ---
    op.execute("""
        CREATE TABLE users (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            username VARCHAR(50) UNIQUE NOT NULL,
            hashed_password VARCHAR(255) NOT NULL,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # --- vehicles ---
    op.execute("""
        CREATE TABLE vehicles (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            license_plate VARCHAR(20) UNIQUE NOT NULL,
            driver_id UUID REFERENCES drivers(id),
            driver_name VARCHAR(100),
            capacity_weight DECIMAL(10,2) NOT NULL,
            capacity_volume DECIMAL(10,2) NOT NULL,
            internal_length DECIMAL(6,2),
            internal_width DECIMAL(6,2),
            internal_height DECIMAL(6,2),
            insulation_grade insulation_grade NOT NULL DEFAULT 'STANDARD',
            k_value DECIMAL(5,4) NOT NULL DEFAULT 0.05,
            door_type door_type NOT NULL DEFAULT 'ROLL',
            door_coefficient DECIMAL(4,2) NOT NULL DEFAULT 0.8,
            has_strip_curtains BOOLEAN NOT NULL DEFAULT FALSE,
            cooling_rate DECIMAL(5,2) NOT NULL DEFAULT -2.5,
            min_temp_capability DECIMAL(5,2) NOT NULL DEFAULT -25.0,
            status vehicle_status NOT NULL DEFAULT 'AVAILABLE',
            current_location GEOMETRY(POINT, 4326),
            current_temperature DECIMAL(5,2),
            last_telemetry_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # --- customers ---
    op.execute("""
        CREATE TABLE customers (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            customer_code VARCHAR(50) UNIQUE NOT NULL,
            name VARCHAR(200) NOT NULL,
            contact_name VARCHAR(100),
            phone VARCHAR(20),
            email VARCHAR(100),
            default_sla_tier sla_tier NOT NULL DEFAULT 'STANDARD',
            default_temp_limit DECIMAL(5,2) DEFAULT 5.0,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # --- optimization_jobs (must exist before routes for FK) ---
    op.execute("""
        CREATE TABLE optimization_jobs (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            celery_task_id VARCHAR(100) UNIQUE,
            status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
            progress INTEGER NOT NULL DEFAULT 0,
            plan_date DATE NOT NULL,
            vehicle_ids UUID[],
            shipment_ids UUID[],
            parameters JSONB,
            result_summary JSONB,
            route_ids UUID[],
            unassigned_shipment_ids UUID[],
            started_at TIMESTAMP WITH TIME ZONE,
            completed_at TIMESTAMP WITH TIME ZONE,
            error_message TEXT,
            error_traceback TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # --- shipments (FK to customers; route_id FK added later) ---
    op.execute("""
        CREATE TABLE shipments (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            order_number VARCHAR(50) UNIQUE NOT NULL,
            customer_id UUID REFERENCES customers(id),
            delivery_address TEXT NOT NULL,
            geo_location GEOMETRY(POINT, 4326) NOT NULL,
            latitude DECIMAL(10,7) NOT NULL,
            longitude DECIMAL(10,7) NOT NULL,
            time_windows JSONB NOT NULL,
            sla_tier sla_tier NOT NULL DEFAULT 'STANDARD',
            temp_limit_upper DECIMAL(5,2) NOT NULL DEFAULT 5.0,
            temp_limit_lower DECIMAL(5,2),
            service_duration INTEGER NOT NULL DEFAULT 15,
            weight DECIMAL(10,2) NOT NULL,
            volume DECIMAL(10,2),
            dimensions JSONB,
            package_count INTEGER DEFAULT 1,
            status shipment_status NOT NULL DEFAULT 'PENDING',
            route_id UUID,
            route_sequence INTEGER,
            actual_arrival_at TIMESTAMP WITH TIME ZONE,
            actual_temperature DECIMAL(5,2),
            was_on_time BOOLEAN,
            was_temp_compliant BOOLEAN,
            delivery_notes TEXT,
            priority INTEGER DEFAULT 0,
            special_instructions TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # --- routes ---
    op.execute("""
        CREATE TABLE routes (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            route_code VARCHAR(50) UNIQUE NOT NULL,
            plan_date DATE NOT NULL,
            vehicle_id UUID NOT NULL REFERENCES vehicles(id),
            driver_id UUID REFERENCES drivers(id),
            driver_name VARCHAR(100),
            status route_status NOT NULL DEFAULT 'PLANNING',
            total_stops INTEGER NOT NULL DEFAULT 0,
            total_distance DECIMAL(10,2),
            total_duration INTEGER,
            total_weight DECIMAL(10,2),
            total_volume DECIMAL(10,2),
            initial_temperature DECIMAL(5,2) NOT NULL,
            predicted_final_temp DECIMAL(5,2),
            predicted_max_temp DECIMAL(5,2),
            planned_departure_at TIMESTAMP WITH TIME ZONE,
            planned_return_at TIMESTAMP WITH TIME ZONE,
            actual_departure_at TIMESTAMP WITH TIME ZONE,
            actual_return_at TIMESTAMP WITH TIME ZONE,
            depot_address TEXT,
            depot_location GEOMETRY(POINT, 4326),
            optimization_job_id UUID REFERENCES optimization_jobs(id),
            optimization_cost DECIMAL(15,4),
            algorithm_version VARCHAR(20),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Add FK from shipments.route_id -> routes.id
    op.execute("""
        ALTER TABLE shipments
        ADD CONSTRAINT fk_shipments_route
        FOREIGN KEY (route_id) REFERENCES routes(id)
    """)

    # --- route_stops ---
    op.execute("""
        CREATE TABLE route_stops (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            route_id UUID NOT NULL REFERENCES routes(id) ON DELETE CASCADE,
            shipment_id UUID NOT NULL REFERENCES shipments(id),
            sequence_number INTEGER NOT NULL,
            location GEOMETRY(POINT, 4326) NOT NULL,
            address TEXT NOT NULL,
            expected_arrival_at TIMESTAMP WITH TIME ZONE NOT NULL,
            expected_departure_at TIMESTAMP WITH TIME ZONE NOT NULL,
            target_time_window_index INTEGER DEFAULT 0,
            slack_minutes INTEGER,
            predicted_arrival_temp DECIMAL(5,2) NOT NULL,
            transit_temp_rise DECIMAL(5,2),
            service_temp_rise DECIMAL(5,2),
            cooling_applied DECIMAL(5,2),
            predicted_departure_temp DECIMAL(5,2),
            is_temp_feasible BOOLEAN NOT NULL DEFAULT TRUE,
            distance_from_prev DECIMAL(10,2),
            travel_time_from_prev INTEGER,
            actual_arrival_at TIMESTAMP WITH TIME ZONE,
            actual_temperature DECIMAL(5,2),
            delivery_status VARCHAR(20),
            notes TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (route_id, sequence_number)
        )
    """)

    # --- temperature_logs ---
    op.execute("""
        CREATE TABLE temperature_logs (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            vehicle_id UUID NOT NULL REFERENCES vehicles(id),
            route_id UUID REFERENCES routes(id),
            temperature DECIMAL(5,2) NOT NULL,
            location GEOMETRY(POINT, 4326),
            recorded_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            is_cooling_active BOOLEAN,
            ambient_temperature DECIMAL(5,2)
        )
    """)

    # --- alerts ---
    op.execute("""
        CREATE TABLE alerts (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            vehicle_id UUID REFERENCES vehicles(id),
            route_id UUID REFERENCES routes(id),
            shipment_id UUID REFERENCES shipments(id),
            alert_type VARCHAR(50) NOT NULL,
            severity VARCHAR(20) NOT NULL DEFAULT 'WARNING',
            message TEXT NOT NULL,
            details JSONB,
            current_temperature DECIMAL(5,2),
            threshold_temperature DECIMAL(5,2),
            is_acknowledged BOOLEAN DEFAULT FALSE,
            acknowledged_by UUID,
            acknowledged_at TIMESTAMP WITH TIME ZONE,
            is_resolved BOOLEAN DEFAULT FALSE,
            resolved_at TIMESTAMP WITH TIME ZONE,
            resolution_notes TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ------------------------------------------------------------------
    # Indexes
    # ------------------------------------------------------------------

    # Depots
    op.execute("CREATE INDEX idx_depots_location ON depots USING GIST (location)")
    op.execute("CREATE INDEX idx_depots_is_active ON depots (is_active)")

    # Users
    op.execute("CREATE INDEX idx_users_username ON users (username)")
    op.execute("CREATE INDEX idx_users_is_active ON users (is_active)")

    # Vehicles
    op.execute("CREATE INDEX idx_vehicles_status ON vehicles (status)")
    op.execute(
        "CREATE INDEX idx_vehicles_location ON vehicles USING GIST (current_location)"
    )

    # Shipments
    op.execute("CREATE INDEX idx_shipments_status ON shipments (status)")
    op.execute("CREATE INDEX idx_shipments_route_id ON shipments (route_id)")
    op.execute(
        "CREATE INDEX idx_shipments_geo ON shipments USING GIST (geo_location)"
    )
    op.execute("CREATE INDEX idx_shipments_customer ON shipments (customer_id)")
    op.execute("CREATE INDEX idx_shipments_created ON shipments (created_at DESC)")

    # Routes
    op.execute("CREATE INDEX idx_routes_status ON routes (status)")
    op.execute("CREATE INDEX idx_routes_plan_date ON routes (plan_date)")
    op.execute("CREATE INDEX idx_routes_vehicle ON routes (vehicle_id)")
    op.execute(
        "CREATE INDEX idx_routes_depot_location ON routes USING GIST (depot_location)"
    )

    # Route stops
    op.execute("CREATE INDEX idx_route_stops_route ON route_stops (route_id)")
    op.execute("CREATE INDEX idx_route_stops_shipment ON route_stops (shipment_id)")
    op.execute(
        "CREATE INDEX idx_route_stops_location ON route_stops USING GIST (location)"
    )

    # Optimization jobs
    op.execute("CREATE INDEX idx_optim_jobs_status ON optimization_jobs (status)")
    op.execute(
        "CREATE INDEX idx_optim_jobs_celery ON optimization_jobs (celery_task_id)"
    )

    # Temperature logs
    op.execute(
        "CREATE INDEX idx_temp_logs_recorded_at ON temperature_logs "
        "USING BRIN (recorded_at)"
    )
    op.execute(
        "CREATE INDEX idx_temp_logs_vehicle_id ON temperature_logs (vehicle_id)"
    )

    # Alerts
    op.execute("CREATE INDEX idx_alerts_type ON alerts (alert_type)")
    op.execute(
        "CREATE INDEX idx_alerts_unresolved ON alerts (is_resolved) "
        "WHERE is_resolved = FALSE"
    )
    op.execute("CREATE INDEX idx_alerts_created ON alerts (created_at DESC)")

    # ------------------------------------------------------------------
    # Functions & triggers
    # ------------------------------------------------------------------

    # Trigger function: auto-update updated_at
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = CURRENT_TIMESTAMP;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)

    _tables_with_triggers = [
        "drivers",
        "users",
        "depots",
        "vehicles",
        "customers",
        "shipments",
        "routes",
        "route_stops",
        "optimization_jobs",
    ]
    for table in _tables_with_triggers:
        op.execute(
            f"CREATE TRIGGER update_{table}_updated_at "
            f"BEFORE UPDATE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()"
        )

    # Validation function for shipments.time_windows
    # Note: 'window' is a reserved keyword, use 'tw' instead
    op.execute("""
        CREATE OR REPLACE FUNCTION validate_time_windows(windows JSONB)
        RETURNS BOOLEAN AS $$
        DECLARE
            tw JSONB;
        BEGIN
            IF jsonb_typeof(windows) != 'array' THEN
                RETURN FALSE;
            END IF;
            IF jsonb_array_length(windows) < 1 THEN
                RETURN FALSE;
            END IF;
            FOR tw IN SELECT * FROM jsonb_array_elements(windows)
            LOOP
                IF NOT (tw ? 'start' AND tw ? 'end') THEN
                    RETURN FALSE;
                END IF;
            END LOOP;
            RETURN TRUE;
        END;
        $$ LANGUAGE plpgsql
    """)

    op.execute("""
        ALTER TABLE shipments ADD CONSTRAINT check_time_windows
        CHECK (validate_time_windows(time_windows))
    """)


def downgrade() -> None:
    # ------------------------------------------------------------------
    # Drop check constraints & functions
    # ------------------------------------------------------------------
    op.execute("ALTER TABLE shipments DROP CONSTRAINT IF EXISTS check_time_windows")
    op.execute("DROP FUNCTION IF EXISTS validate_time_windows(JSONB)")

    # Drop triggers
    _tables_with_triggers = [
        "drivers",
        "users",
        "depots",
        "vehicles",
        "customers",
        "shipments",
        "routes",
        "route_stops",
        "optimization_jobs",
    ]
    for table in _tables_with_triggers:
        op.execute(f"DROP TRIGGER IF EXISTS update_{table}_updated_at ON {table}")

    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column()")

    # ------------------------------------------------------------------
    # Drop tables (reverse dependency order)
    # ------------------------------------------------------------------
    op.execute("DROP TABLE IF EXISTS alerts CASCADE")
    op.execute("DROP TABLE IF EXISTS temperature_logs CASCADE")
    op.execute("DROP TABLE IF EXISTS route_stops CASCADE")
    op.execute("DROP TABLE IF EXISTS routes CASCADE")
    op.execute("DROP TABLE IF EXISTS shipments CASCADE")
    op.execute("DROP TABLE IF EXISTS optimization_jobs CASCADE")
    op.execute("DROP TABLE IF EXISTS customers CASCADE")
    op.execute("DROP TABLE IF EXISTS vehicles CASCADE")
    op.execute("DROP TABLE IF EXISTS users CASCADE")
    op.execute("DROP TABLE IF EXISTS depots CASCADE")
    op.execute("DROP TABLE IF EXISTS drivers CASCADE")

    # ------------------------------------------------------------------
    # Drop enum types
    # ------------------------------------------------------------------
    op.execute("DROP TYPE IF EXISTS vehicle_status")
    op.execute("DROP TYPE IF EXISTS route_status")
    op.execute("DROP TYPE IF EXISTS shipment_status")
    op.execute("DROP TYPE IF EXISTS sla_tier")
    op.execute("DROP TYPE IF EXISTS door_type")
    op.execute("DROP TYPE IF EXISTS insulation_grade")
