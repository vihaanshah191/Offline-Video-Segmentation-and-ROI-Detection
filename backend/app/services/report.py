"""Investigation report generation: CSV event export and PDF summary report."""
from __future__ import annotations

import csv
import io
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.models.video import Video
from app.services.analytics import (
    _events_for,  # internal helper reuse
    compute_analytics,
)

logger = get_logger(__name__)


def events_to_csv(db: Session, video: Video) -> str:
    """Serialise a video's events to a CSV string."""
    events = _events_for(db, video.id)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "event_id",
            "start_time_s",
            "end_time_s",
            "duration_s",
            "motion_score",
            "peak_motion_score",
            "confidence",
            "objects",
            "prohibited_objects",
            "roi_count",
            "clip_path",
        ]
    )
    for event in events:
        prohibited = sorted({d.label for d in event.detections if d.prohibited})
        writer.writerow(
            [
                event.id,
                f"{event.start_time:.3f}",
                f"{event.end_time:.3f}",
                f"{event.duration:.3f}",
                f"{event.motion_score:.5f}",
                f"{event.peak_motion_score:.5f}",
                f"{event.confidence:.4f}",
                event.objects,
                ",".join(prohibited),
                len(event.rois),
                event.clip_path or "",
            ]
        )
    return buffer.getvalue()


def build_pdf_report(db: Session, video: Video) -> bytes:
    """Generate a PDF investigation report and return its bytes.

    Uses ReportLab. Raises ``RuntimeError`` if ReportLab is unavailable so the
    caller can return a clear 501 response.
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError as exc:  # pragma: no cover - depends on optional dep
        raise RuntimeError("ReportLab is not installed; cannot generate PDF") from exc

    analytics = compute_analytics(db, video)
    events = _events_for(db, video.id)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, title=f"Report – {video.original_name}")
    styles = getSampleStyleSheet()
    story: list = []

    story.append(Paragraph("Video Surveillance Investigation Report", styles["Title"]))
    story.append(Spacer(1, 6 * mm))

    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    meta_rows = [
        ["File", video.original_name],
        ["Resolution", f"{video.width}x{video.height}"],
        ["Duration", f"{video.duration:.1f} s"],
        ["FPS", f"{video.fps:.2f}"],
        ["Motion algorithm", video.motion_algorithm or "n/a"],
        ["Generated", generated],
    ]
    meta_table = Table(meta_rows, colWidths=[45 * mm, 120 * mm])
    meta_table.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.grey),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(meta_table)
    story.append(Spacer(1, 6 * mm))

    story.append(Paragraph("Summary", styles["Heading2"]))
    summary_rows = [
        ["Total events", str(analytics.total_events)],
        ["Total motion duration", f"{analytics.total_motion_duration:.1f} s"],
        ["Motion coverage", f"{analytics.motion_coverage * 100:.1f} %"],
        ["Average motion score", f"{analytics.average_motion_score:.4f}"],
        ["Peak activity time", f"{analytics.peak_activity_time:.1f} s"],
        ["Longest event", f"{analytics.longest_event_duration:.1f} s"],
        ["Objects detected", str(analytics.total_detections)],
        ["Prohibited detections", str(analytics.prohibited_detections)],
    ]
    summary_table = Table(summary_rows, colWidths=[60 * mm, 105 * mm])
    summary_table.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#334155")),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(summary_table)
    story.append(Spacer(1, 6 * mm))

    story.append(Paragraph("Event Log", styles["Heading2"]))
    header = ["ID", "Start", "End", "Dur", "Motion", "Conf", "Objects"]
    table_data = [header]
    for event in events:
        table_data.append(
            [
                str(event.id),
                f"{event.start_time:.1f}",
                f"{event.end_time:.1f}",
                f"{event.duration:.1f}",
                f"{event.motion_score:.3f}",
                f"{event.confidence:.2f}",
                event.objects or "-",
            ]
        )
    event_table = Table(table_data, repeatRows=1)
    event_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(event_table)

    doc.build(story)
    return buffer.getvalue()
