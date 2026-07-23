"""Motion detection algorithms.

Three interchangeable strategies are provided, all exposing the same interface
via :class:`MotionDetector`:

* ``mog2`` – MOG2 background subtraction (robust to gradual lighting change).
* ``frame_diff`` – consecutive frame differencing (cheap, sensitive).
* ``optical_flow`` – Farneback dense optical flow (captures true movement).

A fourth pseudo-algorithm, ``auto``, is resolved by :func:`select_best_algorithm`
*before* construction: it pre-scans a handful of frames and heuristically picks
whichever of the three concrete algorithms best matches the footage.

Each call to :meth:`MotionDetector.process` returns a :class:`MotionResult`
containing a normalised motion score (fraction of the frame in motion, 0..1) and
a binary foreground mask suitable for ROI/contour extraction. The returned mask
is fully noise-filtered (connected-component area filtering + morphology) so
the motion *score* itself — not just downstream ROI boxes — reflects genuine
motion rather than sensor/compression noise.
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
AUTO = "auto"
SUPPORTED_ALGORITHMS = (MOG2, FRAME_DIFF, OPTICAL_FLOW)
# ``auto`` is a valid *request* value but resolves to one of the above before
# a MotionDetector is constructed — it is intentionally listed separately so
# API validation can accept it without MotionDetector having to special-case it.
SUPPORTED_REQUEST_VALUES = (*SUPPORTED_ALGORITHMS, AUTO)

# MOG2 needs a handful of frames to build a stable background model. Frames
# processed before this count are still scored (for visibility/debugging) but
# excluded from "active" motion decisions by the pipeline to avoid a spurious
# motion spike at t=0 while the model initialises.
MOG2_WARMUP_FRAMES = 15


@dataclass(slots=True)
class MotionResult:
    """Result of processing a single frame."""

    score: float  # fraction of frame pixels in motion (0..1), noise-filtered
    mask: np.ndarray  # uint8 binary foreground mask (same H/W as input)
    is_warming_up: bool = False  # True while the background model is unstable


def _resolution_scaled_kernel_size(width: int, height: int) -> int:
    """Pick a morphological kernel size proportional to frame resolution.

    A fixed 5x5 kernel over-smooths low-resolution footage and under-cleans
    high-resolution footage. Scaling by the frame diagonal keeps the *relative*
    noise-removal strength consistent from 480p up through 4K.
    """
    diagonal = (width**2 + height**2) ** 0.5
    size = max(3, round(diagonal / 400))
    return size if size % 2 == 1 else size + 1


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
        adaptive_threshold: bool = True,
        frame_width: int = 0,
        frame_height: int = 0,
    ) -> None:
        """Create a motion detector.

        Args:
            algorithm: One of :data:`SUPPORTED_ALGORITHMS` (concrete, not ``auto``).
            blur_ksize: Gaussian blur kernel size applied before detection.
            min_area: Minimum connected-component area (px) kept in the mask;
                smaller blobs are zeroed out as noise. This directly affects
                both the returned mask AND the motion score.
            flow_threshold: Optical-flow magnitude above which a pixel is moving.
            diff_threshold: Grayscale delta floor for frame differencing; used
                as a lower bound when ``adaptive_threshold`` is enabled (Otsu's
                method can otherwise pick an unstably low threshold on a nearly
                static frame) and as the fixed threshold when disabled.
            adaptive_threshold: When True, use Otsu's method to pick a
                per-frame threshold for frame differencing and MOG2 shadow
                rejection, instead of a single fixed constant — this keeps
                sensitivity consistent across varying lighting/noise levels.
            frame_width: Optional frame width, used to scale the morphological
                kernel to resolution. If omitted, kernel size defaults to 5x5
                until the first frame is processed (then auto-detected).
            frame_height: See ``frame_width``.
        """
        algorithm = algorithm.lower()
        if algorithm not in SUPPORTED_ALGORITHMS:
            raise ValueError(
                f"Unknown motion algorithm '{algorithm}'. "
                f"Choose from {SUPPORTED_ALGORITHMS} (or resolve 'auto' first via "
                f"select_best_algorithm())."
            )
        self.algorithm = algorithm
        self.blur_ksize = blur_ksize if blur_ksize % 2 == 1 else blur_ksize + 1
        self.min_area = min_area
        self.flow_threshold = flow_threshold
        self.diff_threshold = diff_threshold
        self.adaptive_threshold = adaptive_threshold

        self._prev_gray: np.ndarray | None = None
        self._frame_index = 0

        kernel_size = 5
        if frame_width and frame_height:
            kernel_size = _resolution_scaled_kernel_size(frame_width, frame_height)
        self._kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
        self._kernel_initialised = bool(frame_width and frame_height)

        self._bg: cv2.BackgroundSubtractorMOG2 | None = None
        if algorithm == MOG2:
            self._bg = cv2.createBackgroundSubtractorMOG2(
                history=500, varThreshold=24, detectShadows=True
            )

    # ------------------------------------------------------------------ public
    @property
    def is_warming_up(self) -> bool:
        """True while MOG2's background model is still initialising."""
        return self.algorithm == MOG2 and self._frame_index < MOG2_WARMUP_FRAMES

    def process(self, frame: np.ndarray) -> MotionResult:
        """Process one BGR frame and return its :class:`MotionResult`."""
        if not self._kernel_initialised:
            h, w = frame.shape[:2]
            kernel_size = _resolution_scaled_kernel_size(w, h)
            self._kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
            self._kernel_initialised = True

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

        warming_up = self.is_warming_up
        self._frame_index += 1
        return MotionResult(score=score, mask=mask, is_warming_up=warming_up)

    def reset(self) -> None:
        """Reset internal state (e.g. between videos)."""
        self._prev_gray = None
        self._frame_index = 0
        if self.algorithm == MOG2:
            self._bg = cv2.createBackgroundSubtractorMOG2(
                history=500, varThreshold=24, detectShadows=True
            )

    # ----------------------------------------------------------------- helpers
    def _preprocess(self, frame: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return cv2.GaussianBlur(gray, (self.blur_ksize, self.blur_ksize), 0)

    def _process_mog2(self, gray: np.ndarray) -> np.ndarray:
        assert self._bg is not None  # only called when algorithm == MOG2
        fg = self._bg.apply(gray)
        # MOG2 marks shadows as 127; keep only strong foreground. Otsu's method
        # adapts the cutoff to the actual bimodal distribution of this frame's
        # foreground-probability map rather than assuming a fixed 200/255 split
        # always separates "shadow" from "object" cleanly.
        if self.adaptive_threshold:
            # Only attempt Otsu when the frame actually has some foreground
            # signal; on a fully empty mask Otsu degenerates unpredictably.
            if fg.max() > 0:
                otsu_val, _ = cv2.threshold(fg, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                threshold = max(otsu_val, 180.0)  # floor: never below "strong foreground"
            else:
                threshold = 200.0
        else:
            threshold = 200.0
        _, mask = cv2.threshold(fg, threshold, 255, cv2.THRESH_BINARY)
        return mask

    def _process_frame_diff(self, gray: np.ndarray) -> np.ndarray:
        if self._prev_gray is None:
            return np.zeros_like(gray)
        delta = cv2.absdiff(self._prev_gray, gray)
        if self.adaptive_threshold and delta.max() > 0:
            otsu_val, _ = cv2.threshold(delta, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            # Floor at the configured diff_threshold so Otsu can't classify
            # ordinary sensor noise on a static scene as widespread motion.
            threshold = max(otsu_val, float(self.diff_threshold))
        else:
            threshold = float(self.diff_threshold)
        _, mask = cv2.threshold(delta, threshold, 255, cv2.THRESH_BINARY)
        return mask

    def _process_optical_flow(self, gray: np.ndarray) -> np.ndarray:
        if self._prev_gray is None:
            return np.zeros_like(gray)
        flow = cv2.calcOpticalFlowFarneback(
            self._prev_gray,
            gray,
            np.zeros((*gray.shape[:2], 2), dtype=np.float32),
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
        """Morphological open+dilate, then connected-component area filtering.

        The morphology removes speckle noise and fills small gaps. The
        connected-component pass then drops any *remaining* blob smaller than
        ``min_area`` entirely — this is what makes ``min_area`` meaningful for
        the motion *score*, not just for downstream ROI boxes (previously this
        parameter was accepted but never actually applied to the mask/score).
        """
        if mask.max() == 0:
            return mask
        opened = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self._kernel, iterations=1)
        dilated = cv2.dilate(opened, self._kernel, iterations=2)

        if self.min_area <= 1 or dilated.max() == 0:
            return dilated

        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(dilated, connectivity=8)
        if num_labels <= 1:
            return dilated

        areas = stats[1:, cv2.CC_STAT_AREA]  # exclude background label 0
        keep = np.where(areas >= self.min_area)[0] + 1
        if len(keep) == num_labels - 1:
            return dilated  # nothing to remove

        filtered = np.isin(labels, keep).astype(np.uint8) * 255
        return filtered


def select_best_algorithm(
    video_path: str,
    *,
    sample_frames: int = 40,
    sample_stride: int = 3,
) -> str:
    """Pre-scan a video and heuristically pick the best motion algorithm.

    Decodes a small, evenly-strided sample of frames (cheap relative to full
    analysis) and measures two signals:

    * **Illumination stability** — the standard deviation of mean frame
      brightness across the sample. High values indicate gradual lighting
      change (e.g. sun through a window, flickering fluorescents), which
      ``mog2``'s adaptive background model handles far better than a naive
      frame-to-frame diff.
    * **Inter-frame noise** — the median absolute frame-to-frame pixel delta
      on a *static* reference region proxy (here, the whole frame, since exam
      halls are mostly static). Low, stable noise with only localised bursts
      of change favours cheap ``frame_diff``; noisier or more complex/textured
      scenes favour ``optical_flow``, which measures true motion vectors
      rather than raw pixel deltas and is more robust to compression noise.

    Args:
        video_path: Path to the video file.
        sample_frames: Number of frames to sample.
        sample_stride: Only decode every Nth frame while sampling (keeps the
            pre-scan itself fast even on long videos).

    Returns:
        One of :data:`SUPPORTED_ALGORITHMS`. Falls back to ``mog2`` (the safest
        general-purpose default) if the video cannot be pre-scanned at all.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        logger.warning("select_best_algorithm: cannot open %s; defaulting to mog2", video_path)
        return MOG2

    brightness_samples: list[float] = []
    noise_samples: list[float] = []
    prev_gray: np.ndarray | None = None
    collected = 0

    try:
        frame_index = 0
        while collected < sample_frames:
            ok, frame = cap.read()
            if not ok or frame is None:
                break
            if frame_index % sample_stride == 0:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                brightness_samples.append(float(np.mean(gray.astype(np.uint8))))
                if prev_gray is not None:
                    delta = cv2.absdiff(prev_gray, gray)
                    noise_samples.append(float(np.median(delta.astype(np.uint8))))
                prev_gray = gray
                collected += 1
            frame_index += 1
    finally:
        cap.release()

    if len(brightness_samples) < 3:
        logger.info("select_best_algorithm: insufficient frames sampled; defaulting to mog2")
        return MOG2

    illumination_std = float(np.std(brightness_samples))
    noise_level = float(np.median(noise_samples)) if noise_samples else 0.0

    if illumination_std > 6.0:
        chosen = MOG2
        reason = f"unstable illumination (std={illumination_std:.2f})"
    elif noise_level > 4.0:
        chosen = OPTICAL_FLOW
        reason = f"high inter-frame noise/texture (median delta={noise_level:.2f})"
    else:
        chosen = FRAME_DIFF
        reason = f"stable lighting and low noise (std={illumination_std:.2f}, delta={noise_level:.2f})"

    logger.info("select_best_algorithm: chose '%s' — %s", chosen, reason)
    return chosen
