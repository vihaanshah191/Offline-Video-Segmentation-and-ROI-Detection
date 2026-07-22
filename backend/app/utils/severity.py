"""Shared event-severity classification.

Used by both the event-log API (``EventRead.severity``) and the timeline's
event markers (``compute_timeline``) so the two views of the same events can
never disagree about how serious one looks.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

# A peak motion score at or above this (0..1, already normalized) is
# considered unusually high activity even with no object detection to back
# it up — e.g. rapid, large-area movement.
HIGH_MOTION_THRESHOLD = 0.66


class _DetectionLike(Protocol):
    prohibited: bool
    heuristic: bool


def compute_severity(peak_motion_score: float, detections: Iterable[_DetectionLike]) -> str:
    """Classify an event as 'critical' | 'warning' | 'normal'.

    * critical — at least one confirmed (non-heuristic) prohibited detection.
    * warning — a heuristic-only prohibited detection (e.g. a 'book' standing
      in for 'possible notes' — see object_detection.py), or unusually high
      peak motion, without a confirmed prohibited detection.
    * normal — everything else.
    """
    detections = list(detections)
    if any(d.prohibited and not d.heuristic for d in detections):
        return "critical"
    if any(d.prohibited and d.heuristic for d in detections) or peak_motion_score >= HIGH_MOTION_THRESHOLD:
        return "warning"
    return "normal"
