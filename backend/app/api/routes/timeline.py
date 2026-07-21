"""Timeline and analytics endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_video_or_404
from app.database.session import get_db
from app.models.video import Video
from app.schemas.analytics import TimelineResponse, VideoAnalytics
from app.services.analytics import compute_analytics, compute_timeline

router = APIRouter(tags=["timeline"])


@router.get("/timeline/{video_id}", response_model=TimelineResponse)
def get_timeline(
    video: Video = Depends(get_video_or_404),
    db: Session = Depends(get_db),
) -> TimelineResponse:
    """Return the motion-intensity timeline and event markers for a video."""
    return compute_timeline(db, video)


@router.get("/analytics/{video_id}", response_model=VideoAnalytics)
def get_analytics(
    video: Video = Depends(get_video_or_404),
    db: Session = Depends(get_db),
) -> VideoAnalytics:
    """Return aggregate dashboard analytics for a video."""
    return compute_analytics(db, video)
