"""Optional Celery application and task.

Only imported when ``settings.task_backend == 'celery'``. Requires Redis. The
task simply reconstructs the :class:`PipelineConfig` and delegates to the shared
:func:`app.workers.tasks.run_analysis` implementation.
"""
from __future__ import annotations

from celery import Celery

from app.core.config import settings
from app.services.pipeline import PipelineConfig

celery_app = Celery(
    "video_analytics",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    worker_max_tasks_per_child=10,
)


@celery_app.task(name="analyze_video")
def analyze_video_task(video_id: int, config_dict: dict) -> dict:
    """Celery entry point: run analysis for a video."""
    from app.workers.tasks import run_analysis

    config = PipelineConfig(**config_dict)
    run_analysis(video_id, config)
    return {"video_id": video_id, "status": "done"}
