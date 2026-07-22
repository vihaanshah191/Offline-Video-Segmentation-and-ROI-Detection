"""Runtime-editable analysis defaults service (the Settings page backend).

Reads/writes the singleton :class:`RuntimeConfig` row. New analysis runs
merge this row's values on top of the env-var (:mod:`app.core.config`)
defaults — see :meth:`RuntimeConfigService.resolved_defaults`. A per-request
``AnalyzeRequest`` field still overrides both, so the precedence is:

    per-request override  >  runtime_config (DB, Settings page)  >  env var
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import settings as env_settings
from app.core.logging_config import get_logger
from app.models.runtime_config import RuntimeConfig

logger = get_logger(__name__)


class RuntimeConfigService:
    """Get/update the singleton runtime configuration row."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self) -> RuntimeConfig:
        """Return the singleton config row, creating it (from env defaults) if absent."""
        config = self.db.get(RuntimeConfig, 1)
        if config is None:
            config = RuntimeConfig(
                id=1,
                default_motion_algorithm=env_settings.default_motion_algorithm,
                motion_threshold=env_settings.motion_threshold,
                min_motion_area=env_settings.min_motion_area,
                frame_sample_step=env_settings.frame_sample_step,
                yolo_confidence=env_settings.yolo_confidence,
                enable_object_detection=env_settings.enable_object_detection,
            )
            self.db.add(config)
            self.db.commit()
            self.db.refresh(config)
        return config

    def update(self, *, updated_by: str | None = None, **fields: object) -> RuntimeConfig:
        """Update whichever fields are provided (None values are ignored)."""
        config = self.get()
        for key, value in fields.items():
            if value is not None and hasattr(config, key):
                setattr(config, key, value)
        config.updated_by = updated_by
        self.db.commit()
        self.db.refresh(config)
        logger.info("Runtime config updated by %s: %s", updated_by or "anonymous", fields)
        return config

    def reset_to_env_defaults(self) -> RuntimeConfig:
        return self.update(
            default_motion_algorithm=env_settings.default_motion_algorithm,
            motion_threshold=env_settings.motion_threshold,
            min_motion_area=env_settings.min_motion_area,
            frame_sample_step=env_settings.frame_sample_step,
            yolo_confidence=env_settings.yolo_confidence,
            enable_object_detection=env_settings.enable_object_detection,
        )
