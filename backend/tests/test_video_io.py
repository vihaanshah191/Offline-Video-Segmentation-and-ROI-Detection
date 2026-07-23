"""Tests for video I/O helpers in app.utils.video_io."""
from __future__ import annotations

from pathlib import Path

import cv2
from app.utils import video_io
from app.utils.video_io import cut_clip


def test_cut_clip_degenerate_range_still_writes_a_playable_clip(
    tmp_path: Path, sample_video_path: Path, monkeypatch
) -> None:
    """Regression test: ``cut_clip`` floors ``duration = end - start`` at 0.1s
    but, before this fix, passed the raw (unclamped) ``end`` through to the
    OpenCV fallback rather than the floored value. When end <= start reaches
    that fallback, its loop's first bounds check can be true before a single
    frame is written — ``VideoWriter.release()`` still leaves a file on disk,
    so ``cut_clip`` reports success for what is actually a zero-frame,
    unplayable clip. This forces the OpenCV path directly (bypassing ffmpeg)
    with a degenerate end == start and asserts the resulting file actually
    contains at least one frame.
    """
    output = tmp_path / "degenerate.mp4"
    monkeypatch.setattr(video_io, "ffmpeg_available", lambda: False)

    result = cut_clip(sample_video_path, output, start=3.0, end=3.0)

    assert result is True
    assert output.exists()
    cap = cv2.VideoCapture(str(output))
    try:
        ok, frame = cap.read()
        assert ok and frame is not None
    finally:
        cap.release()
