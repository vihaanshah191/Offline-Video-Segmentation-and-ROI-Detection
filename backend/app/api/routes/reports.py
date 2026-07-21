"""Report export endpoints (CSV event log and PDF investigation report)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import get_video_or_404
from app.database.session import get_db
from app.models.video import Video
from app.services.report import build_pdf_report, events_to_csv

router = APIRouter(tags=["reports"])


@router.get("/report/{video_id}/csv")
def export_csv(
    video: Video = Depends(get_video_or_404),
    db: Session = Depends(get_db),
) -> Response:
    """Export the event log as a CSV file."""
    csv_data = events_to_csv(db, video)
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="events_video{video.id}.csv"'
        },
    )


@router.get("/report/{video_id}/pdf")
def export_pdf(
    video: Video = Depends(get_video_or_404),
    db: Session = Depends(get_db),
) -> Response:
    """Export a full PDF investigation report."""
    try:
        pdf_bytes = build_pdf_report(db, video)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc)
        ) from exc
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="report_video{video.id}.pdf"'
        },
    )
