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

import dataclasses
import threading

from app.core.config import settings
from app.core.logging_config import get_logger
from app.database.session import SessionLocal
from app.models.video import Video, VideoStatus
from app.services.pipeline import AnalysisPipeline, PipelineCancelled, PipelineConfig

logger = get_logger(__name__)

# Caps how many analyses actually run at once, regardless of how many are
# queued — batch-uploading N videos (see VideoUpload's multi-file support)
# and analyzing all of them would otherwise spawn N concurrent full decode +
# CV threads with no bound, which can exhaust CPU/memory on a single host.
# A thread blocked on this semaphore leaves its video in 'queued' status
# (not 'processing') until a slot frees up. Read once at import time from
# settings, matching how every other startup-time config value behaves.
_analysis_semaphore = threading.Semaphore(settings.max_concurrent_analyses)


def run_analysis(video_id: int, config: PipelineConfig) -> None:
    """Run the full analysis pipeline for ``video_id`` with its own DB session.

    This function is safe to call from a thread or a Celery worker. It never
    raises: failures are recorded on the video row so the API can surface them.
    Blocks (with the video left in 'queued' status) until a concurrency slot
    is available — see ``settings.max_concurrent_analyses``.
    """
    with _analysis_semaphore:
        _run_analysis_locked(video_id, config)


def _run_analysis_locked(video_id: int, config: PipelineConfig) -> None:
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
            # mypy can't carry the `video is not None` narrowing above into a
            # nested closure (the variable could in principle be reassigned
            # before the closure runs); it never is here.
            assert video is not None
            video.progress = round(pct, 2)
            video.status_message = message
            db.commit()

        pipeline = AnalysisPipeline(config=config, settings=settings)
        summary = pipeline.run(video, db, progress_cb=progress_cb)
        logger.info("Analysis complete for video %s: %s", video_id, summary)

    except PipelineCancelled:
        logger.info("Analysis cancelled for video %s", video_id)
        try:
            db.rollback()
            video = db.get(Video, video_id)
            if video is not None:
                video.status = VideoStatus.CANCELLED
                video.status_message = "Cancelled by user"
                video.cancel_requested = False
                video.error = None
                db.commit()
        except Exception:  # noqa: BLE001 - never let cancellation bookkeeping crash the thread
            logger.exception(
                "Failed to persist CANCELLED status for video %s after cancellation", video_id
            )
    except Exception as exc:  # noqa: BLE001 - record and swallow
        logger.exception("Analysis failed for video %s", video_id)
        try:
            db.rollback()
            video = db.get(Video, video_id)
            if video is not None:
                video.status = VideoStatus.FAILED
                video.status_message = "Analysis failed"
                # Truncate defensively: an unexpected exception's message could
                # in principle be very large (e.g. a library dumping a huge
                # buffer into its message); the column has a practical limit
                # and an oversized value should never itself cause a second
                # failure while we're already in the process of recording one.
                video.error = str(exc)[:4000]
                db.commit()
        except Exception:  # noqa: BLE001 - never let error *reporting* itself crash the thread
            # If the database is unreachable even for this final write, there
            # is nothing more we can do from a background thread — a raised
            # exception here would only be printed to stderr and the thread
            # would die silently with no other record of what happened, so we
            # log with full context instead and return cleanly.
            logger.exception(
                "Failed to persist FAILED status for video %s after analysis error", video_id
            )
    finally:
        db.close()


def enqueue_analysis(video_id: int, config: PipelineConfig) -> None:
    """Schedule analysis using the configured backend (thread or celery)."""
    if settings.task_backend == "celery":
        try:
            from app.workers.celery_app import analyze_video_task

            # PipelineConfig is a slots dataclass (no __dict__); asdict() is
            # the correct way to get a plain, Celery-serializable mapping.
            analyze_video_task.delay(video_id, dataclasses.asdict(config))
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
