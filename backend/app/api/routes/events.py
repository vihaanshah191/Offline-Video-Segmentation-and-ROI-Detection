"""Event log endpoints with search, filter, sort and pagination."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select
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


@router.get(
    "/events/{video_id}",
    response_model=list[EventRead],
    summary="Searchable, filterable, sortable, paginated event log",
    response_description=(
        "A page of events. Total/limit/offset are additionally carried in "
        "X-Total-Count / X-Limit / X-Offset response headers."
    ),
)
def list_events(
    response: Response,
    video: Video = Depends(get_video_or_404),
    db: Session = Depends(get_db),
    search: str | None = Query(default=None, description="Filter by detected object label."),
    prohibited_only: bool = Query(default=False, description="Only events with prohibited objects."),
    min_score: float = Query(default=0.0, ge=0.0, le=1.0, description="Minimum normalized motion score."),
    sort_by: str = Query(
        default="start_time",
        description=f"One of: {', '.join(_SORT_FIELDS)}.",
    ),
    order: str = Query(default="asc", pattern="^(asc|desc)$"),
    limit: int = Query(default=200, ge=1, le=1000, description="Max events to return."),
    offset: int = Query(default=0, ge=0, description="Number of events to skip."),
) -> list[EventRead]:
    """Return the searchable, filterable, sortable, paginated event log for a video.

    Pagination is additive and non-breaking: the response body is still a
    plain JSON array; paging metadata is exposed via response headers only,
    so existing clients (which necessarily received at most a bounded number
    of events before pagination existed) are unaffected.

    Note: ``prohibited_only`` is applied in Python after the DB query (it
    depends on the related ``detections`` collection, not a column that can
    be filtered/paginated at the SQL level without a join+distinct), so the
    returned page may contain fewer than ``limit`` items when this filter is
    combined with pagination on a video with sparse prohibited-object hits.
    This is documented behaviour, not a bug — see ``docs/API.md``.
    """
    stmt = (
        select(Event)
        .where(Event.video_id == video.id)
        .options(selectinload(Event.rois), selectinload(Event.detections))
    )

    if search:
        stmt = stmt.where(Event.objects.ilike(f"%{search.strip()}%"))
    if min_score > 0:
        stmt = stmt.where(Event.motion_score >= min_score)

    total = int(db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one())

    column = _SORT_FIELDS.get(sort_by, Event.start_time)
    stmt = stmt.order_by(column.desc() if order == "desc" else column.asc())
    stmt = stmt.limit(limit).offset(offset)

    events = list(db.execute(stmt).scalars().all())
    if prohibited_only:
        events = [e for e in events if any(d.prohibited for d in e.detections)]

    response.headers["X-Total-Count"] = str(total)
    response.headers["X-Limit"] = str(limit)
    response.headers["X-Offset"] = str(offset)
    return [EventRead.model_validate(e) for e in events]
