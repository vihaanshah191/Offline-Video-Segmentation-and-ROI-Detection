"""Motion heatmap accumulation and rendering.

A :class:`HeatmapAccumulator` sums per-frame motion masks into a float buffer.
When finalised it normalises the buffer, applies a JET colormap (high/medium/low
movement bands) and blends it over a representative background frame, exporting a
PNG.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from app.core.logging_config import get_logger

logger = get_logger(__name__)


class HeatmapAccumulator:
    """Accumulate motion masks into a persistent heatmap."""

    def __init__(self, height: int, width: int) -> None:
        self.height = height
        self.width = width
        self._accum = np.zeros((height, width), dtype=np.float32)
        self._background: np.ndarray | None = None
        self._frames_added = 0

    def add(self, mask: np.ndarray, frame: np.ndarray | None = None) -> None:
        """Add a binary motion ``mask`` (and optionally a colour ``frame``)."""
        if mask.shape[:2] != (self.height, self.width):
            mask = cv2.resize(mask, (self.width, self.height))
        self._accum += (mask > 0).astype(np.float32)
        self._frames_added += 1
        # Capture a mid-video background frame for nicer overlays.
        if frame is not None and (self._background is None or self._frames_added % 50 == 0):
            if frame.shape[:2] != (self.height, self.width):
                frame = cv2.resize(frame, (self.width, self.height))
            self._background = frame.copy()

    @property
    def has_data(self) -> bool:
        return self._frames_added > 0 and float(self._accum.max()) > 0

    def render(self, alpha: float = 0.6) -> np.ndarray | None:
        """Render the accumulated heatmap blended over the background frame."""
        if not self.has_data:
            return None

        norm = self._accum / self._accum.max()
        norm = np.power(norm, 0.6)  # gamma boost so low activity stays visible
        heat_u8 = np.uint8(np.clip(norm * 255, 0, 255))
        heat_u8 = cv2.GaussianBlur(heat_u8, (0, 0), sigmaX=5, sigmaY=5)
        colored = cv2.applyColorMap(heat_u8, cv2.COLORMAP_JET)

        if self._background is not None:
            base = self._background
        else:
            base = np.zeros((self.height, self.width, 3), dtype=np.uint8)

        # Only blend where there is measurable activity so cold areas stay clean.
        mask = (heat_u8 > 10).astype(np.float32)[..., None]
        blended = base.astype(np.float32) * (1 - alpha * mask) + colored.astype(
            np.float32
        ) * (alpha * mask)
        return np.uint8(np.clip(blended, 0, 255))

    def save(self, output_path: str | Path, alpha: float = 0.6) -> bool:
        """Render and write the heatmap PNG. Returns success flag."""
        image = self.render(alpha=alpha)
        if image is None:
            logger.info("No motion accumulated; heatmap not generated")
            return False
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        return bool(cv2.imwrite(str(output_path), image))
