"""Application configuration.

Centralised, typed settings loaded from environment variables (and an optional
``.env`` file). Every tunable knob of the pipeline lives here so behaviour can be
changed without touching business logic.

All numeric settings that have a meaningful valid range are constrained with
Pydantic ``Field`` bounds so a misconfigured environment fails fast at startup
with a clear error, instead of causing silent, hard-to-diagnose behaviour deep
inside the CV pipeline at analysis time.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator, model_validator
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
    app_version: str = "1.1.0"
    debug: bool = Field(default=False)
    api_prefix: str = "/api"
    log_level: str = "INFO"
    # "text" for human-readable console logs, "json" for structured logs suited
    # to log aggregation systems (ELK, CloudWatch, Loki, ...).
    log_format: str = "text"

    # CORS – comma separated list of allowed origins. Never combine "*" with
    # credentials; validated below.
    cors_origins: str = "http://localhost:5173,http://localhost:3000,http://localhost:8080"

    # ------------------------------------------------------------- rate limits
    # Best-effort, single-process in-memory rate limiting (sliding window) on
    # the expensive endpoints. NOT a substitute for a distributed limiter
    # (e.g. Redis-backed) behind a multi-worker/multi-node deployment — see
    # docs/SYSTEM_DESIGN.md "Known Limitations".
    rate_limit_enabled: bool = True
    upload_rate_limit_per_minute: int = Field(default=10, ge=1)
    analyze_rate_limit_per_minute: int = Field(default=6, ge=1)
    default_rate_limit_per_minute: int = Field(default=120, ge=1)

    # ---------------------------------------------------------------- database
    # Stored OUTSIDE ``storage_dir`` deliberately: ``storage_dir`` (or its
    # public subdirectories) is served over HTTP by StaticFiles, and the
    # database must never be reachable that way.
    data_dir: Path = REPO_ROOT / "data"
    database_url: str = ""  # resolved in ensure_directories() if left blank

    # ------------------------------------------------------------------ storage
    storage_dir: Path = REPO_ROOT / "storage"
    videos_dir: Path = REPO_ROOT / "storage" / "videos"
    clips_dir: Path = REPO_ROOT / "storage" / "clips"
    heatmaps_dir: Path = REPO_ROOT / "storage" / "heatmaps"
    thumbnails_dir: Path = REPO_ROOT / "storage" / "thumbnails"
    # Reports are downloaded through an authenticated-shape endpoint
    # (/report/{id}/...), never through the public static mount.
    reports_dir: Path = REPO_ROOT / "storage" / "reports"

    max_upload_mb: int = Field(default=8192, gt=0)  # 8 GB – supports 3h+ 1080p.
    allowed_extensions: str = "mp4,avi,mov,mkv"

    # ------------------------------------------------------------ motion / ROI
    # Default motion algorithm: one of ``mog2``, ``frame_diff``, ``optical_flow``,
    # or ``auto`` (heuristically selected from a quick pre-scan of the video).
    default_motion_algorithm: str = "mog2"
    # Process every Nth frame during analysis (>=1). Larger = faster, coarser.
    frame_sample_step: int = Field(default=2, ge=1, le=60)
    # Minimum contour area (px) to be considered real motion (noise filter).
    # Used as a fallback when ``roi_min_area_fraction`` is not set / disabled.
    min_motion_area: int = Field(default=800, ge=1)
    # Minimum ROI area as a fraction of total frame area. Resolution-relative,
    # so the same setting behaves consistently at 480p and at 4K. When set
    # (>0), this takes precedence over the fixed-pixel ``min_motion_area``.
    roi_min_area_fraction: float = Field(default=0.0008, ge=0.0, le=1.0)
    # Motion score (fraction of pixels in motion) above which a frame is
    # considered "active" before hysteresis/smoothing is applied.
    motion_threshold: float = Field(default=0.012, ge=0.0, le=1.0)
    # Hysteresis: the score must drop below (motion_threshold * this factor)
    # to exit the active state, preventing flicker around the boundary.
    motion_hysteresis_ratio: float = Field(default=0.6, ge=0.0, le=1.0)
    # Temporal smoothing window (samples) for the motion-score moving average.
    motion_smoothing_window: int = Field(default=5, ge=1, le=101)
    # Gap (seconds) of no-motion tolerated before a segment is closed.
    segment_merge_gap_sec: float = Field(default=1.5, ge=0.0)
    # Minimum duration (seconds) for a segment to be kept.
    min_segment_duration_sec: float = Field(default=1.0, ge=0.0)
    # IoU above which two ROI boxes are merged.
    roi_merge_iou: float = Field(default=0.2, ge=0.0, le=1.0)
    # Maximum raw contours considered per frame before merging (perf guard
    # against pathological, extremely noisy frames).
    roi_max_raw_contours: int = Field(default=200, ge=1)

    # -------------------------------------------------------------- yolo model
    yolo_model: str = "yolo11n.pt"
    yolo_confidence: float = Field(default=0.35, ge=0.0, le=1.0)
    yolo_iou: float = Field(default=0.5, ge=0.0, le=1.0)
    # Force device: "auto" (cuda if available else cpu), "cpu", "cuda", "cuda:0"...
    yolo_device: str = "auto"
    # Enable/disable object detection entirely (useful for tests / no weights).
    enable_object_detection: bool = True
    # Detection result cache size (identical/near-identical frames within a
    # single analysis run reuse cached results instead of re-running inference).
    yolo_cache_size: int = Field(default=256, ge=0)
    # Optional path to a custom / fine-tuned model (e.g. trained to recognise
    # loose paper, chits or exam-specific contraband). Overrides ``yolo_model``
    # when set. See ``docs/SYSTEM_DESIGN.md`` for the fine-tuning hook contract.
    custom_yolo_model_path: str | None = None
    # Optional path to a JSON file mapping the custom model's class names to
    # the app's normalised label set, e.g. {"chit": "paper_note"}. Only used
    # together with ``custom_yolo_model_path``.
    custom_label_map_path: str | None = None

    # ------------------------------------------------------------------ worker
    # ``thread`` runs the pipeline in a background thread (no external broker).
    # ``celery`` offloads to a Celery worker (requires Redis).
    task_backend: str = "thread"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"
    # Bounded read-ahead queue depth for the decode/process pipeline. Bounds
    # memory growth if CV processing falls behind frame decoding.
    frame_buffer_size: int = Field(default=64, ge=1, le=4096)

    # --------------------------------------------------------------- validators
    @field_validator("default_motion_algorithm")
    @classmethod
    def _validate_motion_algorithm(cls, v: str) -> str:
        allowed = {"mog2", "frame_diff", "optical_flow", "auto"}
        v = v.lower().strip()
        if v not in allowed:
            raise ValueError(f"default_motion_algorithm must be one of {sorted(allowed)}, got {v!r}")
        return v

    @field_validator("task_backend")
    @classmethod
    def _validate_task_backend(cls, v: str) -> str:
        allowed = {"thread", "celery"}
        v = v.lower().strip()
        if v not in allowed:
            raise ValueError(f"task_backend must be one of {sorted(allowed)}, got {v!r}")
        return v

    @field_validator("log_format")
    @classmethod
    def _validate_log_format(cls, v: str) -> str:
        allowed = {"text", "json"}
        v = v.lower().strip()
        if v not in allowed:
            raise ValueError(f"log_format must be one of {sorted(allowed)}, got {v!r}")
        return v

    @model_validator(mode="after")
    def _validate_cors_credentials(self) -> Settings:
        origins = self.cors_origin_list
        if "*" in origins and len(origins) > 1:
            raise ValueError(
                "cors_origins must not mix '*' with explicit origins; use '*' alone "
                "(and only for local/dev use) or an explicit allow-list."
            )
        return self

    # ------------------------------------------------------------------- derived
    @property
    def allowed_extension_set(self) -> set[str]:
        return {e.strip().lower().lstrip(".") for e in self.allowed_extensions.split(",") if e.strip()}

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    def ensure_directories(self) -> None:
        """Create every storage/data directory and resolve the DB URL if unset."""
        for directory in (
            self.storage_dir,
            self.videos_dir,
            self.clips_dir,
            self.heatmaps_dir,
            self.thumbnails_dir,
            self.reports_dir,
            self.data_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

        if not self.database_url:
            self.database_url = f"sqlite:///{self.data_dir / 'app.db'}"


@lru_cache
def get_settings() -> Settings:
    """Return a cached ``Settings`` instance (dependency-injection friendly)."""
    settings = Settings()
    settings.ensure_directories()
    return settings


settings = get_settings()
