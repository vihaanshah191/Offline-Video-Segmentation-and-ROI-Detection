"""Unit tests for motion detection and ROI detection."""
from __future__ import annotations

import cv2
import numpy as np
import pytest
from app.services.motion_detection import (
    FRAME_DIFF,
    MOG2,
    MOG2_WARMUP_FRAMES,
    OPTICAL_FLOW,
    MotionDetector,
    select_best_algorithm,
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


def test_auto_is_not_a_constructible_algorithm() -> None:
    """'auto' must be resolved via select_best_algorithm() before
    construction — MotionDetector itself only accepts concrete algorithms."""
    with pytest.raises(ValueError):
        MotionDetector(algorithm="auto")


# ------------------------------------------------------------- min_area / noise
def test_min_area_filters_score_not_just_boxes() -> None:
    """Regression test for a real bug: min_area was previously accepted by
    MotionDetector but never actually applied to the mask, so the motion
    *score* (used for segmentation decisions) included noise pixels below the
    configured area threshold even though downstream ROI boxes were filtered.
    A tiny speck below min_area must now contribute ~zero to the score."""
    detector_filtered = MotionDetector(algorithm=FRAME_DIFF, min_area=5000, diff_threshold=10)
    detector_unfiltered = MotionDetector(algorithm=FRAME_DIFF, min_area=1, diff_threshold=10)

    base = _blank(200, 200)
    speck = base.copy()
    speck[50:55, 50:55] = 255  # 25px^2 speck — well below the 5000 min_area

    detector_filtered.process(base)
    detector_unfiltered.process(base)
    filtered_result = detector_filtered.process(speck)
    unfiltered_result = detector_unfiltered.process(speck)

    assert filtered_result.score == 0.0
    assert unfiltered_result.score > 0.0


# ---------------------------------------------------------------- MOG2 warmup
def test_mog2_warmup_flag() -> None:
    detector = MotionDetector(algorithm=MOG2)
    first = detector.process(_blank())
    assert first.is_warming_up is True
    assert detector.is_warming_up is True

    for _ in range(MOG2_WARMUP_FRAMES + 5):
        result = detector.process(_blank())
    assert result.is_warming_up is False


def test_non_mog2_algorithms_never_report_warmup() -> None:
    detector = MotionDetector(algorithm=FRAME_DIFF)
    result = detector.process(_blank())
    assert result.is_warming_up is False


def test_reset_restores_warmup_state() -> None:
    detector = MotionDetector(algorithm=MOG2)
    for _ in range(MOG2_WARMUP_FRAMES + 5):
        detector.process(_blank())
    assert detector.is_warming_up is False
    detector.reset()
    assert detector.is_warming_up is True


# ----------------------------------------------------------- adaptive kernel
def test_kernel_scales_with_resolution() -> None:
    small = MotionDetector(algorithm=FRAME_DIFF, frame_width=160, frame_height=120)
    large = MotionDetector(algorithm=FRAME_DIFF, frame_width=3840, frame_height=2160)
    assert small._kernel.shape[0] < large._kernel.shape[0]


def test_kernel_auto_detected_from_first_frame_if_not_provided() -> None:
    detector = MotionDetector(algorithm=FRAME_DIFF)
    assert detector._kernel_initialised is False
    detector.process(_blank(h=1080, w=1920))
    assert detector._kernel_initialised is True


# ------------------------------------------------------------ auto selection
def test_select_best_algorithm_unopenable_file_defaults_to_mog2() -> None:
    assert select_best_algorithm("/nonexistent/path/video.mp4") == MOG2


def test_select_best_algorithm_returns_supported_value(tmp_path) -> None:
    path = tmp_path / "synthetic.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, 15, (64, 64))
    rng = np.random.default_rng(0)
    for _ in range(30):
        frame = rng.integers(0, 255, (64, 64, 3), dtype=np.uint8)
        writer.write(frame)
    writer.release()

    result = select_best_algorithm(str(path))
    assert result in (MOG2, FRAME_DIFF, OPTICAL_FLOW)


# ------------------------------------------------------------------- ROI tests
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


def test_roi_detector_area_fraction_is_resolution_relative() -> None:
    """The same fixed pixel min_area behaves very differently at different
    resolutions; min_area_fraction should filter consistently regardless of
    frame size."""
    fraction = 0.01  # 1% of frame area
    small_mask = np.zeros((100, 100), dtype=np.uint8)  # 1% = 100px^2
    small_mask[0:9, 0:9] = 255  # 81px^2 < 100px^2 -> filtered out
    assert ROIDetector(min_area_fraction=fraction).detect(small_mask) == []

    small_mask2 = np.zeros((100, 100), dtype=np.uint8)
    small_mask2[0:15, 0:15] = 255  # 225px^2 > 100px^2 -> kept
    assert len(ROIDetector(min_area_fraction=fraction).detect(small_mask2)) == 1


def test_roi_detector_area_fraction_takes_precedence_over_fixed() -> None:
    mask = np.zeros((100, 100), dtype=np.uint8)
    mask[0:9, 0:9] = 255  # 81px^2
    # Fixed min_area alone (very low) would keep this; fraction (1%=100px^2)
    # should still filter it out because fraction takes precedence when > 0.
    detector = ROIDetector(min_area=10, min_area_fraction=0.01)
    assert detector.detect(mask) == []


def test_roi_detector_caps_raw_contours_for_performance() -> None:
    """A pathologically noisy frame with hundreds of tiny-but-valid contours
    must not blow up merge-pass cost — only the largest max_raw_contours are
    kept before merging."""
    mask = np.zeros((400, 400), dtype=np.uint8)
    # Scatter 300 well-separated 4x4 blocks (all above a tiny min_area).
    idx = 0
    for gy in range(0, 380, 10):
        for gx in range(0, 380, 10):
            if idx >= 300:
                break
            mask[gy : gy + 4, gx : gx + 4] = 255
            idx += 1
        if idx >= 300:
            break

    detector = ROIDetector(min_area=4, merge_iou=0.9, max_raw_contours=50)
    boxes = detector.detect(mask)
    # With merge_iou this high, disjoint 4x4 blocks won't merge, so the
    # returned box count directly reflects how many raw contours survived
    # the cap — must not exceed the cap (well under the ~300 available).
    assert len(boxes) <= 50
