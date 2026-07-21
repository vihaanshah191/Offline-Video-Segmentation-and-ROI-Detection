"""Unit tests for the segmentation algorithm."""
from __future__ import annotations

from app.services.segmentation import MotionSample, build_segments


def _samples(pattern: list[tuple[float, bool]]) -> list[MotionSample]:
    return [MotionSample(time=t, score=0.05 if a else 0.0, active=a) for t, a in pattern]


def test_single_segment() -> None:
    samples = _samples([(0, False), (1, True), (2, True), (3, True), (4, False)])
    segments = build_segments(samples, merge_gap_sec=1.0, min_duration_sec=0.5)
    assert len(segments) == 1
    assert segments[0].start_time == 1
    assert segments[0].end_time == 3


def test_two_segments_split_by_gap() -> None:
    samples = _samples(
        [(0, True), (1, True), (2, False), (3, False), (4, False), (5, True), (6, True)]
    )
    segments = build_segments(samples, merge_gap_sec=1.0, min_duration_sec=0.5)
    assert len(segments) == 2


def test_short_segment_filtered() -> None:
    samples = _samples([(0, False), (1, True), (1.1, False), (5, False)])
    segments = build_segments(samples, merge_gap_sec=0.5, min_duration_sec=1.0)
    assert segments == []


def test_bridge_short_gap() -> None:
    # A short inactive blip inside an active burst should not split it.
    samples = _samples(
        [(0, True), (1, True), (1.5, False), (2, True), (3, True), (6, False)]
    )
    segments = build_segments(samples, merge_gap_sec=1.0, min_duration_sec=0.5)
    assert len(segments) == 1
    assert segments[0].duration >= 2.0
