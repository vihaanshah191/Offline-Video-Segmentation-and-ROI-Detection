"""Video service: upload handling, metadata extraction and CRUD operations."""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from fastapi import UploadFile
from sqlalchemy import func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging_config import get_logger
from app.models.video import Event, Video, VideoStatus
from app.utils.files import extension_of, unique_filename
from app.utils.validation import validate_video_signature
from app.utils.video_io import probe_metadata

logger = get_logger(__name__)


class VideoValidationError(ValueError):
    """Raised when an uploaded file fails validation."""


@dataclass(slots=True)
class PageResult:
    """A page of results plus the total row count (for pagination headers)."""

    items: list[Video]
    total: int


class VideoService:
    """Encapsulates persistence and file-handling for videos."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------ create
    def save_upload(self, upload: UploadFile, *, content_length: int | None = None) -> Video:
        """Validate, store and register an uploaded video file.

        Args:
            upload: The incoming multipart file.
            content_length: The request's ``Content-Length`` header, if
                present. Used as a fast pre-check to reject obviously
                oversized uploads before streaming any bytes to disk.

        Raises:
            VideoValidationError: On unsupported extension, oversized,
                content/extension mismatch, empty, or unreadable file.
        """
        original = upload.filename or "video"
        ext = extension_of(original)
        if ext not in settings.allowed_extension_set:
            raise VideoValidationError(
                f"Unsupported file type '.{ext}'. Allowed: "
                f"{', '.join(sorted(settings.allowed_extension_set))}."
            )

        if content_length is not None and content_length > settings.max_upload_bytes:
            raise VideoValidationError(
                f"File exceeds maximum size of {settings.max_upload_mb} MB "
                f"(Content-Length reported {content_length / (1024 * 1024):.1f} MB)."
            )

        # A permissive, non-authoritative first filter: browsers/clients set
        # this from the file picker and it is trivially spoofable, but it's a
        # free early rejection for the common case of an obviously-wrong type
        # before we even touch the disk. The magic-byte check below is the
        # actual authoritative content validation.
        if upload.content_type and not (
            upload.content_type.startswith("video/") or upload.content_type == "application/octet-stream"
        ):
            logger.info(
                "Upload '%s' has non-video content-type '%s'; proceeding to authoritative "
                "magic-byte check rather than rejecting on this alone",
                original,
                upload.content_type,
            )

        stored_name = unique_filename(original)
        dest = settings.videos_dir / stored_name
        dest.parent.mkdir(parents=True, exist_ok=True)

        size = self._write_upload(upload, dest)
        if size == 0:
            dest.unlink(missing_ok=True)
            raise VideoValidationError("Uploaded file is empty.")

        signature_ok, signature_reason = validate_video_signature(dest, ext)
        if not signature_ok:
            dest.unlink(missing_ok=True)
            raise VideoValidationError(f"Upload rejected: {signature_reason}")

        try:
            meta = probe_metadata(dest)
        except ValueError as exc:
            dest.unlink(missing_ok=True)
            raise VideoValidationError(f"Unreadable video file: {exc}") from exc

        video = Video(
            filename=stored_name,
            original_name=original,
            path=str(dest),
            fps=meta.fps,
            duration=meta.duration,
            width=meta.width,
            height=meta.height,
            frame_count=meta.frame_count,
            size_bytes=size,
            status=VideoStatus.UPLOADED,
            status_message="Uploaded, awaiting analysis",
        )
        self.db.add(video)
        self.db.commit()
        self.db.refresh(video)
        logger.info(
            "Stored video id=%s (%dx%d, %.1fs, %.1fMB)",
            video.id,
            meta.width,
            meta.height,
            meta.duration,
            size / (1024 * 1024),
        )
        return video

    def load_demo_sample(self) -> Video:
        """Copy the bundled sample recording in as a new video (Demo Mode's
        one-click flow). Ships in the repo, so this works fully offline.

        Raises:
            VideoValidationError: If the sample file is missing (e.g. a
                deployment that stripped ``sample_data/`` from the image).
        """
        source = settings.sample_video_path
        if not source.exists():
            raise VideoValidationError(
                f"Bundled sample video not found at {source}. Demo Mode requires "
                "sample_data/sample_exam_hall.mp4 to be present."
            )

        stored_name = unique_filename(source.name)
        dest = settings.videos_dir / stored_name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
        size = dest.stat().st_size

        meta = probe_metadata(dest)
        video = Video(
            filename=stored_name,
            original_name=f"[Demo] {source.name}",
            path=str(dest),
            fps=meta.fps,
            duration=meta.duration,
            width=meta.width,
            height=meta.height,
            frame_count=meta.frame_count,
            size_bytes=size,
            status=VideoStatus.UPLOADED,
            status_message="Demo sample loaded, awaiting analysis",
        )
        self.db.add(video)
        self.db.commit()
        self.db.refresh(video)
        logger.info("Loaded demo sample as video id=%s", video.id)
        return video

    def _write_upload(self, upload: UploadFile, dest: Path) -> int:
        """Stream the upload to disk in chunks and return the byte count."""
        size = 0
        max_bytes = settings.max_upload_bytes
        with dest.open("wb") as buffer:
            upload.file.seek(0)
            while chunk := upload.file.read(1024 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    buffer.close()
                    dest.unlink(missing_ok=True)
                    raise VideoValidationError(
                        f"File exceeds maximum size of {settings.max_upload_mb} MB."
                    )
                buffer.write(chunk)
        return size

    # -------------------------------------------------------------------- read
    def get(self, video_id: int) -> Video | None:
        return self.db.get(Video, video_id)

    def list_page(
        self, *, status: VideoStatus | None = None, limit: int = 100, offset: int = 0
    ) -> PageResult:
        """Return a page of videos plus the total matching row count.

        Non-breaking pagination: the response body shape returned by the API
        route is unchanged (still a plain JSON array) — pagination metadata is
        carried in ``X-Total-Count`` / ``X-Limit`` / ``X-Offset`` response
        headers instead, so existing clients that ignore headers keep working
        exactly as before, while clients that care about paging can use them.
        """
        base_stmt = select(Video)
        if status is not None:
            base_stmt = base_stmt.where(Video.status == status)

        total = int(self.db.execute(select(func.count()).select_from(base_stmt.subquery())).scalar_one())
        stmt = base_stmt.order_by(Video.created_at.desc()).limit(limit).offset(offset)
        items = list(self.db.execute(stmt).scalars().all())
        return PageResult(items=items, total=total)

    def list_queue(self) -> list[Video]:
        """Every currently queued or processing video, oldest-queued first —
        the operational "what's running right now" view for the dashboard
        and the ``/api/queue`` endpoint."""
        stmt = (
            select(Video)
            .where(Video.status.in_([VideoStatus.QUEUED, VideoStatus.PROCESSING]))
            .order_by(Video.created_at.asc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def event_count(self, video_id: int) -> int:
        return int(
            self.db.execute(
                select(func.count(Event.id)).where(Event.video_id == video_id)
            ).scalar_one()
        )

    def global_stats(self) -> dict:
        """Aggregate counts across every video, for the dashboard overview."""
        total_videos = int(self.db.execute(select(func.count(Video.id))).scalar_one())
        completed = int(
            self.db.execute(
                select(func.count(Video.id)).where(Video.status == VideoStatus.COMPLETED)
            ).scalar_one()
        )
        processing = int(
            self.db.execute(
                select(func.count(Video.id)).where(
                    Video.status.in_([VideoStatus.PROCESSING, VideoStatus.QUEUED])
                )
            ).scalar_one()
        )
        failed = int(
            self.db.execute(
                select(func.count(Video.id)).where(Video.status == VideoStatus.FAILED)
            ).scalar_one()
        )
        total_events = int(self.db.execute(select(func.count(Event.id))).scalar_one())
        total_duration = float(
            self.db.execute(select(func.coalesce(func.sum(Video.duration), 0.0))).scalar_one()
        )
        return {
            "total_videos": total_videos,
            "completed_videos": completed,
            "processing_videos": processing,
            "failed_videos": failed,
            "total_events": total_events,
            "total_video_duration_seconds": round(total_duration, 2),
            "free_disk_bytes": self.free_disk_bytes(),
        }

    # ------------------------------------------------------------------ update
    def try_mark_queued(self, video: Video) -> bool:
        """Atomically transition a video to QUEUED iff it isn't already busy.

        A plain "check status, then write" pattern (read in Python, decide,
        then commit) has a TOCTOU race: two near-simultaneous
        ``POST /analyze/{id}`` requests can each read the pre-transition
        status in their own DB session before either commits, both pass the
        "not already processing" check, and both enqueue a duplicate analysis
        run for the same video. This uses a single conditional ``UPDATE ...
        WHERE status NOT IN (...)`` statement instead, so the database (not
        two racing Python code paths) is the sole arbiter of which request
        wins — the classic compare-and-swap pattern, and one that SQLite's
        single-writer model handles correctly without extra locking.

        Returns:
            ``True`` if this call won the transition (caller should enqueue
            the analysis job); ``False`` if the video was already
            queued/processing (caller should reject with 409).
        """
        busy_statuses = (VideoStatus.QUEUED, VideoStatus.PROCESSING)
        result = cast(
            CursorResult,
            self.db.execute(
                update(Video)
                .where(Video.id == video.id, Video.status.not_in(busy_statuses))
                .values(
                    status=VideoStatus.QUEUED,
                    progress=0.0,
                    status_message="Queued for analysis",
                    error=None,
                )
            ),
        )
        self.db.commit()
        won = result.rowcount == 1
        if won:
            self.db.refresh(video)
        return won

    def request_cancel(self, video: Video) -> bool:
        """Set the cooperative-cancellation flag iff the video is currently
        queued or processing.

        Analysis runs in a daemon thread that cannot be forcibly killed, so
        this only *requests* cancellation — the pipeline polls
        ``cancel_requested`` and stops at its next checkpoint (see
        ``AnalysisPipeline._check_cancelled``), then the worker sets the
        video's status to ``CANCELLED``. Uses the same atomic
        conditional-``UPDATE`` pattern as :meth:`try_mark_queued` to avoid a
        TOCTOU race against a run that finishes/fails at the same moment.

        Returns:
            ``True`` if a cancellable run was found and flagged; ``False``
            if the video wasn't queued/processing (nothing to cancel).
        """
        cancellable_statuses = (VideoStatus.QUEUED, VideoStatus.PROCESSING)
        result = cast(
            CursorResult,
            self.db.execute(
                update(Video)
                .where(Video.id == video.id, Video.status.in_(cancellable_statuses))
                .values(cancel_requested=True)
            ),
        )
        self.db.commit()
        won = result.rowcount == 1
        if won:
            self.db.refresh(video)
        return won

    def mark_status(
        self,
        video: Video,
        status: VideoStatus,
        *,
        progress: float | None = None,
        message: str | None = None,
        error: str | None = None,
    ) -> None:
        video.status = status
        if progress is not None:
            video.progress = round(progress, 2)
        if message is not None:
            video.status_message = message
        if error is not None:
            video.error = error
        self.db.commit()

    # ------------------------------------------------------------------ delete
    def delete(self, video: Video) -> None:
        """Delete a video, its DB rows (cascade) and all on-disk artefacts."""
        video_id = video.id
        paths: list[str | None] = [video.path, video.heatmap_path, video.thumbnail_path]
        for event in video.events:
            paths.extend([event.clip_path, event.thumbnail_path])

        self.db.delete(video)
        self.db.commit()

        for path in paths:
            if path:
                Path(path).unlink(missing_ok=True)
        logger.info("Deleted video id=%s and %d artefacts", video_id, len([p for p in paths if p]))

    @staticmethod
    def free_disk_bytes() -> int:
        return shutil.disk_usage(settings.storage_dir).free
