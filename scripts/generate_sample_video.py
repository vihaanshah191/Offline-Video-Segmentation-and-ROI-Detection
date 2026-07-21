#!/usr/bin/env python3
"""Generate a synthetic sample video for demos, tests and CI.

The clip simulates an examination hall: a mostly static scene ("desks") with
bursts of movement (a moving block = a person / object) separated by quiet
periods. This produces a video the analysis pipeline can meaningfully segment
without requiring any real footage.

Usage:
    python scripts/generate_sample_video.py [output.mp4] [--seconds 20] [--fps 15]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np


def generate(output: Path, seconds: int = 20, fps: int = 15, width: int = 640, height: int = 360) -> Path:
    """Render a synthetic video with alternating motion / still segments."""
    output.parent.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(output), fourcc, fps, (width, height))
    total = seconds * fps

    # Static background: a desk grid on a neutral floor.
    background = np.full((height, width, 3), 40, dtype=np.uint8)
    for gx in range(60, width, 120):
        for gy in range(60, height, 100):
            cv2.rectangle(background, (gx, gy), (gx + 70, gy + 45), (90, 90, 90), -1)

    # Motion windows (in seconds): (start, end).
    motion_windows = [(2, 5), (8, 11), (14, 18)]

    def in_motion(t: float) -> bool:
        return any(a <= t <= b for a, b in motion_windows)

    for i in range(total):
        t = i / fps
        frame = background.copy()
        # Mild sensor noise so background subtraction behaves realistically.
        frame = cv2.add(frame, np.random.randint(0, 6, frame.shape, dtype=np.uint8))

        if in_motion(t):
            phase = (t * 2.0) % (2 * np.pi)
            cx = int(width * 0.5 + np.sin(phase) * width * 0.3)
            cy = int(height * 0.5 + np.cos(phase * 0.7) * height * 0.25)
            cv2.rectangle(frame, (cx - 30, cy - 40), (cx + 30, cy + 40), (0, 140, 255), -1)
            cv2.circle(frame, (cx, cy - 55), 18, (0, 200, 255), -1)  # a "head"

        writer.write(frame)

    writer.release()
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a synthetic sample video.")
    parser.add_argument("output", nargs="?", default="sample_data/sample_exam_hall.mp4")
    parser.add_argument("--seconds", type=int, default=20)
    parser.add_argument("--fps", type=int, default=15)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=360)
    args = parser.parse_args()

    path = generate(Path(args.output), args.seconds, args.fps, args.width, args.height)
    print(f"Wrote sample video: {path.resolve()}")


if __name__ == "__main__":
    main()
