"""Shared FastAPI dependencies and cross-route response mappers."""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.video import Video
from app.schemas.video import VideoDetail
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


def to_video_detail(video: Video, service: VideoService) -> VideoDetail:
    """Build the full :class:`VideoDetail` response (shared by every route
    that returns one) so event counts are always populated consistently.
    ``processing_stats`` is parsed from its stored JSON-text form by a
    validator on the schema itself (see ``app/schemas/video.py``)."""
    detail = VideoDetail.model_validate(video)
    detail.event_count = service.event_count(video.id)
    return detail
