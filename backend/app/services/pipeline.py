"""End-to-end offline analysis pipeline.

Orchestrates the full flow for a single uploaded video:

    Extract frames -> Motion detection -> Noise filtering -> ROI detection
    -> Object detection (YOLO) -> Merge events -> Generate clips -> Heatmap
    -> Timeline data -> Persist to database.

The pipeline is deliberately single-pass for the heavy motion analysis (one
decode of the video) and performs a light second pass that only seeks to a few
representative frames per segment for object detection, clip cutting and
thumbnails — keeping it viable for multi-hour 1080p recordings.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

import cv2
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.config import settings as global_settings
from app.core.logging_config import get_logger
from app.models.video import ROI, Detection, Event, Video, VideoStatus
from app.services.heatmap import HeatmapAccumulator
from app.services.motion_detection import MotionDetector
from app.services.object_detection import ObjectDetection, ObjectDetector
from app.services.roi_detection import ROIDetector
from app.services.segmentation import MotionSample, Segment, build_segments
from app.utils.geometry import Box, merge_boxes
from app.utils.video_io import cut_clip, extract_thumbnail

logger = get_logger(__name__)

ProgressCallback = Callable[[float, str], None]


@dataclass(slots=True)
class FrameSample:
    """Per-sampled-frame analysis record kept in memory during pass one."""

    time: float
    frame_index: int
    score: float
    active: bool
    rois: list[Box] = field(default_factory=list)


@dataclass(slots=True)
class PipelineConfig:
    """Resolved, per-run configuration (overrides global settings)."""

    motion_algorithm: str
    frame_sample_step: int
    min_motion_area: int
    motion_threshold: float
    segment_merge_gap_sec: float
    min_segment_duration_sec: float
    roi_merge_iou: float
    enable_object_detection: bool

    @classmethod
    def from_settings(cls, s: Settings, **overrides) -> PipelineConfig:
        base = cls(
            motion_algorithm=s.default_motion_algorithm,
            frame_sample_step=s.frame_sample_step,
            min_motion_area=s.min_motion_area,
            motion_threshold=s.motion_threshold,
            segment_merge_gap_sec=s.segment_merge_gap_sec,
            min_segment_duration_sec=s.min_segment_duration_sec,
            roi_merge_iou=s.roi_merge_iou,
            enable_object_detection=s.enable_object_detection,
        )
        for key, value in overrides.items():
            if value is not None and hasattr(base, key):
                setattr(base, key, value)
        return base


class AnalysisPipeline:
    """Runs the offline analysis for one video and persists the results."""

    def __init__(self, config: PipelineConfig, settings: Settings | None = None) -> None:
        self.config = config
        self.settings = settings or global_settings
        self.motion = MotionDetector(
            algorithm=config.motion_algorithm, min_area=config.min_motion_area
        )
        self.roi = ROIDetector(
            min_area=config.min_motion_area, merge_iou=config.roi_merge_iou
        )
        self.detector = ObjectDetector(enabled=config.enable_object_detection)

    # ------------------------------------------------------------------ public
    def run(
        self,
        video: Video,
        db: Session,
        progress_cb: ProgressCallback | None = None,
    ) -> dict:
        """Execute the full pipeline for ``video`` and persist events.

        Returns a small summary dict (counts) for logging/telemetry.
        """
        report = progress_cb or (lambda pct, msg: None)
        video_path = video.path

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Cannot open video for analysis: {video_path}")

        fps = video.fps or (cap.get(cv2.CAP_PROP_FPS) or 25.0)
        total_frames = video.frame_count or int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
        width = video.width or int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = video.height or int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        step = max(1, self.config.frame_sample_step)

        heatmap = HeatmapAccumulator(height=height, width=width)
        samples: list[FrameSample] = []

        report(2.0, "Extracting frames and detecting motion")
        frame_index = 0
        processed = 0
        try:
            while True:
                ok, frame = cap.read()
                if not ok or frame is None:
                    break
                if frame_index % step != 0:
                    frame_index += 1
                    continue

                result = self.motion.process(frame)
                heatmap.add(result.mask, frame)
                roi_boxes = self.roi.detect(result.mask)
                active = result.score >= self.config.motion_threshold and bool(roi_boxes)

                samples.append(
                    FrameSample(
                        time=frame_index / fps,
                        frame_index=frame_index,
                        score=result.score,
                        active=active,
                        rois=[b.as_tuple() for b in roi_boxes],
                    )
                )

                processed += 1
                frame_index += 1
                if total_frames and processed % 50 == 0:
                    pct = 2.0 + 68.0 * (frame_index / max(1, total_frames))
                    report(min(70.0, pct), "Analysing motion")
        finally:
            cap.release()

        report(72.0, "Segmenting activity")
        motion_samples = [
            MotionSample(time=s.time, score=s.score, active=s.active) for s in samples
        ]
        segments = build_segments(
            motion_samples,
            merge_gap_sec=self.config.segment_merge_gap_sec,
            min_duration_sec=self.config.min_segment_duration_sec,
        )
        logger.info("Video %s: %d segments from %d samples", video.id, len(segments), len(samples))

        report(75.0, "Generating heatmap")
        heatmap_path = self._save_heatmap(video, heatmap)
        video.heatmap_path = heatmap_path

        # Save a video-level thumbnail from the busiest moment (or start).
        thumb_time = self._peak_time(samples) or 0.0
        video_thumb = self.settings.thumbnails_dir / f"video_{video.id}.jpg"
        if extract_thumbnail(video_path, video_thumb, timestamp=thumb_time):
            video.thumbnail_path = str(video_thumb)

        report(78.0, "Building clips and detecting objects")
        self._materialise_events(video, db, samples, segments, width, height, report)

        video.status = VideoStatus.COMPLETED
        video.progress = 100.0
        video.status_message = "Analysis complete"
        video.motion_algorithm = self.config.motion_algorithm
        video.analyzed_at = datetime.now(UTC)
        db.commit()

        return {
            "events": len(segments),
            "samples": len(samples),
            "object_detection": self.detector.available,
        }

    # ----------------------------------------------------------------- helpers
    def _materialise_events(
        self,
        video: Video,
        db: Session,
        samples: list[FrameSample],
        segments: list[Segment],
        width: int,
        height: int,
        report: ProgressCallback,
    ) -> None:
        """Create Event/ROI/Detection rows plus clips and thumbnails."""
        total = max(1, len(segments))
        for idx, seg in enumerate(segments):
            seg_samples = [
                s for s in samples if seg.start_time <= s.time <= seg.end_time
            ]
            merged_rois = self._aggregate_rois(seg_samples, width, height)
            peak_sample = max(seg_samples, key=lambda s: s.score, default=None)

            event = Event(
                video_id=video.id,
                start_time=round(seg.start_time, 3),
                end_time=round(seg.end_time, 3),
                duration=round(seg.duration, 3),
                motion_score=round(seg.avg_score, 5),
                peak_motion_score=round(seg.peak_score, 5),
                confidence=round(min(1.0, seg.avg_score * 8), 4),
            )
            db.add(event)
            db.flush()  # obtain event.id

            for box in merged_rois:
                x, y, w, h = box
                event.rois.append(ROI(x=x, y=y, w=w, h=h, confidence=round(seg.peak_score, 4)))

            # ---- object detection on a few representative frames -------------
            detections = self._detect_for_segment(video.path, seg, peak_sample)
            labels: list[str] = []
            for det in detections:
                event.detections.append(
                    Detection(
                        label=det.label,
                        confidence=det.confidence,
                        timestamp=round(seg.start_time, 3),
                        prohibited=det.prohibited,
                        x=det.x,
                        y=det.y,
                        w=det.w,
                        h=det.h,
                    )
                )
                labels.append(det.label)
            event.objects = ",".join(sorted(set(labels)))

            # ---- clip + thumbnail -------------------------------------------
            clip_path = self.settings.clips_dir / f"video_{video.id}_event_{event.id}.mp4"
            if cut_clip(video.path, clip_path, seg.start_time, seg.end_time):
                event.clip_path = str(clip_path)
            thumb_path = self.settings.thumbnails_dir / f"event_{event.id}.jpg"
            thumb_time = peak_sample.time if peak_sample else seg.start_time
            if extract_thumbnail(video.path, thumb_path, timestamp=thumb_time):
                event.thumbnail_path = str(thumb_path)

            db.commit()
            report(
                78.0 + 21.0 * ((idx + 1) / total),
                f"Processed event {idx + 1}/{total}",
            )

    def _aggregate_rois(
        self, seg_samples: list[FrameSample], width: int, height: int
    ) -> list[Box]:
        """Merge every ROI box observed across a segment into stable regions."""
        all_boxes: list[Box] = []
        for sample in seg_samples:
            all_boxes.extend(sample.rois)
        if not all_boxes:
            return []
        return merge_boxes(all_boxes, iou_threshold=self.config.roi_merge_iou)

    def _detect_for_segment(
        self, video_path: str, seg: Segment, peak: FrameSample | None
    ) -> list[ObjectDetection]:
        """Run YOLO on up to three frames spanning the segment; dedupe by label."""
        if not self.detector.available:
            return []

        times = sorted(
            {
                seg.start_time,
                (peak.time if peak else (seg.start_time + seg.end_time) / 2),
                seg.end_time,
            }
        )
        best: dict[str, ObjectDetection] = {}
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return []
        try:
            for t in times:
                cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, t) * 1000.0)
                ok, frame = cap.read()
                if not ok or frame is None:
                    continue
                for det in self.detector.detect(frame):
                    prev = best.get(det.label)
                    if prev is None or det.confidence > prev.confidence:
                        best[det.label] = det
        finally:
            cap.release()
        return list(best.values())

    def _save_heatmap(self, video: Video, heatmap: HeatmapAccumulator) -> str | None:
        path = self.settings.heatmaps_dir / f"video_{video.id}.png"
        if heatmap.save(path):
            return str(path)
        return None

    @staticmethod
    def _peak_time(samples: list[FrameSample]) -> float | None:
        if not samples:
            return None
        return max(samples, key=lambda s: s.score).time
