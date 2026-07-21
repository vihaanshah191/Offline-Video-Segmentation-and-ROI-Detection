"""Video segmentation from a per-frame motion-score timeline.

Converts a chronological list of raw motion samples into discrete activity
segments ("events") using three standard signal-processing techniques applied
in sequence:

1. **Temporal smoothing** — a trailing moving average damps single-frame noise
   spikes/dropouts in the raw score series before any threshold decision is
   made (``smooth_scores``).
2. **Hysteresis thresholding** — rather than a single boundary (which causes a
   noisy score hovering near the threshold to flicker active/inactive many
   times per second, fragmenting one real event into dozens of tiny ones), two
   thresholds are used: a higher one to *enter* the active state and a lower
   one to *exit* it. This is the standard fix (used in e.g. Canny edge
   detection) for a noisy continuous signal driving a binary decision.
3. **Gap bridging + minimum-duration filtering** — short inactive gaps inside
   a burst are bridged into one segment; segments shorter than a minimum
   duration are dropped as residual noise.

**Score normalization** rescales the raw (algorithm-dependent, typically tiny)
motion scores to the video's own 0..1 activity range, so "1.0" always means
"the most active moment in this recording" — making the numbers legible on a
dashboard — without disturbing the raw scores used for threshold decisions.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass(slots=True)
class MotionSample:
    """A single sampled frame's raw motion measurement."""

    time: float  # seconds
    score: float  # raw fraction of frame pixels in motion, 0..1
    roi_present: bool = True  # whether at least one ROI box was detected


@dataclass(slots=True)
class Segment:
    """A contiguous activity segment."""

    start_time: float
    end_time: float
    scores: list[float] = field(default_factory=list)  # raw scores
    normalized_scores: list[float] = field(default_factory=list)  # video-relative 0..1

    @property
    def duration(self) -> float:
        return max(0.0, self.end_time - self.start_time)

    @property
    def avg_score(self) -> float:
        return sum(self.scores) / len(self.scores) if self.scores else 0.0

    @property
    def peak_score(self) -> float:
        return max(self.scores) if self.scores else 0.0

    @property
    def avg_normalized_score(self) -> float:
        return (
            sum(self.normalized_scores) / len(self.normalized_scores)
            if self.normalized_scores
            else 0.0
        )

    @property
    def peak_normalized_score(self) -> float:
        return max(self.normalized_scores) if self.normalized_scores else 0.0


def smooth_scores(scores: np.ndarray, window: int) -> np.ndarray:
    """Trailing moving-average smoothing, vectorized via convolution.

    A *trailing* (causal) window is used rather than a centered one so the
    smoothed value at index ``i`` never depends on future samples — this keeps
    the semantics compatible with (eventual) streaming/online processing and
    avoids smearing an event's true start time earlier than it occurred.

    Args:
        scores: 1-D array of raw scores, chronologically ordered.
        window: Number of trailing samples to average (>=1). Clamped to the
            series length.

    Returns:
        A same-length array of smoothed scores.
    """
    n = len(scores)
    if n == 0 or window <= 1:
        return scores.astype(np.float64, copy=True)

    window = min(window, n)
    kernel = np.ones(window, dtype=np.float64) / window
    # Pad the front by replicating the first sample so the average at index 0
    # is well-defined (equal to scores[0]) instead of ramping up from zero.
    padded = np.concatenate([np.full(window - 1, scores[0], dtype=np.float64), scores])
    return np.convolve(padded, kernel, mode="valid")


def normalize_scores(scores: np.ndarray) -> np.ndarray:
    """Min-max normalize a score series to 0..1 using its own observed range.

    Returns an all-zero array (rather than dividing by zero) when the series
    has no dynamic range (e.g. a perfectly static video).
    """
    if len(scores) == 0:
        return scores.astype(np.float64, copy=True)
    lo, hi = float(scores.min()), float(scores.max())
    if hi - lo < 1e-12:
        return np.zeros_like(scores, dtype=np.float64)
    return (scores - lo) / (hi - lo)


def build_segments(
    samples: list[MotionSample],
    *,
    enter_threshold: float,
    exit_threshold: float | None = None,
    smoothing_window: int = 5,
    merge_gap_sec: float = 1.5,
    min_duration_sec: float = 1.0,
) -> list[Segment]:
    """Group motion samples into activity segments.

    Args:
        samples: Chronologically ordered motion samples.
        enter_threshold: Smoothed score above which a sample can *start* an
            active segment (also requires ``roi_present``).
        exit_threshold: Smoothed score below which an active segment *ends*.
            Defaults to 60% of ``enter_threshold`` (hysteresis band) when not
            given explicitly; must be <= ``enter_threshold``.
        smoothing_window: Trailing moving-average window (samples) applied to
            the raw score series before thresholding.
        merge_gap_sec: Max gap of inactivity tolerated before closing a segment.
        min_duration_sec: Segments shorter than this are dropped.

    Returns:
        A list of :class:`Segment` objects ordered by start time.
    """
    if not samples:
        return []

    if exit_threshold is None:
        exit_threshold = enter_threshold * 0.6
    exit_threshold = min(exit_threshold, enter_threshold)

    times = np.array([s.time for s in samples], dtype=np.float64)
    raw_scores = np.array([s.score for s in samples], dtype=np.float64)
    roi_flags = np.array([s.roi_present for s in samples], dtype=bool)

    smoothed = smooth_scores(raw_scores, smoothing_window)
    normalized = normalize_scores(raw_scores)

    # Hysteresis state machine: enter on a high threshold + ROI presence,
    # exit only once the smoothed score drops below the (lower) exit
    # threshold. This is what actually prevents fragmentation from a score
    # dithering around a single boundary.
    active = np.zeros(len(samples), dtype=bool)
    state = False
    for i in range(len(samples)):
        if state:
            state = smoothed[i] >= exit_threshold
        else:
            state = bool(smoothed[i] >= enter_threshold and roi_flags[i])
        active[i] = state

    segments: list[Segment] = []
    current: Segment | None = None
    last_active_time: float | None = None

    for i in range(len(samples)):
        t = float(times[i])
        if active[i]:
            if current is None:
                current = Segment(start_time=t, end_time=t)
            current.end_time = t
            current.scores.append(float(raw_scores[i]))
            current.normalized_scores.append(float(normalized[i]))
            last_active_time = t
        elif current is not None and last_active_time is not None:
            if t - last_active_time > merge_gap_sec:
                # Inactivity exceeded the bridge window: close the segment at
                # its last *active* sample (end_time already set there) rather
                # than extending it into the quiet tail.
                segments.append(current)
                current = None
                last_active_time = None
            # else: still inside the bridge window — keep the segment open
            # without extending end_time or appending scores for inactive
            # samples, so a brief lull inside a burst neither fragments nor
            # inflates the reported event duration.

    if current is not None:
        segments.append(current)

    return [seg for seg in segments if seg.duration >= min_duration_sec]
