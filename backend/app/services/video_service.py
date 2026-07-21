"""Video service: upload handling, metadata extraction and CRUD operations."""
from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging_config import get_logger
from app.models.video import Event, Video, VideoStatus
from app.utils.files import extension_of, unique_filename
from app.utils.video_io import probe_metadata

logger = get_logger(__name__)


class VideoValidationError(ValueError):
    """Raised when an uploaded file fails validation."""


class VideoService:
    """Encapsulates persistence and file-handling for videos."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------ create
    def save_upload(self, upload: UploadFile) -> Video:
        """Validate, store and register an uploaded video file.

        Raises:
            VideoValidationError: On unsupported extension or empty file.
        """
        original = upload.filename or "video"
        ext = extension_of(original)
        if ext not in settings.allowed_extension_set:
            raise VideoValidationError(
                f"Unsupported file type '.{ext}'. Allowed: "
                f"{', '.join(sorted(settings.allowed_extension_set))}."
            )

        stored_name = unique_filename(original)
        dest = settings.videos_dir / stored_name
        dest.parent.mkdir(parents=True, exist_ok=True)

        size = self._write_upload(upload, dest)
        if size == 0:
            dest.unlink(missing_ok=True)
            raise VideoValidationError("Uploaded file is empty.")

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
        logger.info("Stored video id=%s (%s, %.1fs)", video.id, meta.width, meta.duration)
        return video

    def _write_upload(self, upload: UploadFile, dest: Path) -> int:
        """Stream the upload to disk in chunks and return the byte count."""
        size = 0
        max_bytes = settings.max_upload_mb * 1024 * 1024
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

    def list(self, *, status: VideoStatus | None = None) -> list[Video]:
        stmt = select(Video).order_by(Video.created_at.desc())
        if status is not None:
            stmt = stmt.where(Video.status == status)
        return list(self.db.execute(stmt).scalars().all())

    def event_count(self, video_id: int) -> int:
        return int(
            self.db.execute(
                select(func.count(Event.id)).where(Event.video_id == video_id)
            ).scalar_one()
        )

    # ------------------------------------------------------------------ update
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
