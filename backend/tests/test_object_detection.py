"""Tests for the YOLO object detection wrapper.

The real ``ultralytics`` package (and its ``torch`` dependency) is a heavy,
optional runtime dependency the pipeline is explicitly designed to degrade
gracefully without (see ``ObjectDetector``'s docstring). These tests exercise
all the detector's *logic* — label mapping, caching, batching, custom-model
hooks, confidence filtering — against a lightweight fake model, so none of it
requires actual model weights or GPU/CPU inference to be installed.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from app.services.object_detection import (
    _DEFAULT_CLASS_MAP,
    _DEFAULT_PROHIBITED_LABELS,
    ObjectDetector,
    _average_hash,
)


class _FakeBox:
    """Mimics one ultralytics ``Boxes`` row: .cls, .conf, .xyxy (tensor-like,
    i.e. supports ``.tolist()`` the same way a real torch tensor does)."""

    def __init__(self, cls_id: int, conf: float, xyxy: tuple[float, float, float, float]) -> None:
        self.cls = [cls_id]
        self.conf = [conf]
        self.xyxy = [np.array(xyxy, dtype=float)]


class _FakeResult:
    def __init__(self, names: dict[int, str], boxes: list[_FakeBox]) -> None:
        self.names = names
        self.boxes = boxes


class _FakeModel:
    """Mimics ``ultralytics.YOLO``'s callable ``.predict()`` interface.

    ``responses`` is a list (one entry per call to ``.predict``) of lists (one
    entry per input frame) of ``_FakeResult``.
    """

    def __init__(self, responses: list[list[_FakeResult]], names: dict[int, str]) -> None:
        self._responses = list(responses)
        self.names = names
        self.calls: list[int] = []  # records batch sizes passed to predict()

    def predict(self, frames, *, conf, iou, device, verbose):
        self.calls.append(len(frames))
        if not self._responses:
            return [_FakeResult(self.names, []) for _ in frames]
        return self._responses.pop(0)


def _blank_frame(seed: int = 0, size: int = 16) -> np.ndarray:
    """A tiny distinct frame so perceptual hashes differ between calls."""
    rng = np.random.default_rng(seed)
    return rng.integers(0, 255, (size, size, 3), dtype=np.uint8)


def _detector(**kwargs) -> ObjectDetector:
    kwargs.setdefault("device", "cpu")
    kwargs.setdefault("confidence", 0.3)
    kwargs.setdefault("iou", 0.5)
    return ObjectDetector(enabled=True, **kwargs)


def _install_fake_model(detector: ObjectDetector, model: _FakeModel) -> None:
    detector._model = model  # bypass lazy YOLO import entirely


# ------------------------------------------------------------- label mapping
def test_book_is_not_relabelled_to_paper() -> None:
    """The critical, explicitly-required fix: COCO's 'book' class must never
    be silently reported as 'paper' — that overstates the model's actual
    capability (COCO has no loose-paper/chit class at all)."""
    assert _DEFAULT_CLASS_MAP["book"] == "book"
    assert "paper" not in _DEFAULT_CLASS_MAP.values()


def test_book_is_flagged_as_heuristic_not_confident() -> None:
    detector = _detector()
    names = {0: "book"}
    model = _FakeModel([[_FakeResult(names, [_FakeBox(0, 0.9, (10, 10, 50, 50))])]], names)
    _install_fake_model(detector, model)

    detections = detector.detect(_blank_frame())
    assert len(detections) == 1
    det = detections[0]
    assert det.label == "book"
    assert det.heuristic is True
    assert det.prohibited is True  # still a (heuristic) prohibited signal


def test_phone_is_not_heuristic() -> None:
    detector = _detector()
    names = {0: "cell phone"}
    model = _FakeModel([[_FakeResult(names, [_FakeBox(0, 0.9, (0, 0, 10, 10))])]], names)
    _install_fake_model(detector, model)

    detections = detector.detect(_blank_frame())
    assert detections[0].label == "phone"
    assert detections[0].heuristic is False
    assert detections[0].prohibited is True


def test_irrelevant_class_is_filtered_out() -> None:
    detector = _detector()
    names = {0: "car"}  # not in the relevant label set
    model = _FakeModel([[_FakeResult(names, [_FakeBox(0, 0.9, (0, 0, 10, 10))])]], names)
    _install_fake_model(detector, model)

    assert detector.detect(_blank_frame()) == []


def test_low_confidence_detection_is_filtered() -> None:
    detector = _detector(confidence=0.5)
    names = {0: "person"}
    model = _FakeModel([[_FakeResult(names, [_FakeBox(0, 0.1, (0, 0, 10, 10))])]], names)
    _install_fake_model(detector, model)

    assert detector.detect(_blank_frame()) == []


# ---------------------------------------------------------------- batching
def test_detect_batch_makes_a_single_predict_call() -> None:
    detector = _detector()
    names = {0: "person"}
    frames = [_blank_frame(i) for i in range(4)]
    responses = [[_FakeResult(names, []) for _ in frames]]
    model = _FakeModel(responses, names)
    _install_fake_model(detector, model)

    results = detector.detect_batch(frames)
    assert len(results) == 4
    assert model.calls == [4]  # one call, batch size 4 — not four separate calls


def test_detect_batch_empty_input() -> None:
    detector = _detector()
    assert detector.detect_batch([]) == []


# ------------------------------------------------------------------- caching
def test_repeated_identical_frame_hits_cache() -> None:
    detector = _detector(cache_size=16)
    names = {0: "person"}
    frame = _blank_frame(42)
    model = _FakeModel(
        [[_FakeResult(names, [_FakeBox(0, 0.9, (0, 0, 5, 5))])]],
        names,
    )
    _install_fake_model(detector, model)

    first = detector.detect(frame)
    second = detector.detect(frame)  # identical frame -> should hit cache
    assert len(first) == 1
    assert first == second
    assert model.calls == [1]  # only ONE real inference call was made
    stats = detector.cache_stats()
    assert stats["cache_hits"] == 1
    assert stats["cache_misses"] == 1


def test_cache_disabled_when_size_zero() -> None:
    detector = _detector(cache_size=0)
    names = {0: "person"}
    frame = _blank_frame(7)
    model = _FakeModel(
        [
            [_FakeResult(names, [])],
            [_FakeResult(names, [])],
        ],
        names,
    )
    _install_fake_model(detector, model)

    detector.detect(frame)
    detector.detect(frame)
    assert model.calls == [1, 1]  # cache disabled -> inference runs every time


def test_average_hash_is_stable_and_distinguishes_frames() -> None:
    frame_a = _blank_frame(1)
    frame_b = _blank_frame(1)  # same seed -> identical content
    frame_c = _blank_frame(2)  # different seed -> different content

    assert _average_hash(frame_a) == _average_hash(frame_b)
    assert _average_hash(frame_a) != _average_hash(frame_c)


# --------------------------------------------------------------- custom hook
def test_custom_label_map_overrides_defaults(tmp_path: Path) -> None:
    label_map_path = tmp_path / "labels.json"
    label_map_path.write_text(
        json.dumps(
            {
                "class_map": {"chit": "paper_note"},
                "prohibited_labels": ["paper_note", "phone"],
                "relevant_labels": ["paper_note", "phone", "person"],
            }
        )
    )
    detector = ObjectDetector(
        enabled=True,
        custom_model_path="fake/weights.pt",
        custom_label_map_path=str(label_map_path),
    )
    assert detector.is_custom_model is True
    assert detector.class_map["chit"] == "paper_note"
    assert "paper_note" in detector.prohibited_labels

    names = {0: "chit"}
    model = _FakeModel([[_FakeResult(names, [_FakeBox(0, 0.9, (0, 0, 5, 5))])]], names)
    _install_fake_model(detector, model)

    detections = detector.detect(_blank_frame())
    assert len(detections) == 1
    assert detections[0].label == "paper_note"
    assert detections[0].prohibited is True
    # A custom model's own class is a direct detection, not COCO's "book"
    # heuristic proxy.
    assert detections[0].heuristic is False


def test_missing_label_map_file_falls_back_to_defaults(tmp_path: Path) -> None:
    detector = ObjectDetector(
        enabled=True, custom_label_map_path=str(tmp_path / "does_not_exist.json")
    )
    assert detector.class_map == _DEFAULT_CLASS_MAP
    assert detector.prohibited_labels == _DEFAULT_PROHIBITED_LABELS


def test_disabled_detector_returns_empty_without_loading_model() -> None:
    detector = ObjectDetector(enabled=False)
    assert detector.available is False
    assert detector.detect(_blank_frame()) == []
    assert detector.detect_batch([_blank_frame()]) == [[]]


# --------------------------------------------------------------- GPU OOM path
def test_cuda_oom_falls_back_to_cpu_and_retries() -> None:
    detector = _detector(device="cuda:0")
    detector.device = "cuda:0"
    names = {0: "person"}

    call_count = {"n": 0}

    class _OomThenOkModel:
        names = {0: "person"}

        def predict(self, frames, *, conf, iou, device, verbose):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("CUDA out of memory. Tried to allocate 2.00 GiB")
            return [_FakeResult(names, []) for _ in frames]

    _install_fake_model(detector, _OomThenOkModel())
    detections = detector.detect(_blank_frame())
    assert detections == []  # the (empty) result from the successful CPU retry
    assert detector.device == "cpu"  # self-healed for subsequent calls
    assert call_count["n"] == 2  # first call OOM'd, second (retry) succeeded


@pytest.mark.parametrize("bad_frame_count", [1, 3])
def test_non_oom_inference_error_returns_empty_without_raising(bad_frame_count: int) -> None:
    detector = _detector()

    class _AlwaysFailsModel:
        names = {0: "person"}

        def predict(self, frames, *, conf, iou, device, verbose):
            raise ValueError("corrupt model state")

    _install_fake_model(detector, _AlwaysFailsModel())
    frames = [_blank_frame(i) for i in range(bad_frame_count)]
    results = detector.detect_batch(frames)
    assert results == [[] for _ in frames]
