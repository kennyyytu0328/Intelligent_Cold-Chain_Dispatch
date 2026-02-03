"""
Celery application configuration for ICCDDS.

Celery is used for running long-running optimization tasks asynchronously.
This prevents the FastAPI main thread from being blocked during OR-Tools computations.

Usage:
    # Start worker (from project root):
    celery -A app.core.celery_app worker --loglevel=info

    # Start Flower monitoring (optional):
    celery -A app.core.celery_app flower --port=5555
"""
from celery import Celery

from app.core.config import settings

# Create Celery application
celery_app = Celery(
    "iccdds",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.services.tasks"],  # Auto-discover tasks
)

# Celery configuration
celery_app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Taipei",
    enable_utc=True,

    # Task execution
    task_acks_late=True,  # Acknowledge after task completes (safety)
    task_reject_on_worker_lost=True,

    # Result backend
    result_expires=86400,  # Results expire after 24 hours

    # Worker settings
    worker_prefetch_multiplier=1,  # One task at a time (optimization is heavy)
    worker_concurrency=2,  # Number of worker processes

    # Task routing
    task_routes={
        "app.services.tasks.run_optimization": {"queue": "optimization"},
        "app.services.tasks.*": {"queue": "default"},
    },

    # Task time limits
    task_soft_time_limit=600,  # Soft limit: 10 minutes
    task_time_limit=660,  # Hard limit: 11 minutes

    # Retry settings
    task_default_retry_delay=30,
    task_max_retries=3,
)

# Define task queues
celery_app.conf.task_queues = {
    "default": {
        "exchange": "default",
        "routing_key": "default",
    },
    "optimization": {
        "exchange": "optimization",
        "routing_key": "optimization",
    },
}
