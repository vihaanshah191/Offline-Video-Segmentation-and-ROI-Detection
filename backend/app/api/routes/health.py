"""Health and system-info endpoints."""
from __future__ import annotations

from fastapi import APIRouter

from app.core.config import settings
from app.core.logging_config import get_logger
from app.services.object_detection import ObjectDetector
from app.services.video_service import VideoService
from app.utils.video_io import ffmpeg_available

logger = get_logger(__name__)
router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict:
    """Liveness probe."""
    return {"status": "ok", "app": settings.app_name, "version": settings.app_version}


def _resource_usage() -> dict:
    """Host CPU/memory (and GPU, if CUDA is available) usage for the
    dashboard's live resource panel. Never raises: psutil/torch calls are
    best-effort telemetry, not load-bearing for anything else."""
    usage: dict = {
        "cpu_percent": None,
        "memory_percent": None,
        "memory_used_mb": None,
        "memory_total_mb": None,
        "gpu_name": None,
        "gpu_memory_used_mb": None,
        "gpu_memory_total_mb": None,
    }
    try:
        import psutil

        usage["cpu_percent"] = psutil.cpu_percent(interval=0.05)
        mem = psutil.virtual_memory()
        usage["memory_percent"] = mem.percent
        usage["memory_used_mb"] = round(mem.used / (1024 * 1024), 1)
        usage["memory_total_mb"] = round(mem.total / (1024 * 1024), 1)
    except Exception:  # noqa: BLE001
        logger.debug("psutil resource sampling unavailable", exc_info=True)

    try:
        import torch

        if torch.cuda.is_available():
            usage["gpu_name"] = torch.cuda.get_device_name(0)
            usage["gpu_memory_used_mb"] = round(torch.cuda.memory_allocated(0) / (1024 * 1024), 1)
            usage["gpu_memory_total_mb"] = round(
                torch.cuda.get_device_properties(0).total_memory / (1024 * 1024), 1
            )
    except Exception:  # noqa: BLE001
        logger.debug("CUDA GPU telemetry unavailable", exc_info=True)

    return usage


@router.get("/system")
def system_info() -> dict:
    """Report capabilities, model info and live resource usage of the running backend."""
    detector = ObjectDetector()
    try:
        import torch

        cuda = bool(torch.cuda.is_available())
    except Exception:  # noqa: BLE001
        cuda = False

    return {
        "version": settings.app_version,
        "ffmpeg": ffmpeg_available(),
        "cuda": cuda,
        "object_detection": detector.available,
        "default_motion_algorithm": settings.default_motion_algorithm,
        "free_disk_bytes": VideoService.free_disk_bytes(),
        "allowed_extensions": sorted(settings.allowed_extension_set),
        "yolo_model": settings.custom_yolo_model_path or settings.yolo_model,
        "yolo_device": settings.yolo_device,
        "task_backend": settings.task_backend,
        "resources": _resource_usage(),
    }
