"""Region-of-interest detection from a binary motion mask.

Given a foreground mask, contours are extracted, tiny/noise contours are
discarded, and overlapping bounding boxes are merged into clean ROI regions.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from app.utils.geometry import Box, clamp_box, merge_boxes


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
        merge_iou: float = 0.2,
        max_boxes: int = 25,
    ) -> None:
        """Create an ROI detector.

        Args:
            min_area: Minimum contour area (px) to keep (noise/tiny-motion filter).
            merge_iou: IoU threshold above which overlapping boxes are merged.
            max_boxes: Hard cap on returned boxes (largest kept).
        """
        self.min_area = min_area
        self.merge_iou = merge_iou
        self.max_boxes = max_boxes

    def detect(self, mask: np.ndarray) -> list[ROIBox]:
        """Return merged, noise-filtered ROI boxes for a motion ``mask``."""
        if mask is None or mask.max() == 0:
            return []

        height, width = mask.shape[:2]
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        raw: list[Box] = []
        for contour in contours:
            if cv2.contourArea(contour) < self.min_area:
                continue
            x, y, w, h = cv2.boundingRect(contour)
            raw.append(clamp_box((x, y, w, h), width, height))

        if not raw:
            return []

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
