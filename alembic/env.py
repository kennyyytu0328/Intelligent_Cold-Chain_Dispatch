"""
Alembic migration environment for ICCDDS.

Reads database URL from app settings and registers all ORM models
so autogenerate can detect schema changes.
"""
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# Alembic Config object
config = context.config

# Set up Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ---------------------------------------------------------------------------
# Import app settings and models
# ---------------------------------------------------------------------------
from app.core.config import get_settings  # noqa: E402

settings = get_settings()

# Override sqlalchemy.url from app settings (sync driver for migrations).
# Allow override via: alembic -x db_url=postgresql://... upgrade head
db_url = config.get_main_option("sqlalchemy.url")
cmd_line_url = context.get_x_argument(as_dictionary=True).get("db_url")
if cmd_line_url:
    db_url = cmd_line_url
elif not db_url:
    db_url = settings.database_url_sync
config.set_main_option("sqlalchemy.url", db_url)

# Import all ORM models so Base.metadata knows about every table.
# This is required for autogenerate to detect schema changes.
from app.db.database import Base  # noqa: E402
import app.models  # noqa: E402, F401

target_metadata = Base.metadata


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
# Tables to exclude from autogenerate (PostGIS internals, etc.)
EXCLUDE_TABLES = {"spatial_ref_sys"}


def include_object(object, name, type_, reflected, compare_to):
    """Filter out PostGIS internal tables from autogenerate."""
    if type_ == "table" and name in EXCLUDE_TABLES:
        return False
    return True


# ---------------------------------------------------------------------------
# Migration runners
# ---------------------------------------------------------------------------
def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (SQL script generation)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (direct database connection)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
