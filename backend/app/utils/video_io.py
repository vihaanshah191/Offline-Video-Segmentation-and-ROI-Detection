"""Video I/O helpers built on OpenCV and FFmpeg.

Responsibilities:
* Probe video metadata (fps, duration, resolution, frame count).
* Extract thumbnails.
* Cut clips using FFmpeg (fast, lossless stream-copy where possible).
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import cv2

from app.core.logging_config import get_logger

logger = get_logger(__name__)


@dataclass(slots=True)
class VideoMetadata:
    """Container for probed video metadata."""

    fps: float
    frame_count: int
    width: int
    height: int
    duration: float  # seconds


def ffmpeg_available() -> bool:
    """Return ``True`` if the ``ffmpeg`` binary is on the PATH."""
    return shutil.which("ffmpeg") is not None


def probe_metadata(video_path: str | Path) -> VideoMetadata:
    """Read metadata from a video file using OpenCV.

    Args:
        video_path: Path to the video file.

    Returns:
        A :class:`VideoMetadata` instance.

    Raises:
        ValueError: If the file cannot be opened.
    """
    path = str(video_path)
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise ValueError(f"Unable to open video file: {path}")

    try:
        fps = float(cap.get(cv2.CAP_PROP_FPS)) or 0.0
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 0
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 0
    finally:
        cap.release()

    # Some containers report fps=0 or bad frame counts; fall back sensibly.
    if fps <= 0:
        fps = 25.0
    duration = frame_count / fps if fps > 0 and frame_count > 0 else 0.0
    return VideoMetadata(
        fps=round(fps, 3),
        frame_count=frame_count,
        width=width,
        height=height,
        duration=round(duration, 3),
    )


def extract_thumbnail(
    video_path: str | Path,
    output_path: str | Path,
    timestamp: float = 0.0,
    max_width: int = 640,
) -> bool:
    """Extract a single frame at ``timestamp`` and save it as a JPEG thumbnail.

    Args:
        video_path: Source video.
        output_path: Destination image path.
        timestamp: Time (seconds) to grab the frame from.
        max_width: Downscale the thumbnail so its width does not exceed this.

    Returns:
        ``True`` on success, ``False`` otherwise.
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        logger.warning("Cannot open %s for thumbnail extraction", video_path)
        return False
    try:
        cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, timestamp) * 1000.0)
        ok, frame = cap.read()
        if not ok or frame is None:
            # Retry from the very first frame.
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = cap.read()
        if not ok or frame is None:
            return False

        h, w = frame.shape[:2]
        if w > max_width:
            scale = max_width / w
            frame = cv2.resize(frame, (int(w * scale), int(h * scale)))

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        return bool(cv2.imwrite(str(output_path), frame))
    finally:
        cap.release()


def cut_clip(
    video_path: str | Path,
    output_path: str | Path,
    start: float,
    end: float,
) -> bool:
    """Cut a sub-clip ``[start, end]`` (seconds) from a video.

    Uses FFmpeg with stream copy when available (fast, no re-encode). Falls back
    to an OpenCV frame-by-frame re-encode if FFmpeg is not installed.

    Returns:
        ``True`` if the clip was written successfully.
    """
    start = max(0.0, start)
    duration = max(0.1, end - start)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    if ffmpeg_available():
        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            f"{start:.3f}",
            "-i",
            str(video_path),
            "-t",
            f"{duration:.3f}",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-an",
            str(output_path),
        ]
        try:
            subprocess.run(
                cmd,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=600,
            )
            return Path(output_path).exists()
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            logger.warning("FFmpeg clip failed (%s); falling back to OpenCV", exc)

    return _cut_clip_opencv(video_path, output_path, start, end)


def _cut_clip_opencv(
    video_path: str | Path, output_path: str | Path, start: float, end: float
) -> bool:
    """Fallback clip cutter that re-encodes frames with OpenCV."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return False
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))

        cap.set(cv2.CAP_PROP_POS_MSEC, start * 1000.0)
        end_ms = end * 1000.0
        while True:
            if cap.get(cv2.CAP_PROP_POS_MSEC) > end_ms:
                break
            ok, frame = cap.read()
            if not ok or frame is None:
                break
            writer.write(frame)
        writer.release()
        return Path(output_path).exists()
    finally:
        cap.release()
