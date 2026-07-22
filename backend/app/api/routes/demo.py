"""Demo Mode: one-click "load the bundled sample and analyze it" endpoint.

Lets a judge or first-time user see the full pipeline run end-to-end
without needing their own footage, entirely offline (the sample ships in
the repo). A thin composition of the existing upload + analyze flows —
no new pipeline code, so it exercises exactly the same code path a real
upload would.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.auth_deps import Principal, require_permission
from app.api.deps import get_video_service, to_video_detail
from app.core.config import settings
from app.core.logging_config import get_logger
from app.database.session import get_db
from app.schemas.video import VideoDetail
from app.services.auth_service import AuthService
from app.services.pipeline import PipelineConfig
from app.services.video_service import VideoService
from app.workers.tasks import enqueue_analysis

logger = get_logger(__name__)
router = APIRouter(tags=["demo"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.post(
    "/demo/load-sample",
    response_model=VideoDetail,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Load the bundled sample video and immediately queue analysis",
)
def load_demo_sample(
    request: Request,
    service: VideoService = Depends(get_video_service),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permission("upload")),
) -> VideoDetail:
    """One-click Demo Mode: copies in the bundled sample recording, creates
    its video row, and immediately queues analysis with the server's
    default settings (motion algorithm 'auto', object detection as
    configured). Returns 404 if Demo Mode is disabled for this deployment,
    matching the read-only /settings/capabilities.demo_mode_enabled flag."""
    if not settings.demo_mode_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Demo Mode is disabled on this deployment (DEMO_MODE_ENABLED=false).",
        )

    video = service.load_demo_sample()
    AuthService(db).record_audit(
        action="upload",
        username=principal.username,
        resource=f"video:{video.id}",
        ip_address=_client_ip(request),
        detail="demo sample",
    )

    service.try_mark_queued(video)
    config = PipelineConfig.from_settings(settings, motion_algorithm="auto")
    enqueue_analysis(video.id, config)
    AuthService(db).record_audit(
        action="analyze",
        username=principal.username,
        resource=f"video:{video.id}",
        ip_address=_client_ip(request),
        detail="auto (demo)",
    )

    return to_video_detail(video, service)
