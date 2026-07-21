"""Unit tests for the segmentation algorithm: smoothing, hysteresis, normalization."""
from __future__ import annotations

import numpy as np
from app.services.segmentation import (
    MotionSample,
    build_segments,
    normalize_scores,
    smooth_scores,
)


def _samples(pattern: list[tuple[float, bool]], score: float = 0.05) -> list[MotionSample]:
    """Build samples whose raw score is high enough to cross the default
    threshold whenever ``roi_present`` is True, and zero otherwise."""
    return [
        MotionSample(time=t, score=score if roi else 0.0, roi_present=roi) for t, roi in pattern
    ]


def test_single_segment() -> None:
    samples = _samples([(0, False), (1, True), (2, True), (3, True), (4, False)])
    segments = build_segments(
        samples, enter_threshold=0.01, smoothing_window=1, merge_gap_sec=1.0, min_duration_sec=0.5
    )
    assert len(segments) == 1
    assert segments[0].start_time == 1
    assert segments[0].end_time == 3


def test_two_segments_split_by_gap() -> None:
    samples = _samples(
        [(0, True), (1, True), (2, False), (3, False), (4, False), (5, True), (6, True)]
    )
    segments = build_segments(
        samples, enter_threshold=0.01, smoothing_window=1, merge_gap_sec=1.0, min_duration_sec=0.5
    )
    assert len(segments) == 2


def test_short_segment_filtered() -> None:
    samples = _samples([(0, False), (1, True), (1.1, False), (5, False)])
    segments = build_segments(
        samples, enter_threshold=0.01, smoothing_window=1, merge_gap_sec=0.5, min_duration_sec=1.0
    )
    assert segments == []


def test_bridge_short_gap() -> None:
    # A short inactive blip inside an active burst should not split it.
    samples = _samples(
        [(0, True), (1, True), (1.5, False), (2, True), (3, True), (6, False)]
    )
    segments = build_segments(
        samples, enter_threshold=0.01, smoothing_window=1, merge_gap_sec=1.0, min_duration_sec=0.5
    )
    assert len(segments) == 1
    assert segments[0].duration >= 2.0


def test_empty_samples_returns_no_segments() -> None:
    assert build_segments([], enter_threshold=0.5) == []


def test_roi_absence_prevents_segment_start() -> None:
    """A high score with no detected ROI must not open a segment (guards
    against a false-positive global score spike with no actual object)."""
    samples = [
        MotionSample(time=0.0, score=0.9, roi_present=False),
        MotionSample(time=1.0, score=0.9, roi_present=False),
        MotionSample(time=2.0, score=0.9, roi_present=False),
    ]
    segments = build_segments(samples, enter_threshold=0.1, smoothing_window=1, min_duration_sec=0.1)
    assert segments == []


def test_hysteresis_prevents_flicker_fragmentation() -> None:
    """A score dithering just above/below a single threshold would fragment
    into many tiny segments without hysteresis; the exit threshold being
    lower than the enter threshold should keep it as one segment."""
    # Score oscillates between 0.008 and 0.014 around enter=0.012; with a
    # lower exit threshold (0.6x = 0.0072) it never actually drops enough to
    # exit once active.
    pattern_scores = [0.0, 0.013, 0.009, 0.013, 0.009, 0.013, 0.009, 0.013, 0.0]
    samples = [
        MotionSample(time=float(i), score=s, roi_present=(s > 0)) for i, s in enumerate(pattern_scores)
    ]
    segments = build_segments(
        samples,
        enter_threshold=0.012,
        exit_threshold=0.012 * 0.6,
        smoothing_window=1,
        merge_gap_sec=0.5,
        min_duration_sec=0.5,
    )
    # Without hysteresis this would fragment into ~4 segments (one per dip
    # below 0.012); with hysteresis it should stay as a single segment.
    assert len(segments) == 1


def test_smooth_scores_moving_average() -> None:
    raw = np.array([0.0, 0.0, 1.0, 0.0, 0.0], dtype=np.float64)
    smoothed = smooth_scores(raw, window=3)
    assert len(smoothed) == len(raw)
    # The spike should be damped, not eliminated: middle value is the average
    # of a trailing 3-window that includes the spike.
    assert 0.0 < smoothed[2] <= 1.0
    assert smoothed[2] < raw[2]


def test_smooth_scores_window_one_is_noop() -> None:
    raw = np.array([0.1, 0.5, 0.2], dtype=np.float64)
    np.testing.assert_array_equal(smooth_scores(raw, window=1), raw)


def test_smooth_scores_empty() -> None:
    assert len(smooth_scores(np.array([], dtype=np.float64), window=5)) == 0


def test_normalize_scores_rescales_to_unit_range() -> None:
    raw = np.array([0.01, 0.02, 0.05, 0.1], dtype=np.float64)
    normalized = normalize_scores(raw)
    assert normalized.min() == 0.0
    assert normalized.max() == 1.0


def test_normalize_scores_constant_series_is_zero() -> None:
    raw = np.array([0.02, 0.02, 0.02], dtype=np.float64)
    normalized = normalize_scores(raw)
    assert np.all(normalized == 0.0)


def test_segment_exposes_normalized_scores() -> None:
    samples = _samples([(0, True), (1, True), (2, True)], score=0.05)
    segments = build_segments(samples, enter_threshold=0.01, smoothing_window=1, min_duration_sec=0.1)
    assert len(segments) == 1
    seg = segments[0]
    assert seg.avg_normalized_score >= 0.0
    assert seg.peak_normalized_score >= seg.avg_normalized_score
