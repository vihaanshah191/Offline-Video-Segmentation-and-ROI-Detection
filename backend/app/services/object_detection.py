"""YOLO object detection wrapper.

Wraps Ultralytics YOLOv11 with graceful degradation: if the ``ultralytics``
package or model weights are unavailable (e.g. fully offline CI), the detector
disables itself and returns no detections instead of crashing the pipeline.

Only a curated subset of COCO classes relevant to exam-hall monitoring is
reported.

**Known limitation — please read before trusting "prohibited" flags in a
demo or production context:** the pretrained COCO checkpoint YOLOv11 ships
with has **no class for loose paper, hand-written chits, or exam-specific
contraband**. Earlier revisions of this module worked around that gap by
silently relabelling COCO's ``book`` class as ``"paper"``. That was
misleading — a book is not a chit, and reporting it as one overstates the
system's actual capability to a judge or an operator relying on this signal.

This module now reports ``book`` as ``book``, flags it only as a *heuristic,
low-confidence* signal (not a confident "prohibited item found" claim), and
exposes a first-class hook (``custom_yolo_model_path`` /
``custom_label_map_path``) for plugging in a model fine-tuned on an
exam-specific dataset (loose paper, folded notes, smartwatches, ...), which is
the only way to close this gap properly. See ``docs/SYSTEM_DESIGN.md`` →
"Known Limitations" → "Object Detection" for the full discussion, and
``docs/SYSTEM_DESIGN.md`` → "Future Improvements" for the fine-tuning recipe.
"""
from __future__ import annotations

import json
import threading
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from app.core.config import settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# COCO label -> normalised label used across the app. Every entry here is an
# HONEST 1:1 (or many:1 for genuine synonyms like backpack/handbag/suitcase ->
# bag) rename — nothing is mapped to a concept COCO cannot actually see.
_DEFAULT_CLASS_MAP: dict[str, str] = {
    "cell phone": "phone",
    "book": "book",  # NOT relabelled to "paper" — see module docstring.
    "backpack": "bag",
    "handbag": "bag",
    "suitcase": "bag",
    "person": "person",
    "bottle": "bottle",
    "laptop": "laptop",
}

# Labels treated as a *heuristic* prohibited-item signal. "book" is included
# only as a low-confidence proxy (a book might contain notes; it might also
# just be a book) — the frontend/report should present it with appropriately
# hedged language, not as a confirmed violation. "phone" is the one genuinely
# reliable signal COCO gives us for this use case.
_DEFAULT_PROHIBITED_LABELS: set[str] = {"phone", "book"}

# Which normalised labels we keep at all (everything else is discarded).
_DEFAULT_RELEVANT_LABELS: set[str] = {"phone", "book", "bag", "person", "bottle", "laptop"}

# Backwards-compatible module-level aliases (some call sites / tests import
# these directly). They reflect the *default* built-in model's label set; an
# ``ObjectDetector`` configured with a custom model may use a different set,
# available on the instance as ``.class_map`` / ``.prohibited_labels`` /
# ``.relevant_labels``.
_CLASS_ALIASES = _DEFAULT_CLASS_MAP
PROHIBITED_LABELS = _DEFAULT_PROHIBITED_LABELS
RELEVANT_LABELS = _DEFAULT_RELEVANT_LABELS

_HASH_SIZE = 8  # 8x8 average-hash -> 64-bit perceptual fingerprint


@dataclass(slots=True)
class ObjectDetection:
    """A single detected object."""

    label: str
    confidence: float
    x: int
    y: int
    w: int
    h: int
    # Whether this label is only a heuristic proxy (e.g. "book" standing in
    # for "possible prohibited material") rather than a direct, reliable
    # detection of the target concept. Surfaced so the frontend/report can
    # word the finding appropriately instead of overclaiming.
    heuristic: bool = False
    prohibited: bool = False


def _average_hash(frame: np.ndarray) -> int:
    """Cheap perceptual hash used as a cache key for (near-)duplicate frames.

    An exact byte-equality cache would almost never hit on real video (frames
    are rarely bit-identical even in static scenes, due to sensor/compression
    noise). An 8x8 average hash is invariant to that noise while still being
    sensitive to genuine content changes, and costs well under a millisecond.
    """
    small = cv2.resize(frame, (_HASH_SIZE, _HASH_SIZE), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY) if small.ndim == 3 else small
    mean = gray.mean()
    bits = (gray > mean).flatten()
    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)
    return value


class ObjectDetector:
    """Lazy-loading YOLOv11 detector with a safe no-op fallback.

    Supports plugging in a custom / fine-tuned model via
    ``custom_model_path`` (or ``settings.custom_yolo_model_path``) together
    with an optional label-map JSON file (``custom_label_map_path`` /
    ``settings.custom_label_map_path``) of the form::

        {
          "class_map": {"chit": "paper_note", "smartwatch": "watch"},
          "prohibited_labels": ["paper_note", "phone", "watch"],
          "relevant_labels": ["paper_note", "phone", "watch", "person"]
        }

    This is the intended extension point for closing the "loose paper" gap
    described in the module docstring: train/fine-tune a YOLO model on an
    exam-specific dataset, point ``custom_yolo_model_path`` at the resulting
    weights, and supply a label map — no other code changes required.
    """

    def __init__(
        self,
        model_name: str | None = None,
        *,
        confidence: float | None = None,
        iou: float | None = None,
        device: str | None = None,
        enabled: bool | None = None,
        custom_model_path: str | None = None,
        custom_label_map_path: str | None = None,
        cache_size: int | None = None,
    ) -> None:
        custom_path = custom_model_path or settings.custom_yolo_model_path
        self.model_name = custom_path or model_name or settings.yolo_model
        self.is_custom_model = bool(custom_path)

        self.confidence = confidence if confidence is not None else settings.yolo_confidence
        self.iou = iou if iou is not None else settings.yolo_iou
        self.device = self._resolve_device(device or settings.yolo_device)
        self.enabled = settings.enable_object_detection if enabled is None else enabled

        self.class_map, self.prohibited_labels, self.relevant_labels = self._load_label_config(
            custom_label_map_path or settings.custom_label_map_path
        )

        self._model = None
        self._load_failed = False
        self._lock = threading.Lock()  # guards lazy model load from concurrent threads

        cache_capacity = settings.yolo_cache_size if cache_size is None else cache_size
        self._cache_capacity = max(0, cache_capacity)
        self._cache: OrderedDict[int, list[ObjectDetection]] = OrderedDict()
        self.cache_hits = 0
        self.cache_misses = 0

    # ------------------------------------------------------------------ public
    @property
    def available(self) -> bool:
        """Whether detection can actually run (enabled and model loadable)."""
        if not self.enabled or self._load_failed:
            return False
        return self._ensure_model() is not None

    def detect(self, frame: np.ndarray) -> list[ObjectDetection]:
        """Run detection on a single BGR frame (thin wrapper over :meth:`detect_batch`)."""
        results = self.detect_batch([frame])
        return results[0] if results else []

    def detect_batch(self, frames: list[np.ndarray]) -> list[list[ObjectDetection]]:
        """Run detection on a batch of BGR frames in a single inference call.

        Batching amortises Python/CUDA-launch overhead across frames instead
        of paying it once per frame, which matters when a pipeline run needs
        detections on several representative frames per activity segment.
        Frames that hit the perceptual-hash cache are skipped from the actual
        model call entirely.

        Returns:
            A list parallel to ``frames``, each entry the detections for that
            frame. Returns an all-empty result (never raises) if detection is
            disabled/unavailable.
        """
        if not frames:
            return []

        model = self._ensure_model()
        if model is None:
            return [[] for _ in frames]

        results: list[list[ObjectDetection] | None] = [None] * len(frames)
        cache_keys: list[int | None] = [None] * len(frames)

        to_infer_indices: list[int] = []
        to_infer_frames: list[np.ndarray] = []

        if self._cache_capacity > 0:
            for i, frame in enumerate(frames):
                key = _average_hash(frame)
                cache_keys[i] = key
                cached = self._cache.get(key)
                if cached is not None:
                    self._cache.move_to_end(key)
                    results[i] = cached
                    self.cache_hits += 1
                else:
                    to_infer_indices.append(i)
                    to_infer_frames.append(frame)
        else:
            to_infer_indices = list(range(len(frames)))
            to_infer_frames = list(frames)

        if to_infer_frames:
            self.cache_misses += len(to_infer_frames)
            inferred = self._run_inference(model, to_infer_frames)
            for idx, dets in zip(to_infer_indices, inferred, strict=True):
                results[idx] = dets
                key = cache_keys[idx]
                if key is not None and self._cache_capacity > 0:
                    self._cache[key] = dets
                    self._cache.move_to_end(key)
                    while len(self._cache) > self._cache_capacity:
                        self._cache.popitem(last=False)

        return [r if r is not None else [] for r in results]

    def cache_stats(self) -> dict[str, int]:
        """Return cache hit/miss counters for this detector instance (perf/logging)."""
        return {
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "cache_size": len(self._cache),
        }

    # ----------------------------------------------------------------- helpers
    def _run_inference(
        self, model, frames: list[np.ndarray], *, _retried: bool = False
    ) -> list[list[ObjectDetection]]:
        """Run the actual YOLO forward pass, with CUDA-OOM self-healing.

        On a CUDA out-of-memory error the detector permanently downgrades
        itself to CPU (rather than dropping every subsequent frame silently,
        which is what a bare try/except around a single-frame call would do)
        and retries the same batch once.
        """
        try:
            raw_results = model.predict(
                frames,
                conf=self.confidence,
                iou=self.iou,
                device=self.device,
                verbose=False,
            )
        except Exception as exc:  # noqa: BLE001 - never let inference kill the pipeline
            message = str(exc).lower()
            is_oom = "out of memory" in message or "cuda" in message and "memory" in message
            if is_oom and not _retried and self.device != "cpu":
                logger.warning(
                    "CUDA out of memory during YOLO inference; falling back to CPU "
                    "for the remainder of this run (was: %s)",
                    self.device,
                )
                self._free_cuda_memory()
                self.device = "cpu"
                return self._run_inference(model, frames, _retried=True)
            logger.warning("YOLO inference failed on a batch of %d frame(s): %s", len(frames), exc)
            return [[] for _ in frames]

        return [self._extract_detections(result) for result in raw_results]

    def _free_cuda_memory(self) -> None:
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:  # noqa: BLE001
            pass

    def _extract_detections(self, result) -> list[ObjectDetection]:
        names = result.names
        boxes = getattr(result, "boxes", None)
        if boxes is None:
            return []

        detections: list[ObjectDetection] = []
        for box in boxes:
            cls_id = int(box.cls[0])
            raw_label = names.get(cls_id, str(cls_id)) if isinstance(names, dict) else names[cls_id]
            label = self.class_map.get(raw_label)
            if label is None or label not in self.relevant_labels:
                continue
            conf = float(box.conf[0])
            # Defensive re-filter: some model/wrapper combinations do not
            # strictly enforce ``conf`` internally for every export format.
            if conf < self.confidence:
                continue
            x1, y1, x2, y2 = (float(v) for v in box.xyxy[0].tolist())
            detections.append(
                ObjectDetection(
                    label=label,
                    confidence=round(conf, 4),
                    x=int(x1),
                    y=int(y1),
                    w=int(x2 - x1),
                    h=int(y2 - y1),
                    heuristic=(label == "book" and not self.is_custom_model),
                    prohibited=label in self.prohibited_labels,
                )
            )
        return detections

    def _resolve_device(self, device: str) -> str:
        if device != "auto":
            return device
        try:
            import torch

            return "cuda:0" if torch.cuda.is_available() else "cpu"
        except Exception:  # noqa: BLE001
            return "cpu"

    def _load_label_config(
        self, label_map_path: str | None
    ) -> tuple[dict[str, str], set[str], set[str]]:
        """Load a custom label-map JSON, falling back to the built-in defaults."""
        if not label_map_path:
            return dict(_DEFAULT_CLASS_MAP), set(_DEFAULT_PROHIBITED_LABELS), set(_DEFAULT_RELEVANT_LABELS)

        path = Path(label_map_path)
        try:
            data = json.loads(path.read_text())
            class_map = {**_DEFAULT_CLASS_MAP, **data.get("class_map", {})}
            prohibited = set(data.get("prohibited_labels", _DEFAULT_PROHIBITED_LABELS))
            relevant = set(data.get("relevant_labels", set(class_map.values()) | prohibited))
            logger.info("Loaded custom object-detection label map from %s", path)
            return class_map, prohibited, relevant
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            logger.warning(
                "Could not load custom label map at %s (%s); using built-in defaults",
                label_map_path,
                exc,
            )
            return dict(_DEFAULT_CLASS_MAP), set(_DEFAULT_PROHIBITED_LABELS), set(_DEFAULT_RELEVANT_LABELS)

    def _ensure_model(self):
        if self._model is not None or self._load_failed or not self.enabled:
            return self._model
        with self._lock:
            # Re-check inside the lock: another thread may have loaded (or
            # failed to load) the model while we were waiting.
            if self._model is not None or self._load_failed:
                return self._model
            try:
                from ultralytics import YOLO

                logger.info(
                    "Loading %s YOLO model '%s' on device '%s'",
                    "custom" if self.is_custom_model else "default",
                    self.model_name,
                    self.device,
                )
                self._model = YOLO(self.model_name)
                return self._model
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Object detection disabled – could not load YOLO model '%s': %s",
                    self.model_name,
                    exc,
                )
                self._load_failed = True
                return None
