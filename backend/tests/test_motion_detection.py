"""Unit tests for motion detection and ROI detection."""
from __future__ import annotations

import numpy as np
import pytest

from app.services.motion_detection import (
    FRAME_DIFF,
    MOG2,
    OPTICAL_FLOW,
    MotionDetector,
)
from app.services.roi_detection import ROIDetector


def _blank(h: int = 120, w: int = 160) -> np.ndarray:
    return np.zeros((h, w, 3), dtype=np.uint8)


def _with_block(h: int = 120, w: int = 160, x: int = 40, y: int = 40) -> np.ndarray:
    frame = _blank(h, w)
    frame[y : y + 30, x : x + 30] = 255
    return frame


@pytest.mark.parametrize("algorithm", [MOG2, FRAME_DIFF, OPTICAL_FLOW])
def test_static_scene_no_motion(algorithm: str) -> None:
    detector = MotionDetector(algorithm=algorithm)
    detector.process(_blank())
    result = detector.process(_blank())
    assert result.score == 0.0


@pytest.mark.parametrize("algorithm", [FRAME_DIFF, MOG2])
def test_moving_block_produces_motion(algorithm: str) -> None:
    detector = MotionDetector(algorithm=algorithm)
    detector.process(_blank())
    detector.process(_with_block(x=20))
    result = detector.process(_with_block(x=80))
    assert result.score > 0.0
    assert result.mask.shape == (120, 160)


def test_invalid_algorithm_raises() -> None:
    with pytest.raises(ValueError):
        MotionDetector(algorithm="nope")


def test_roi_detector_finds_block() -> None:
    mask = np.zeros((120, 160), dtype=np.uint8)
    mask[30:80, 40:110] = 255
    boxes = ROIDetector(min_area=100).detect(mask)
    assert len(boxes) == 1
    box = boxes[0]
    assert box.w > 40 and box.h > 30
    assert 0.0 <= box.confidence <= 1.0


def test_roi_detector_filters_noise() -> None:
    mask = np.zeros((120, 160), dtype=np.uint8)
    mask[10:12, 10:12] = 255  # tiny speck below min_area
    boxes = ROIDetector(min_area=500).detect(mask)
    assert boxes == []


def test_roi_detector_empty_mask() -> None:
    assert ROIDetector().detect(np.zeros((50, 50), dtype=np.uint8)) == []
