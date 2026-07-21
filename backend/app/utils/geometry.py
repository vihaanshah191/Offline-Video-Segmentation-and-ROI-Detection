"""Geometry helpers for bounding-box manipulation.

Boxes are represented as ``(x, y, w, h)`` integer tuples in pixel coordinates.
"""
from __future__ import annotations

from typing import Iterable

Box = tuple[int, int, int, int]


def box_area(box: Box) -> int:
    """Return the area of a box."""
    _, _, w, h = box
    return max(0, w) * max(0, h)


def iou(a: Box, b: Box) -> float:
    """Intersection-over-union of two boxes (0..1)."""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ax2, ay2 = ax + aw, ay + ah
    bx2, by2 = bx + bw, by + bh

    inter_x1 = max(ax, bx)
    inter_y1 = max(ay, by)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)

    inter_w = max(0, inter_x2 - inter_x1)
    inter_h = max(0, inter_y2 - inter_y1)
    inter = inter_w * inter_h
    if inter == 0:
        return 0.0

    union = box_area(a) + box_area(b) - inter
    return inter / union if union > 0 else 0.0


def union_box(a: Box, b: Box) -> Box:
    """Return the smallest box containing both ``a`` and ``b``."""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    x1 = min(ax, bx)
    y1 = min(ay, by)
    x2 = max(ax + aw, bx + bw)
    y2 = max(ay + ah, by + bh)
    return (x1, y1, x2 - x1, y2 - y1)


def merge_boxes(boxes: Iterable[Box], iou_threshold: float = 0.2) -> list[Box]:
    """Greedily merge overlapping boxes.

    Two boxes are merged when their IoU exceeds ``iou_threshold``. The process
    repeats until no further merges are possible, so chains of overlapping
    regions collapse into a single bounding box.

    Args:
        boxes: Iterable of ``(x, y, w, h)`` boxes.
        iou_threshold: Minimum IoU for two boxes to be merged.

    Returns:
        A list of merged boxes.
    """
    result: list[Box] = list(boxes)
    merged = True
    while merged:
        merged = False
        output: list[Box] = []
        while result:
            current = result.pop()
            i = 0
            while i < len(result):
                if iou(current, result[i]) >= iou_threshold:
                    current = union_box(current, result.pop(i))
                    merged = True
                else:
                    i += 1
            output.append(current)
        result = output
    return result


def clamp_box(box: Box, width: int, height: int) -> Box:
    """Clamp a box so it stays within the ``width`` x ``height`` frame."""
    x, y, w, h = box
    x = max(0, min(x, width - 1))
    y = max(0, min(y, height - 1))
    w = max(1, min(w, width - x))
    h = max(1, min(h, height - y))
    return (x, y, w, h)
