"""YOLO object detection wrapper.

Wraps Ultralytics YOLOv11 with graceful degradation: if the ``ultralytics``
package or model weights are unavailable (e.g. fully offline CI), the detector
disables itself and returns no detections instead of crashing the pipeline.

Only a curated subset of COCO classes relevant to exam-hall monitoring is
reported. ``cell phone`` and ``book`` (a proxy for paper/chits) are flagged as
*prohibited*.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.core.config import settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# COCO label -> normalised label used across the app.
_CLASS_ALIASES: dict[str, str] = {
    "cell phone": "phone",
    "book": "paper",
    "backpack": "bag",
    "handbag": "bag",
    "suitcase": "bag",
    "person": "person",
    "bottle": "bottle",
    "laptop": "laptop",
}

# Labels considered prohibited in an examination context.
PROHIBITED_LABELS: set[str] = {"phone", "paper", "book"}

# Which normalised labels we keep.
RELEVANT_LABELS: set[str] = {"phone", "paper", "bag", "person", "bottle", "laptop"}


@dataclass(slots=True)
class ObjectDetection:
    """A single detected object."""

    label: str
    confidence: float
    x: int
    y: int
    w: int
    h: int

    @property
    def prohibited(self) -> bool:
        return self.label in PROHIBITED_LABELS


class ObjectDetector:
    """Lazy-loading YOLOv11 detector with a safe no-op fallback."""

    def __init__(
        self,
        model_name: str | None = None,
        *,
        confidence: float | None = None,
        iou: float | None = None,
        device: str | None = None,
        enabled: bool | None = None,
    ) -> None:
        self.model_name = model_name or settings.yolo_model
        self.confidence = confidence if confidence is not None else settings.yolo_confidence
        self.iou = iou if iou is not None else settings.yolo_iou
        self.device = self._resolve_device(device or settings.yolo_device)
        self.enabled = settings.enable_object_detection if enabled is None else enabled

        self._model = None
        self._load_failed = False

    # ------------------------------------------------------------------ public
    @property
    def available(self) -> bool:
        """Whether detection can actually run (enabled and model loadable)."""
        if not self.enabled or self._load_failed:
            return False
        return self._ensure_model() is not None

    def detect(self, frame: np.ndarray) -> list[ObjectDetection]:
        """Run detection on a single BGR frame.

        Returns an empty list if detection is disabled/unavailable.
        """
        model = self._ensure_model()
        if model is None:
            return []

        try:
            results = model.predict(
                frame,
                conf=self.confidence,
                iou=self.iou,
                device=self.device,
                verbose=False,
            )
        except Exception as exc:  # noqa: BLE001 - never let inference kill pipeline
            logger.warning("YOLO inference failed: %s", exc)
            return []

        detections: list[ObjectDetection] = []
        for result in results:
            names = result.names
            boxes = getattr(result, "boxes", None)
            if boxes is None:
                continue
            for box in boxes:
                cls_id = int(box.cls[0])
                raw_label = names.get(cls_id, str(cls_id)) if isinstance(names, dict) else names[cls_id]
                label = _CLASS_ALIASES.get(raw_label)
                if label is None or label not in RELEVANT_LABELS:
                    continue
                conf = float(box.conf[0])
                x1, y1, x2, y2 = (float(v) for v in box.xyxy[0].tolist())
                detections.append(
                    ObjectDetection(
                        label=label,
                        confidence=round(conf, 4),
                        x=int(x1),
                        y=int(y1),
                        w=int(x2 - x1),
                        h=int(y2 - y1),
                    )
                )
        return detections

    # ----------------------------------------------------------------- helpers
    def _resolve_device(self, device: str) -> str:
        if device != "auto":
            return device
        try:
            import torch

            return "cuda:0" if torch.cuda.is_available() else "cpu"
        except Exception:  # noqa: BLE001
            return "cpu"

    def _ensure_model(self):
        if self._model is not None or self._load_failed or not self.enabled:
            return self._model
        try:
            from ultralytics import YOLO

            logger.info("Loading YOLO model '%s' on device '%s'", self.model_name, self.device)
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
