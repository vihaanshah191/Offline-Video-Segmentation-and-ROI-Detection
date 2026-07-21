"""Region-of-interest detection from a binary motion mask.

Given a foreground mask, contours are extracted, tiny/noise contours are
discarded, overlapping bounding boxes are merged into clean ROI regions, and
the result is capped for performance safety.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from app.core.logging_config import get_logger
from app.utils.geometry import Box, clamp_box, merge_boxes

logger = get_logger(__name__)


@dataclass(slots=True)
class ROIBox:
    """A region of interest with a motion-based confidence score."""

    x: int
    y: int
    w: int
    h: int
    confidence: float  # 0..1, fraction of the box that is in motion

    def as_tuple(self) -> Box:
        return (self.x, self.y, self.w, self.h)


class ROIDetector:
    """Extract merged ROI boxes from motion masks."""

    def __init__(
        self,
        *,
        min_area: int = 800,
        min_area_fraction: float = 0.0,
        merge_iou: float = 0.2,
        max_boxes: int = 25,
        max_raw_contours: int = 200,
    ) -> None:
        """Create an ROI detector.

        Args:
            min_area: Minimum contour area (px) to keep (noise/tiny-motion
                filter). Used when ``min_area_fraction`` is 0.
            min_area_fraction: Minimum contour area as a fraction of the frame
                area (0..1). When > 0, this takes precedence over the fixed
                ``min_area`` and makes noise filtering resolution-relative —
                the same fraction behaves consistently whether the source is
                480p or 4K, whereas a fixed pixel count does not (800px^2 is
                tiny at 4K but comparatively large at 480p).
            merge_iou: IoU threshold above which overlapping boxes are merged.
            max_boxes: Hard cap on returned boxes (largest kept).
            max_raw_contours: Performance guard — if a pathologically noisy
                frame produces more raw (pre-merge) contours than this, only
                the largest ``max_raw_contours`` are kept before the O(n^2)
                merge pass runs, bounding worst-case per-frame cost.
        """
        self.min_area = min_area
        self.min_area_fraction = min_area_fraction
        self.merge_iou = merge_iou
        self.max_boxes = max_boxes
        self.max_raw_contours = max_raw_contours

    def _effective_min_area(self, width: int, height: int) -> float:
        if self.min_area_fraction > 0:
            return self.min_area_fraction * width * height
        return float(self.min_area)

    def detect(self, mask: np.ndarray) -> list[ROIBox]:
        """Return merged, noise-filtered ROI boxes for a motion ``mask``."""
        if mask is None or mask.max() == 0:
            return []

        height, width = mask.shape[:2]
        min_area = self._effective_min_area(width, height)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        candidates: list[tuple[float, Box]] = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < min_area:
                continue
            x, y, w, h = cv2.boundingRect(contour)
            candidates.append((area, clamp_box((x, y, w, h), width, height)))

        if not candidates:
            return []

        if len(candidates) > self.max_raw_contours:
            logger.debug(
                "Frame produced %d raw contours (> %d cap); keeping the largest",
                len(candidates),
                self.max_raw_contours,
            )
            candidates.sort(key=lambda c: c[0], reverse=True)
            candidates = candidates[: self.max_raw_contours]

        raw: list[Box] = [box for _, box in candidates]
        merged = merge_boxes(raw, iou_threshold=self.merge_iou)

        boxes: list[ROIBox] = []
        for box in merged:
            x, y, w, h = clamp_box(box, width, height)
            region = mask[y : y + h, x : x + w]
            confidence = (
                float(np.count_nonzero(region)) / float(region.size)
                if region.size
                else 0.0
            )
            boxes.append(ROIBox(x=x, y=y, w=w, h=h, confidence=round(confidence, 4)))

        # Keep the largest boxes if we exceeded the cap.
        boxes.sort(key=lambda b: b.w * b.h, reverse=True)
        return boxes[: self.max_boxes]
