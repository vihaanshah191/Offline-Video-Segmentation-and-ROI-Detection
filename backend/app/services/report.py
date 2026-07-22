"""Investigation report generation: CSV event export and PDF summary report."""
from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging_config import get_logger
from app.models.video import Video
from app.schemas.analytics import VideoAnalytics
from app.services.analytics import (
    _events_for,  # internal helper reuse
    compute_analytics,
    compute_timeline,
)
from app.utils.severity import compute_severity

logger = get_logger(__name__)


def _executive_summary(video: Video, analytics: VideoAnalytics) -> str:
    """A short, judge/investigator-readable prose summary of the findings."""
    coverage_pct = analytics.motion_coverage * 100
    sentences = [
        f"This report covers an offline analysis of '{video.original_name}' "
        f"({video.duration:.0f}s at {video.width}x{video.height}, {video.fps:.0f} fps), "
        f"processed with the '{video.motion_algorithm or 'n/a'}' motion algorithm."
    ]
    sentences.append(
        f"{analytics.total_events} motion event(s) were detected, covering "
        f"{coverage_pct:.1f}% of the recording's duration "
        f"({analytics.total_motion_duration:.1f}s total)."
    )
    if analytics.total_detections > 0:
        sentences.append(
            f"Object detection identified {analytics.total_detections} detection(s) "
            f"across {len(analytics.object_counts)} distinct object type(s)"
            + (f", most frequently '{analytics.top_object}'." if analytics.top_object else ".")
        )
    else:
        sentences.append("Object detection was not enabled, or found no relevant objects, for this run.")
    if analytics.prohibited_detections > 0:
        sentences.append(
            f"{analytics.prohibited_detections} detection(s) were flagged as potentially "
            "prohibited items and warrant manual review (see the Event Log)."
        )
    else:
        sentences.append("No detections were flagged as prohibited items.")
    return " ".join(sentences)


def _recommendations(analytics: VideoAnalytics) -> list[str]:
    """Dynamically generated next-step suggestions based on what was found —
    never a static/canned list, so the report doesn't overclaim."""
    recs: list[str] = []
    if analytics.prohibited_detections > 0:
        recs.append(
            "Manually review every event flagged with a prohibited-item detection before "
            "taking any action — automated detections (especially heuristic ones, marked "
            "in the Event Log) are a screening aid, not a final determination."
        )
    if analytics.motion_coverage > 0.5:
        recs.append(
            "Motion covers more than half of the recording; consider raising the motion "
            "sensitivity threshold in Settings for future analyses of similar footage to "
            "reduce noise."
        )
    if analytics.total_events == 0:
        recs.append(
            "No motion events were detected. If activity was expected, verify the motion "
            "sensitivity threshold and camera framing before concluding the period was quiet."
        )
    if not recs:
        recs.append("No specific follow-up actions are indicated by this analysis.")
    return recs


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
    """Generate a professional PDF investigation report and return its bytes.

    Sections: title, executive summary, system info, video metadata,
    summary statistics, a motion-over-time chart, the motion heatmap (if
    generated), a snapshot of the most significant event, detected-objects
    breakdown, the full event log, recommendations, and a raw
    processing-stats appendix.

    Uses ReportLab (including its bundled ``reportlab.graphics`` charting —
    no separate plotting library needed). Raises ``RuntimeError`` if
    ReportLab is unavailable so the caller can return a clear 501 response.
    """
    try:
        from reportlab.graphics.charts.linecharts import HorizontalLineChart
        from reportlab.graphics.shapes import Drawing, String
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            Image,
            PageBreak,
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
    timeline = compute_timeline(db, video, max_points=60)
    processing_stats: dict = {}
    if video.processing_stats:
        try:
            processing_stats = json.loads(video.processing_stats)
        except json.JSONDecodeError:
            processing_stats = {}

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, title=f"Report – {video.original_name}")
    styles = getSampleStyleSheet()
    body_style = styles["BodyText"]
    story: list = []

    def _section(title: str) -> None:
        story.append(Spacer(1, 4 * mm))
        story.append(Paragraph(title, styles["Heading2"]))

    def _plain_table(rows: list[list[str]], col_widths: list[float]) -> Table:
        table = Table(rows, colWidths=col_widths)
        table.setStyle(
            TableStyle(
                [
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#334155")),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        return table

    # ------------------------------------------------------------- title
    story.append(Paragraph("Video Surveillance Investigation Report", styles["Title"]))
    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    story.append(Paragraph(f"Generated {generated}", styles["Italic"]))
    story.append(Spacer(1, 6 * mm))

    # -------------------------------------------------- executive summary
    _section("Executive Summary")
    story.append(Paragraph(_executive_summary(video, analytics), body_style))

    # -------------------------------------------------------- system info
    _section("System Information")
    system_rows = [
        ["Motion algorithm", video.motion_algorithm or "n/a"],
        ["YOLO model", settings.custom_yolo_model_path or settings.yolo_model],
        ["Inference device", settings.yolo_device],
        ["Task backend", settings.task_backend],
        [
            "Processing time",
            f"{processing_stats.get('total_pipeline_seconds', 0):.1f} s"
            if processing_stats
            else "n/a",
        ],
        [
            "Motion detection throughput",
            f"{processing_stats.get('motion_detection_throughput_fps', 0):.1f} fps"
            if processing_stats
            else "n/a",
        ],
    ]
    story.append(_plain_table(system_rows, [60 * mm, 105 * mm]))

    # ------------------------------------------------------- video metadata
    _section("Video Metadata")
    meta_rows = [
        ["File", video.original_name],
        ["Resolution", f"{video.width}x{video.height}"],
        ["Duration", f"{video.duration:.1f} s"],
        ["FPS", f"{video.fps:.2f}"],
        ["File size", f"{video.size_bytes / (1024 * 1024):.2f} MB"],
    ]
    story.append(_plain_table(meta_rows, [45 * mm, 120 * mm]))

    # ------------------------------------------------------------- summary
    _section("Summary Statistics")
    summary_rows = [
        ["Total events", str(analytics.total_events)],
        ["Total motion duration", f"{analytics.total_motion_duration:.1f} s"],
        ["Motion coverage", f"{analytics.motion_coverage * 100:.1f} %"],
        ["Average motion score", f"{analytics.average_motion_score:.4f}"],
        ["Average event duration", f"{analytics.average_event_duration:.1f} s"],
        ["Peak activity time", f"{analytics.peak_activity_time:.1f} s"],
        ["Longest event", f"{analytics.longest_event_duration:.1f} s"],
        ["Total ROI area", f"{analytics.total_roi_area_pixels:,} px²"],
        ["Objects detected", str(analytics.total_detections)],
        ["Prohibited detections", str(analytics.prohibited_detections)],
    ]
    story.append(_plain_table(summary_rows, [60 * mm, 105 * mm]))

    # ------------------------------------------------------- motion graph
    if timeline.points:
        _section("Motion Over Time")
        drawing = Drawing(460, 160)
        chart = HorizontalLineChart()
        chart.x, chart.y = 30, 20
        chart.width, chart.height = 410, 120
        scores = [p.motion_score * 100 for p in timeline.points]
        chart.data = [scores]
        chart.lines[0].strokeColor = colors.HexColor("#0ea5e9")
        chart.lines[0].strokeWidth = 1.2
        chart.categoryAxis.visible = False
        chart.valueAxis.valueMin = 0
        chart.valueAxis.valueMax = max(1, max(scores))
        chart.valueAxis.labels.fontSize = 7
        drawing.add(chart)
        drawing.add(String(30, 145, "Motion intensity (%) over the recording", fontSize=8))
        story.append(drawing)

    # --------------------------------------------------------------- heatmap
    if video.heatmap_path and Path(video.heatmap_path).exists():
        _section("Motion Heatmap")
        story.append(Paragraph("Accumulated motion intensity across the entire recording.", body_style))
        story.append(Image(video.heatmap_path, width=140 * mm, height=140 * mm * video.height / max(1, video.width)))

    # ------------------------------------------------------- event snapshot
    significant_event = max(events, key=lambda e: e.peak_motion_score, default=None)
    if significant_event and significant_event.thumbnail_path and Path(significant_event.thumbnail_path).exists():
        _section("Most Significant Event Snapshot")
        story.append(
            Paragraph(
                f"Event #{significant_event.id} at {significant_event.start_time:.1f}s "
                f"(peak motion score {significant_event.peak_motion_score:.3f}).",
                body_style,
            )
        )
        story.append(
            Image(
                significant_event.thumbnail_path,
                width=100 * mm,
                height=100 * mm * video.height / max(1, video.width),
            )
        )

    # ------------------------------------------------------- detected objects
    if analytics.object_counts:
        _section("Detected Objects")
        obj_header = ["Label", "Count", "Prohibited"]
        obj_rows = [obj_header] + [
            [oc.label, str(oc.count), "Yes" if oc.prohibited else "No"] for oc in analytics.object_counts
        ]
        obj_table = Table(obj_rows, repeatRows=1, colWidths=[70 * mm, 40 * mm, 40 * mm])
        obj_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
                ]
            )
        )
        story.append(obj_table)

    # ------------------------------------------------------------ event log
    story.append(PageBreak())
    _section("Event Log")
    header = ["ID", "Start", "End", "Dur", "Motion", "Conf", "Severity", "Objects"]
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
                compute_severity(event.peak_motion_score, event.detections),
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

    # --------------------------------------------------------- recommendations
    _section("Recommendations")
    for rec in _recommendations(analytics):
        story.append(Paragraph(f"• {rec}", body_style))

    # ---------------------------------------------------------------- appendix
    if processing_stats:
        story.append(PageBreak())
        _section("Appendix: Processing Statistics")
        appendix_rows = [[str(k), str(v)] for k, v in processing_stats.items()]
        story.append(_plain_table(appendix_rows, [80 * mm, 85 * mm]))

    doc.build(story)
    return buffer.getvalue()
