"""Background analysis task runner.

Two execution backends are supported (selected via ``settings.task_backend``):

* ``thread`` – runs the pipeline in a daemon thread using its own DB session.
  Zero external dependencies; ideal for a single-node deployment or demos.
* ``celery`` – delegates to a Celery task (see :mod:`app.workers.celery_app`),
  suitable when Redis + separate workers are available.

Both paths share :func:`run_analysis` which owns the full lifecycle: status
transitions, progress reporting and error capture.
"""
from __future__ import annotations

import threading

from app.core.config import settings
from app.core.logging_config import get_logger
from app.database.session import SessionLocal
from app.models.video import Video, VideoStatus
from app.services.pipeline import AnalysisPipeline, PipelineConfig

logger = get_logger(__name__)


def run_analysis(video_id: int, config: PipelineConfig) -> None:
    """Run the full analysis pipeline for ``video_id`` with its own DB session.

    This function is safe to call from a thread or a Celery worker. It never
    raises: failures are recorded on the video row so the API can surface them.
    """
    db = SessionLocal()
    try:
        video = db.get(Video, video_id)
        if video is None:
            logger.error("run_analysis: video %s not found", video_id)
            return

        video.status = VideoStatus.PROCESSING
        video.progress = 0.0
        video.status_message = "Starting analysis"
        video.error = None
        db.commit()

        def progress_cb(pct: float, message: str) -> None:
            video.progress = round(pct, 2)
            video.status_message = message
            db.commit()

        pipeline = AnalysisPipeline(config=config, settings=settings)
        summary = pipeline.run(video, db, progress_cb=progress_cb)
        logger.info("Analysis complete for video %s: %s", video_id, summary)

    except Exception as exc:  # noqa: BLE001 - record and swallow
        logger.exception("Analysis failed for video %s", video_id)
        db.rollback()
        video = db.get(Video, video_id)
        if video is not None:
            video.status = VideoStatus.FAILED
            video.status_message = "Analysis failed"
            video.error = str(exc)
            db.commit()
    finally:
        db.close()


def enqueue_analysis(video_id: int, config: PipelineConfig) -> None:
    """Schedule analysis using the configured backend (thread or celery)."""
    if settings.task_backend == "celery":
        try:
            from app.workers.celery_app import analyze_video_task

            analyze_video_task.delay(video_id, config.__dict__)
            logger.info("Enqueued Celery analysis for video %s", video_id)
            return
        except Exception as exc:  # noqa: BLE001 - fall back to threads
            logger.warning("Celery unavailable (%s); using thread backend", exc)

    thread = threading.Thread(
        target=run_analysis,
        args=(video_id, config),
        name=f"analysis-{video_id}",
        daemon=True,
    )
    thread.start()
    logger.info("Started thread analysis for video %s", video_id)
