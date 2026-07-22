"""Runtime settings endpoints (the Settings page)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.auth_deps import Principal, require_permission
from app.core.config import settings as env_settings
from app.database.session import get_db
from app.schemas.settings import RuntimeConfigRead, RuntimeConfigUpdate, SystemCapabilities
from app.services.runtime_config_service import RuntimeConfigService

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=RuntimeConfigRead, summary="Get current analysis defaults")
def get_settings(db: Session = Depends(get_db)) -> RuntimeConfigRead:
    return RuntimeConfigRead.model_validate(RuntimeConfigService(db).get())


@router.put("", response_model=RuntimeConfigRead, summary="Update analysis defaults")
def update_settings(
    payload: RuntimeConfigUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permission("manage_users")),
) -> RuntimeConfigRead:
    """Update the runtime-editable analysis defaults used by new analysis runs.

    Does not affect analyses already in progress. Gated behind the
    ``manage_users``-equivalent admin permission when auth is enabled (a
    global setting change is an administrative action); a no-op check when
    auth is disabled.
    """
    updated = RuntimeConfigService(db).update(
        updated_by=principal.username, **payload.model_dump(exclude_unset=True)
    )
    return RuntimeConfigRead.model_validate(updated)


@router.post("/reset", response_model=RuntimeConfigRead, summary="Reset analysis defaults to environment defaults")
def reset_settings(
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permission("manage_users")),
) -> RuntimeConfigRead:
    updated = RuntimeConfigService(db).reset_to_env_defaults()
    return RuntimeConfigRead.model_validate(updated)


@router.get(
    "/capabilities",
    response_model=SystemCapabilities,
    summary="Read-only deployment capabilities (model, device, limits)",
)
def get_capabilities() -> SystemCapabilities:
    return SystemCapabilities(
        yolo_model=env_settings.custom_yolo_model_path or env_settings.yolo_model,
        yolo_device=env_settings.yolo_device,
        task_backend=env_settings.task_backend,
        max_upload_mb=env_settings.max_upload_mb,
        allowed_extensions=sorted(env_settings.allowed_extension_set),
        auth_enabled=env_settings.auth_enabled,
        demo_mode_enabled=env_settings.demo_mode_enabled,
    )
