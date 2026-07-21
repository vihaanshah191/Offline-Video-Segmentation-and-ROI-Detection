"""Motion detection algorithms.

Three interchangeable strategies are provided, all exposing the same interface
via :class:`MotionDetector`:

* ``mog2`` – MOG2 background subtraction (robust to gradual lighting change).
* ``frame_diff`` – consecutive frame differencing (cheap, sensitive).
* ``optical_flow`` – Farneback dense optical flow (captures true movement).

Each call to :meth:`MotionDetector.process` returns a :class:`MotionResult`
containing a normalised motion score (fraction of the frame in motion, 0..1) and
a binary foreground mask suitable for ROI/contour extraction.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from app.core.logging_config import get_logger

logger = get_logger(__name__)

MOG2 = "mog2"
FRAME_DIFF = "frame_diff"
OPTICAL_FLOW = "optical_flow"
SUPPORTED_ALGORITHMS = (MOG2, FRAME_DIFF, OPTICAL_FLOW)


@dataclass(slots=True)
class MotionResult:
    """Result of processing a single frame."""

    score: float  # fraction of frame pixels in motion (0..1)
    mask: np.ndarray  # uint8 binary foreground mask (same H/W as input)


class MotionDetector:
    """Stateful motion detector supporting three swappable algorithms.

    The detector keeps whatever internal state its algorithm needs (background
    model, previous frame, previous grayscale for flow) so frames must be fed in
    chronological order.
    """

    def __init__(
        self,
        algorithm: str = MOG2,
        *,
        blur_ksize: int = 5,
        min_area: int = 800,
        flow_threshold: float = 1.5,
        diff_threshold: int = 25,
    ) -> None:
        """Create a motion detector.

        Args:
            algorithm: One of :data:`SUPPORTED_ALGORITHMS`.
            blur_ksize: Gaussian blur kernel size applied before detection.
            min_area: Morphological noise-removal reference (kept for parity).
            flow_threshold: Optical-flow magnitude above which a pixel is moving.
            diff_threshold: Grayscale delta above which a pixel is moving.
        """
        algorithm = algorithm.lower()
        if algorithm not in SUPPORTED_ALGORITHMS:
            raise ValueError(
                f"Unknown motion algorithm '{algorithm}'. "
                f"Choose from {SUPPORTED_ALGORITHMS}."
            )
        self.algorithm = algorithm
        self.blur_ksize = blur_ksize if blur_ksize % 2 == 1 else blur_ksize + 1
        self.min_area = min_area
        self.flow_threshold = flow_threshold
        self.diff_threshold = diff_threshold

        self._prev_gray: np.ndarray | None = None
        self._kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))

        if algorithm == MOG2:
            self._bg = cv2.createBackgroundSubtractorMOG2(
                history=500, varThreshold=24, detectShadows=True
            )
        else:
            self._bg = None

    # ------------------------------------------------------------------ public
    def process(self, frame: np.ndarray) -> MotionResult:
        """Process one BGR frame and return its :class:`MotionResult`."""
        gray = self._preprocess(frame)

        if self.algorithm == MOG2:
            mask = self._process_mog2(gray)
        elif self.algorithm == FRAME_DIFF:
            mask = self._process_frame_diff(gray)
        else:
            mask = self._process_optical_flow(gray)

        self._prev_gray = gray
        mask = self._clean_mask(mask)
        score = float(np.count_nonzero(mask)) / float(mask.size) if mask.size else 0.0
        return MotionResult(score=score, mask=mask)

    def reset(self) -> None:
        """Reset internal state (e.g. between videos)."""
        self._prev_gray = None
        if self.algorithm == MOG2:
            self._bg = cv2.createBackgroundSubtractorMOG2(
                history=500, varThreshold=24, detectShadows=True
            )

    # ----------------------------------------------------------------- helpers
    def _preprocess(self, frame: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return cv2.GaussianBlur(gray, (self.blur_ksize, self.blur_ksize), 0)

    def _process_mog2(self, gray: np.ndarray) -> np.ndarray:
        fg = self._bg.apply(gray)
        # MOG2 marks shadows as 127; keep only strong foreground.
        _, mask = cv2.threshold(fg, 200, 255, cv2.THRESH_BINARY)
        return mask

    def _process_frame_diff(self, gray: np.ndarray) -> np.ndarray:
        if self._prev_gray is None:
            return np.zeros_like(gray)
        delta = cv2.absdiff(self._prev_gray, gray)
        _, mask = cv2.threshold(delta, self.diff_threshold, 255, cv2.THRESH_BINARY)
        return mask

    def _process_optical_flow(self, gray: np.ndarray) -> np.ndarray:
        if self._prev_gray is None:
            return np.zeros_like(gray)
        flow = cv2.calcOpticalFlowFarneback(
            self._prev_gray,
            gray,
            None,
            pyr_scale=0.5,
            levels=3,
            winsize=15,
            iterations=3,
            poly_n=5,
            poly_sigma=1.2,
            flags=0,
        )
        magnitude, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])
        mask = (magnitude > self.flow_threshold).astype(np.uint8) * 255
        return mask

    def _clean_mask(self, mask: np.ndarray) -> np.ndarray:
        """Morphological open+dilate to remove speckle noise and fill gaps."""
        if mask.max() == 0:
            return mask
        opened = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self._kernel, iterations=1)
        dilated = cv2.dilate(opened, self._kernel, iterations=2)
        return dilated
