"""End-to-end offline analysis pipeline.

Orchestrates the full flow for a single uploaded video:

    Extract frames -> Motion detection -> Noise filtering -> ROI detection
    -> Object detection (YOLO, batched) -> Merge events (smoothing +
    hysteresis) -> Generate clips -> Heatmap -> Timeline data -> Persist.

Two concurrency/performance techniques keep this viable for multi-hour 1080p
recordings:

* A background **frame-reader thread** decodes frames and pushes only the
  sampled ones onto a bounded queue, overlapping video decode I/O with CV
  processing in the main thread (OpenCV's C++ core releases the GIL for both,
  so this achieves genuine wall-clock overlap despite the interpreter's GIL).
  The queue is bounded (``frame_buffer_size``), so memory use cannot grow
  unbounded if processing falls behind decoding.
* The heavy motion-analysis pass decodes the video exactly once. A light
  second pass only random-seeks a handful of representative frames per
  detected segment for object detection, clip cutting and thumbnails.
"""
from __future__ import annotations

import json
import queue
import threading
from bisect import bisect_left, bisect_right
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

import cv2
import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.config import settings as global_settings
from app.core.logging_config import LogTimer, get_logger
from app.models.video import ROI, Detection, Event, Video, VideoStatus
from app.services.heatmap import HeatmapAccumulator
from app.services.motion_detection import AUTO, MotionDetector, select_best_algorithm
from app.services.object_detection import ObjectDetection, ObjectDetector
from app.services.roi_detection import ROIDetector
from app.services.segmentation import MotionSample, Segment, build_segments
from app.utils.geometry import Box, merge_boxes
from app.utils.video_io import cut_clip, extract_thumbnail

logger = get_logger(__name__)

ProgressCallback = Callable[[float, str], None]

# If more than this many CONSECUTIVE frames fail to decode/process, the video
# is treated as genuinely corrupt/unsupported (rather than having a handful of
# glitchy frames from a marginal codec) and analysis aborts with a clear error
# instead of silently producing a near-empty, misleading result.
MAX_CONSECUTIVE_FRAME_ERRORS = 30


class PipelineCancelled(Exception):
    """Raised internally when a user-requested cancellation is observed
    mid-run. Caught by :func:`app.workers.tasks.run_analysis`, which records
    ``VideoStatus.CANCELLED`` rather than treating this as a failure."""


@dataclass(slots=True)
class FrameSample:
    """Per-sampled-frame analysis record kept in memory during pass one."""

    time: float
    frame_index: int
    score: float
    roi_present: bool
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
    motion_hysteresis_ratio: float = 0.6
    motion_smoothing_window: int = 5
    roi_min_area_fraction: float = 0.0
    roi_max_raw_contours: int = 200
    adaptive_threshold: bool = True
    frame_buffer_size: int = 64
    object_detection_confidence: float | None = None
    object_detection_classes: list[str] | None = None

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
            motion_hysteresis_ratio=s.motion_hysteresis_ratio,
            motion_smoothing_window=s.motion_smoothing_window,
            roi_min_area_fraction=s.roi_min_area_fraction,
            roi_max_raw_contours=s.roi_max_raw_contours,
            frame_buffer_size=s.frame_buffer_size,
        )
        for key, value in overrides.items():
            if value is not None and hasattr(base, key):
                setattr(base, key, value)
        return base


class _FrameReaderThread:
    """Decodes video frames on a background thread, feeding a bounded queue.

    Only frames matching the sample step are enqueued (skipped frames are
    still decoded — OpenCV does not support cheap frame-skipping for most
    compressed codecs — but are discarded immediately without leaving the
    reader thread, so the consumer never pays Python-level overhead for them).

    The queue bound (``queue_size``) caps memory growth if the consumer (CV
    processing) falls behind the producer (decode), which is the concrete
    safeguard against unbounded memory use on very long recordings.
    """

    _SENTINEL = object()

    def __init__(self, video_path: str, step: int, queue_size: int) -> None:
        self.video_path = video_path
        self.step = max(1, step)
        self.frame_queue: queue.Queue = queue.Queue(maxsize=max(1, queue_size))
        self.error: Exception | None = None
        self.frames_decoded = 0
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, name="frame-reader", daemon=True)

    def start(self) -> _FrameReaderThread:
        self._thread.start()
        return self

    def stop(self) -> None:
        """Signal the producer to stop and unblock a pending queue ``put``.

        The consumer (``frames()``) is a generator abandoned mid-iteration
        whenever the pipeline exits its frame loop early (cancellation, or
        the too-many-corrupt-frames abort) — nothing calls ``.get()`` on the
        queue again. Without this, a producer blocked on ``put()`` (the
        common case: CV processing is normally slower than raw decode, so
        the bounded queue is usually full) would stay blocked for the rest
        of the process's life, leaking this thread and its open
        ``VideoCapture``. Call before ``join()`` on every exit path.
        """
        self._stop_event.set()

    def _run(self) -> None:
        cap = cv2.VideoCapture(self.video_path)
        try:
            if not cap.isOpened():
                self.error = ValueError(f"Cannot open video for analysis: {self.video_path}")
                return
            frame_index = 0
            while not self._stop_event.is_set():
                ok, frame = cap.read()
                if not ok or frame is None:
                    break
                self.frames_decoded += 1
                if frame_index % self.step == 0 and not self._put_until_stopped((frame_index, frame)):
                    break
                frame_index += 1
        except Exception as exc:  # noqa: BLE001 - surfaced to the consumer thread
            self.error = exc
        finally:
            cap.release()
            self._put_until_stopped(self._SENTINEL)

    def _put_until_stopped(self, item: object) -> bool:
        """Block on ``frame_queue.put`` but wake periodically to re-check ``_stop_event``.

        Returns False if ``stop()`` was called before the item could be enqueued.
        """
        while not self._stop_event.is_set():
            try:
                self.frame_queue.put(item, timeout=0.5)
                return True
            except queue.Full:
                continue
        return False

    def frames(self):
        """Yield ``(frame_index, frame)`` tuples until the reader is exhausted.

        Re-raises any decode-thread error in the *consumer* thread once the
        stream is exhausted, so pipeline error handling stays centralised.
        """
        while True:
            item = self.frame_queue.get()
            if item is self._SENTINEL:
                if self.error is not None:
                    raise self.error
                return
            yield item

    def join(self, timeout: float = 5.0) -> None:
        self._thread.join(timeout=timeout)


class AnalysisPipeline:
    """Runs the offline analysis for one video and persists the results."""

    def __init__(self, config: PipelineConfig, settings: Settings | None = None) -> None:
        self.config = config
        self.settings = settings or global_settings
        self.detector = ObjectDetector(
            enabled=config.enable_object_detection,
            confidence=config.object_detection_confidence,
            class_filter=config.object_detection_classes,
        )
        # Motion detector and ROI detector are constructed lazily inside run()
        # once the resolved (non-"auto") algorithm and frame resolution are
        # known.
        self.motion: MotionDetector | None = None
        self.roi: ROIDetector | None = None

    # ------------------------------------------------------------------ public
    def run(
        self,
        video: Video,
        db: Session,
        progress_cb: ProgressCallback | None = None,
    ) -> dict:
        """Execute the full pipeline for ``video`` and persist events.

        Returns a summary dict (counts + performance stats) for logging and
        for the ``Video.processing_stats`` column.
        """
        pipeline_timer = LogTimer(logger, "full_pipeline_run")
        with pipeline_timer:
            stats = self._run_inner(video, db, progress_cb or (lambda pct, msg: None))
        stats["total_pipeline_seconds"] = round(pipeline_timer.elapsed_seconds, 3)
        video.processing_stats = json.dumps(stats)
        db.commit()
        return stats

    @staticmethod
    def _check_cancelled(db: Session, video_id: int) -> None:
        """Raise :class:`PipelineCancelled` if the user requested cancellation.

        Python threads cannot be forcibly killed, so cancellation is
        cooperative: the API sets ``Video.cancel_requested`` on its own DB
        session/connection, and this thread polls for it. A plain column
        ``select`` (rather than touching the ORM-identity-mapped ``video``
        object already loaded in this session) is used so the read isn't
        served from a stale in-memory copy — it always reflects the latest
        committed value from the other session.
        """
        flag = db.execute(
            select(Video.cancel_requested).where(Video.id == video_id)
        ).scalar_one_or_none()
        if flag:
            raise PipelineCancelled(f"Analysis cancelled by user for video {video_id}")

    def _run_inner(self, video: Video, db: Session, report: ProgressCallback) -> dict:
        """The actual pipeline body, timed by :meth:`run`."""
        video_path = video.path
        fps = video.fps or 25.0
        total_frames = video.frame_count or 0
        width = video.width or 0
        height = video.height or 0
        if not width or not height or not fps:
            width, height, fps, total_frames = self._probe_fallback(
                video_path, width, height, fps, total_frames
            )

        resolved_algorithm = self._resolve_algorithm(video_path)
        self.motion = MotionDetector(
            algorithm=resolved_algorithm,
            min_area=self.config.min_motion_area,
            adaptive_threshold=self.config.adaptive_threshold,
            frame_width=width,
            frame_height=height,
        )
        self.roi = ROIDetector(
            min_area=self.config.min_motion_area,
            min_area_fraction=self.config.roi_min_area_fraction,
            merge_iou=self.config.roi_merge_iou,
            max_raw_contours=self.config.roi_max_raw_contours,
        )

        step = max(1, self.config.frame_sample_step)
        heatmap = HeatmapAccumulator(height=height, width=width)
        samples: list[FrameSample] = []
        frame_errors = 0
        consecutive_errors = 0

        report(2.0, f"Extracting frames and detecting motion ({resolved_algorithm})")
        motion_timer = LogTimer(logger, "motion_detection", item_count=None)
        with motion_timer:
            reader = _FrameReaderThread(video_path, step, self.config.frame_buffer_size).start()
            processed = 0
            try:
                for frame_index, frame in reader.frames():
                    try:
                        result = self.motion.process(frame)
                        heatmap.add(result.mask, frame)
                        roi_boxes = self.roi.detect(result.mask)
                        roi_present = bool(roi_boxes) and not result.is_warming_up

                        samples.append(
                            FrameSample(
                                time=frame_index / fps,
                                frame_index=frame_index,
                                score=result.score,
                                roi_present=roi_present,
                                rois=[b.as_tuple() for b in roi_boxes],
                            )
                        )
                        consecutive_errors = 0
                    except Exception as exc:  # noqa: BLE001 - one bad frame must not fail the run
                        frame_errors += 1
                        consecutive_errors += 1
                        logger.warning(
                            "Skipping unreadable/corrupt frame %d: %s", frame_index, exc
                        )
                        if consecutive_errors > MAX_CONSECUTIVE_FRAME_ERRORS:
                            raise ValueError(
                                f"Aborting analysis: {consecutive_errors} consecutive frames "
                                "failed to process — the video is likely corrupt or uses an "
                                "unsupported codec."
                            ) from exc

                    processed += 1
                    if processed % 50 == 0:
                        self._check_cancelled(db, video.id)
                        if total_frames:
                            pct = 2.0 + 68.0 * (frame_index / max(1, total_frames))
                            report(min(70.0, pct), "Analysing motion")
            finally:
                # stop() unblocks a reader still stuck in put() when this
                # loop was abandoned early (cancellation / corrupt-frame
                # abort); harmless no-op if the reader already finished.
                reader.stop()
                reader.join()
        motion_timer_stats = {
            "elapsed_seconds": round(motion_timer.elapsed_seconds, 3),
            "frames_processed": processed,
            "frames_with_errors": frame_errors,
            "throughput_fps": round(processed / motion_timer.elapsed_seconds, 2)
            if motion_timer.elapsed_seconds > 0
            else 0.0,
        }
        logger.info("Motion detection stats for video %s: %s", video.id, motion_timer_stats)

        report(72.0, "Segmenting activity")
        with LogTimer(logger, "segmentation", item_count=len(samples)):
            motion_samples = [
                MotionSample(time=s.time, score=s.score, roi_present=s.roi_present) for s in samples
            ]
            segments = build_segments(
                motion_samples,
                enter_threshold=self.config.motion_threshold,
                exit_threshold=self.config.motion_threshold * self.config.motion_hysteresis_ratio,
                smoothing_window=self.config.motion_smoothing_window,
                merge_gap_sec=self.config.segment_merge_gap_sec,
                min_duration_sec=self.config.min_segment_duration_sec,
            )
        logger.info(
            "Video %s: %d segments from %d samples (algorithm=%s)",
            video.id,
            len(segments),
            len(samples),
            resolved_algorithm,
        )

        report(75.0, "Generating heatmap")
        heatmap_path = self._save_heatmap(video, heatmap)
        video.heatmap_path = heatmap_path

        # Save a video-level thumbnail from the busiest moment (or start).
        thumb_time = self._peak_time(samples) or 0.0
        video_thumb = self.settings.thumbnails_dir / f"video_{video.id}.jpg"
        if extract_thumbnail(video_path, video_thumb, timestamp=thumb_time):
            video.thumbnail_path = str(video_thumb)

        self._check_cancelled(db, video.id)
        report(78.0, "Building clips and detecting objects")
        with LogTimer(logger, "event_materialisation", item_count=len(segments), item_label="events"):
            self._materialise_events(video, db, samples, segments, width, height, report)

        video.status = VideoStatus.COMPLETED
        video.progress = 100.0
        video.status_message = "Analysis complete"
        video.motion_algorithm = resolved_algorithm
        video.analyzed_at = datetime.now(UTC)
        db.commit()

        cache_stats = self.detector.cache_stats()
        return {
            "events": len(segments),
            "samples": len(samples),
            "frames_processed": processed,
            "frames_with_errors": frame_errors,
            "object_detection": self.detector.available,
            "resolved_motion_algorithm": resolved_algorithm,
            "motion_detection_seconds": motion_timer_stats["elapsed_seconds"],
            "motion_detection_throughput_fps": motion_timer_stats["throughput_fps"],
            "object_detection_cache_hits": cache_stats["cache_hits"],
            "object_detection_cache_misses": cache_stats["cache_misses"],
        }

    # ----------------------------------------------------------------- helpers
    def _resolve_algorithm(self, video_path: str) -> str:
        """Resolve the ``auto`` pseudo-algorithm to a concrete one, if requested."""
        if self.config.motion_algorithm != AUTO:
            return self.config.motion_algorithm
        with LogTimer(logger, "auto_algorithm_selection"):
            return select_best_algorithm(video_path)

    def _probe_fallback(
        self, video_path: str, width: int, height: int, fps: float, total_frames: int
    ) -> tuple[int, int, float, int]:
        """Fallback metadata probe used only if the DB row is missing values."""
        cap = cv2.VideoCapture(video_path)
        try:
            if cap.isOpened():
                width = width or int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = height or int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fps = fps or (cap.get(cv2.CAP_PROP_FPS) or 25.0)
                total_frames = total_frames or int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        finally:
            cap.release()
        return width, height, fps, total_frames

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
        # Samples are chronologically ordered; binary-search the slice for
        # each segment instead of a full linear scan per segment. This turns
        # O(events x samples) into O(events x log(samples)) — meaningful on a
        # multi-hour recording with hundreds of segments and tens of
        # thousands of samples.
        sample_times = [s.time for s in samples]

        for idx, seg in enumerate(segments):
            lo = bisect_left(sample_times, seg.start_time)
            hi = bisect_right(sample_times, seg.end_time)
            seg_samples = samples[lo:hi]

            merged_rois = self._aggregate_rois(seg_samples, width, height)
            peak_sample = max(seg_samples, key=lambda s: s.score, default=None)

            event = Event(
                video_id=video.id,
                start_time=round(seg.start_time, 3),
                end_time=round(seg.end_time, 3),
                duration=round(seg.duration, 3),
                motion_score=round(seg.avg_normalized_score, 5),
                peak_motion_score=round(seg.peak_normalized_score, 5),
                confidence=round(min(1.0, seg.avg_normalized_score * 1.2), 4),
            )
            db.add(event)
            db.flush()  # obtain event.id

            for box in merged_rois:
                x, y, w, h = box
                event.rois.append(
                    ROI(x=x, y=y, w=w, h=h, confidence=round(seg.peak_normalized_score, 4))
                )

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
                        heuristic=det.heuristic,
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

            # ---- per-event heatmap -------------------------------------------
            event.heatmap_path = self._generate_event_heatmap(event.id, seg_samples, width, height)

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
        """Run batched YOLO inference on up to three frames spanning the segment.

        All representative frames for this segment are collected first and
        passed to :meth:`ObjectDetector.detect_batch` in a single call, rather
        than three sequential single-frame calls — this amortises inference
        overhead (Python dispatch, and on GPU, kernel-launch latency) across
        the batch instead of paying it three times.
        """
        if not self.detector.available:
            return []

        times = sorted(
            {
                seg.start_time,
                (peak.time if peak else (seg.start_time + seg.end_time) / 2),
                seg.end_time,
            }
        )
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return []
        frames: list[np.ndarray] = []
        try:
            for t in times:
                cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, t) * 1000.0)
                ok, frame = cap.read()
                if ok and frame is not None:
                    frames.append(frame)
        finally:
            cap.release()

        if not frames:
            return []

        best: dict[str, ObjectDetection] = {}
        for frame_detections in self.detector.detect_batch(frames):
            for det in frame_detections:
                prev = best.get(det.label)
                if prev is None or det.confidence > prev.confidence:
                    best[det.label] = det
        return list(best.values())

    def _save_heatmap(self, video: Video, heatmap: HeatmapAccumulator) -> str | None:
        path = self.settings.heatmaps_dir / f"video_{video.id}.png"
        if heatmap.save(path):
            return str(path)
        return None

    def _generate_event_heatmap(
        self, event_id: int, seg_samples: list[FrameSample], width: int, height: int
    ) -> str | None:
        """Render a per-event motion heatmap (same JET-colormap style as the
        whole-video one) from this event's own already-computed ROI boxes.

        Deliberately reuses pass-one's ROI data rather than re-decoding and
        re-running motion detection over the event's frame range a second
        time — cheap, and consistent with the per-event object-detection
        pass already only touching a handful of representative frames
        rather than every frame in the segment.
        """
        if not seg_samples:
            return None
        accumulator = HeatmapAccumulator(height=height, width=width)
        for sample in seg_samples:
            if not sample.rois:
                continue
            mask = np.zeros((height, width), dtype=np.uint8)
            for x, y, w, h in sample.rois:
                cv2.rectangle(mask, (x, y), (x + w, y + h), 255, thickness=-1)
            accumulator.add(mask)
        if not accumulator.has_data:
            return None
        path = self.settings.heatmaps_dir / f"event_{event_id}.png"
        return str(path) if accumulator.save(path) else None

    @staticmethod
    def _peak_time(samples: list[FrameSample]) -> float | None:
        if not samples:
            return None
        return max(samples, key=lambda s: s.score).time
