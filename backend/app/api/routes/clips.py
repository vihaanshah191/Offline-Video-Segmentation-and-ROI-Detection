"""Clip listing and download endpoints."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_video_or_404
from app.core.config import settings
from app.database.session import get_db
from app.models.video import Event, Video
from app.utils.files import to_relative_url

router = APIRouter(tags=["clips"])


@router.get("/clips/{video_id}")
def list_clips(
    video: Video = Depends(get_video_or_404),
    db: Session = Depends(get_db),
) -> list[dict]:
    """List generated clips (one per event) with URLs and metadata."""
    events = list(
        db.execute(
            select(Event).where(Event.video_id == video.id).order_by(Event.start_time)
        ).scalars().all()
    )
    clips = []
    for event in events:
        if not event.clip_path:
            continue
        clips.append(
            {
                "event_id": event.id,
                "start_time": event.start_time,
                "end_time": event.end_time,
                "duration": event.duration,
                "motion_score": event.motion_score,
                "objects": [o for o in event.objects.split(",") if o],
                "clip_url": to_relative_url(event.clip_path, settings.storage_dir),
                "thumbnail_url": to_relative_url(event.thumbnail_path, settings.storage_dir),
            }
        )
    return clips


@router.get("/clips/{video_id}/{event_id}/download")
def download_clip(
    event_id: int,
    video: Video = Depends(get_video_or_404),
    db: Session = Depends(get_db),
) -> FileResponse:
    """Download a single event clip as an attachment."""
    event = db.get(Event, event_id)
    if event is None or event.video_id != video.id or not event.clip_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip not found")
    path = Path(event.clip_path)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip file missing on disk")
    return FileResponse(
        path,
        media_type="video/mp4",
        filename=f"video{video.id}_event{event.id}.mp4",
    )
