"""
Application configuration using Pydantic Settings.

Loads configuration from environment variables and .env file.
"""
from decimal import Decimal
from functools import lru_cache
from typing import Optional

from pydantic import Field, PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # =========================================================================
    # Application
    # =========================================================================
    app_name: str = "ICCDDS"
    app_version: str = "1.0.0"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    # =========================================================================
    # Security & Authentication
    # =========================================================================
    secret_key: str = Field(
        default="CHANGE_THIS_IN_PRODUCTION_PLEASE_USE_OPENSSL_RAND_HEX_32",
        description="Secret key for JWT signing (use openssl rand -hex 32)",
    )
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440  # 24 hours

    # =========================================================================
    # Database
    # =========================================================================
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/iccdds",
        description="PostgreSQL connection URL (async)",
    )

    # Sync URL for Celery workers (they can't use async)
    database_url_sync: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/iccdds",
        description="PostgreSQL connection URL (sync for Celery)",
    )

    db_pool_size: int = 10
    db_max_overflow: int = 20

    # =========================================================================
    # Redis & Celery
    # =========================================================================
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis URL for Celery broker",
    )

    celery_broker_url: str = Field(
        default="redis://localhost:6379/0",
        description="Celery message broker URL",
    )

    celery_result_backend: str = Field(
        default="redis://localhost:6379/1",
        description="Celery result backend URL",
    )

    # =========================================================================
    # Optimization Defaults
    # =========================================================================
    default_solver_time_limit: int = Field(
        default=300,
        description="Default solver time limit in seconds",
    )

    default_ambient_temperature: Decimal = Field(
        default=Decimal("30.0"),
        description="Default ambient temperature (°C)",
    )

    default_initial_vehicle_temp: Decimal = Field(
        default=Decimal("-5.0"),
        description="Default initial vehicle temperature (°C)",
    )

    # =========================================================================
    # Depot Configuration
    # =========================================================================
    default_depot_latitude: Decimal = Field(
        default=Decimal("25.0330"),
        description="Default depot latitude",
    )

    default_depot_longitude: Decimal = Field(
        default=Decimal("121.5654"),
        description="Default depot longitude",
    )

    default_depot_address: str = Field(
        default="台北市信義區物流中心",
        description="Default depot address",
    )

    # =========================================================================
    # Constraint Penalties (for OR-Tools)
    # =========================================================================
    # Penalty for violating temperature constraint (per degree over limit)
    temp_violation_penalty: int = Field(
        default=100000,
        description="Penalty per degree over temperature limit",
    )

    # Penalty for late delivery (per minute late)
    late_delivery_penalty: int = Field(
        default=1000,
        description="Penalty per minute late for STANDARD SLA",
    )

    # Cost for using an additional vehicle
    vehicle_fixed_cost: int = Field(
        default=50000,
        description="Fixed cost for using a vehicle",
    )

    # Cost per kilometer
    distance_cost_per_km: int = Field(
        default=10,
        description="Variable cost per kilometer",
    )

    # =========================================================================
    # Speed & Time Estimates
    # =========================================================================
    average_speed_kmh: int = Field(
        default=30,
        description="Average vehicle speed in km/h for time estimation",
    )

    # =========================================================================
    # Infeasibility Markers
    # =========================================================================
    infeasible_cost: int = Field(
        default=10000000,
        description="Cost to mark a route as infeasible",
    )


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Convenience alias
settings = get_settings()
