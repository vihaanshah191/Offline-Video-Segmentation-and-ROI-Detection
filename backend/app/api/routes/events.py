"""Event log endpoints with search, filter and sort."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_video_or_404
from app.database.session import get_db
from app.models.video import Event, Video
from app.schemas.event import EventRead

router = APIRouter(tags=["events"])

_SORT_FIELDS = {
    "start_time": Event.start_time,
    "duration": Event.duration,
    "motion_score": Event.motion_score,
    "confidence": Event.confidence,
}


@router.get("/events/{video_id}", response_model=list[EventRead])
def list_events(
    video: Video = Depends(get_video_or_404),
    db: Session = Depends(get_db),
    search: str | None = Query(default=None, description="Filter by detected object label."),
    prohibited_only: bool = Query(default=False, description="Only events with prohibited objects."),
    min_score: float = Query(default=0.0, ge=0.0, le=1.0),
    sort_by: str = Query(default="start_time"),
    order: str = Query(default="asc", pattern="^(asc|desc)$"),
) -> list[EventRead]:
    """Return the searchable, filterable, sortable event log for a video."""
    stmt = (
        select(Event)
        .where(Event.video_id == video.id)
        .options(selectinload(Event.rois), selectinload(Event.detections))
    )

    if search:
        stmt = stmt.where(Event.objects.ilike(f"%{search.strip()}%"))
    if min_score > 0:
        stmt = stmt.where(Event.motion_score >= min_score)

    column = _SORT_FIELDS.get(sort_by, Event.start_time)
    stmt = stmt.order_by(column.desc() if order == "desc" else column.asc())

    events = list(db.execute(stmt).scalars().all())
    if prohibited_only:
        events = [e for e in events if any(d.prohibited for d in e.detections)]

    return [EventRead.model_validate(e) for e in events]
