"""Video segmentation from a per-frame motion-score timeline.

Converts a chronological list of motion samples into discrete activity segments
("events"). A segment opens when motion crosses the activity threshold and
closes after a configurable gap of no motion. Short gaps within a burst are
bridged; segments shorter than a minimum duration are discarded as noise.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class MotionSample:
    """A single sampled frame's motion measurement."""

    time: float  # seconds
    score: float  # 0..1
    active: bool


@dataclass(slots=True)
class Segment:
    """A contiguous activity segment."""

    start_time: float
    end_time: float
    scores: list[float] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return max(0.0, self.end_time - self.start_time)

    @property
    def avg_score(self) -> float:
        return sum(self.scores) / len(self.scores) if self.scores else 0.0

    @property
    def peak_score(self) -> float:
        return max(self.scores) if self.scores else 0.0


def build_segments(
    samples: list[MotionSample],
    *,
    merge_gap_sec: float = 1.5,
    min_duration_sec: float = 1.0,
    min_score: float = 0.0,
) -> list[Segment]:
    """Group motion samples into activity segments.

    Args:
        samples: Chronologically ordered motion samples.
        merge_gap_sec: Max gap of inactivity tolerated before closing a segment.
        min_duration_sec: Segments shorter than this are dropped.
        min_score: Segments whose average score is below this are dropped.

    Returns:
        A list of :class:`Segment` objects ordered by start time.
    """
    segments: list[Segment] = []
    current: Segment | None = None
    last_active_time: float | None = None

    for sample in samples:
        if sample.active:
            if current is None:
                current = Segment(start_time=sample.time, end_time=sample.time)
            current.end_time = sample.time
            current.scores.append(sample.score)
            last_active_time = sample.time
        else:
            if current is not None and last_active_time is not None:
                if sample.time - last_active_time > merge_gap_sec:
                    # The inactivity gap exceeded the bridge window: close the
                    # segment at its last *active* sample (end_time already set).
                    segments.append(current)
                    current = None
                    last_active_time = None
                # Otherwise stay within the bridge window and keep the segment
                # open without extending its end into the quiet tail, so brief
                # lulls inside a burst do not fragment (or inflate) the event.

    if current is not None:
        segments.append(current)

    # Filter by duration and average score.
    return [
        seg
        for seg in segments
        if seg.duration >= min_duration_sec and seg.avg_score >= min_score
    ]
