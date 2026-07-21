"""Shared FastAPI dependencies."""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.video import Video
from app.services.video_service import VideoService


def get_video_service(db: Session = Depends(get_db)) -> VideoService:
    """Provide a :class:`VideoService` bound to the request-scoped session."""
    return VideoService(db)


def get_video_or_404(
    video_id: int, service: VideoService = Depends(get_video_service)
) -> Video:
    """Fetch a video by id or raise a 404."""
    video = service.get(video_id)
    if video is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Video {video_id} not found"
        )
    return video
