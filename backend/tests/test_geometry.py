"""Unit tests for geometry helpers."""
from __future__ import annotations

from app.utils.geometry import clamp_box, iou, merge_boxes, union_box


def test_iou_identical_boxes() -> None:
    assert iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0


def test_iou_disjoint_boxes() -> None:
    assert iou((0, 0, 10, 10), (100, 100, 10, 10)) == 0.0


def test_iou_partial_overlap() -> None:
    # Half-overlap along x: intersection 5x10=50, union=150 -> 1/3.
    assert abs(iou((0, 0, 10, 10), (5, 0, 10, 10)) - (50 / 150)) < 1e-6


def test_union_box() -> None:
    assert union_box((0, 0, 10, 10), (20, 20, 10, 10)) == (0, 0, 30, 30)


def test_merge_boxes_combines_overlapping() -> None:
    boxes = [(0, 0, 10, 10), (5, 5, 10, 10), (100, 100, 5, 5)]
    merged = merge_boxes(boxes, iou_threshold=0.1)
    assert len(merged) == 2  # two overlapping merge, the far one stays separate


def test_merge_boxes_keeps_disjoint() -> None:
    boxes = [(0, 0, 5, 5), (50, 50, 5, 5)]
    merged = merge_boxes(boxes, iou_threshold=0.2)
    assert len(merged) == 2


def test_clamp_box_within_frame() -> None:
    assert clamp_box((-5, -5, 100, 100), 50, 40) == (0, 0, 50, 40)
