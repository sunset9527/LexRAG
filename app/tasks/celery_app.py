"""Celery application for document-processing jobs."""

from celery import Celery

from config import settings

celery_app = Celery(
    "lexrag",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks.document_tasks", "app.tasks.scenario_tasks", "app.tasks.law_update_tasks"],
)
celery_app.conf.update(
    task_track_started=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    beat_schedule={
        "check-law-update-snapshots": {
            "task": "lexrag.check_law_update_snapshots",
            "schedule": 900.0,
        }
    },
)
