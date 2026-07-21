"""Application configuration.

Centralised, typed settings loaded from environment variables (and an optional
``.env`` file). Every tunable knob of the pipeline lives here so behaviour can be
changed without touching business logic.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repository root ( .../backend/app/core/config.py -> repo root is 3 parents up
# from the ``backend`` package directory).
BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    """Strongly typed application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="",
        extra="ignore",
    )

    # ----------------------------------------------------------------- general
    app_name: str = "Offline Video Segmentation & ROI Detection"
    app_version: str = "1.0.0"
    debug: bool = Field(default=False)
    api_prefix: str = "/api"
    log_level: str = "INFO"

    # CORS – comma separated list of allowed origins.
    cors_origins: str = "http://localhost:5173,http://localhost:3000,http://localhost:8080"

    # ---------------------------------------------------------------- database
    database_url: str = f"sqlite:///{REPO_ROOT / 'storage' / 'app.db'}"

    # ------------------------------------------------------------------ storage
    storage_dir: Path = REPO_ROOT / "storage"
    videos_dir: Path = REPO_ROOT / "storage" / "videos"
    clips_dir: Path = REPO_ROOT / "storage" / "clips"
    heatmaps_dir: Path = REPO_ROOT / "storage" / "heatmaps"
    thumbnails_dir: Path = REPO_ROOT / "storage" / "thumbnails"
    reports_dir: Path = REPO_ROOT / "storage" / "reports"

    max_upload_mb: int = 4096  # 4 GB – supports 2 hour 1080p recordings.
    allowed_extensions: str = "mp4,avi,mov,mkv"

    # ------------------------------------------------------------ motion / ROI
    # Default motion algorithm: one of ``mog2``, ``frame_diff``, ``optical_flow``.
    default_motion_algorithm: str = "mog2"
    # Process every Nth frame during analysis (>=1). Larger = faster, coarser.
    frame_sample_step: int = 2
    # Minimum contour area (px) to be considered real motion (noise filter).
    min_motion_area: int = 800
    # Motion score (fraction of pixels in motion) above which a frame is "active".
    motion_threshold: float = 0.012
    # Gap (seconds) of no-motion tolerated before a segment is closed.
    segment_merge_gap_sec: float = 1.5
    # Minimum duration (seconds) for a segment to be kept.
    min_segment_duration_sec: float = 1.0
    # IoU above which two ROI boxes are merged.
    roi_merge_iou: float = 0.2

    # -------------------------------------------------------------- yolo model
    yolo_model: str = "yolo11n.pt"
    yolo_confidence: float = 0.35
    yolo_iou: float = 0.5
    # Force device: "auto" (cuda if available else cpu), "cpu", "cuda", "cuda:0"...
    yolo_device: str = "auto"
    # Enable/disable object detection entirely (useful for tests / no weights).
    enable_object_detection: bool = True

    # ------------------------------------------------------------------ worker
    # ``thread`` runs the pipeline in a background thread (no external broker).
    # ``celery`` offloads to a Celery worker (requires Redis).
    task_backend: str = "thread"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    @property
    def allowed_extension_set(self) -> set[str]:
        return {e.strip().lower().lstrip(".") for e in self.allowed_extensions.split(",") if e.strip()}

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def ensure_directories(self) -> None:
        """Create every storage directory if it does not yet exist."""
        for directory in (
            self.storage_dir,
            self.videos_dir,
            self.clips_dir,
            self.heatmaps_dir,
            self.thumbnails_dir,
            self.reports_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Return a cached ``Settings`` instance (dependency-injection friendly)."""
    settings = Settings()
    settings.ensure_directories()
    return settings


settings = get_settings()
