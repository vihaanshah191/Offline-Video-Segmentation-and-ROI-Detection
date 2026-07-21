"""Health and system-info endpoints."""
from __future__ import annotations

from fastapi import APIRouter

from app.core.config import settings
from app.services.object_detection import ObjectDetector
from app.services.video_service import VideoService
from app.utils.video_io import ffmpeg_available

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict:
    """Liveness probe."""
    return {"status": "ok", "app": settings.app_name, "version": settings.app_version}


@router.get("/system")
def system_info() -> dict:
    """Report capabilities of the running backend."""
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
    }
