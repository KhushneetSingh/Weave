"""Celery worker configuration for Weave."""

from celery import Celery

from app.config import settings

celery_app = Celery(
    "weave",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)


@celery_app.task
def example_task(message: str) -> dict:
    """Placeholder task to verify worker is running."""
    return {"status": "ok", "message": message}
