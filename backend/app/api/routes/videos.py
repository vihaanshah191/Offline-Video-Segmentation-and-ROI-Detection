"""Video upload, listing, retrieval, deletion and aggregate-stats endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.api.auth_deps import Principal, require_permission
from app.api.deps import get_video_or_404, get_video_service, to_video_detail
from app.core.logging_config import get_logger
from app.database.session import get_db
from app.models.video import Video, VideoStatus
from app.schemas.video import GlobalStats, MessageResponse, VideoDetail, VideoRead
from app.services.auth_service import AuthService
from app.services.video_service import VideoService

logger = get_logger(__name__)
router = APIRouter(tags=["videos"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.post(
    "/upload",
    response_model=VideoDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a video for analysis",
    response_description="The stored video with its extracted metadata.",
)
def upload_video(
    request: Request,
    file: UploadFile = File(..., description="Video file (mp4, avi, mov or mkv)."),
    service: VideoService = Depends(get_video_service),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permission("upload")),
) -> VideoDetail:
    """Upload a video file and extract its metadata.

    Validation performed (see ``docs/SYSTEM_DESIGN.md`` → Security):
    extension allow-list, ``Content-Length`` pre-check, streamed size
    enforcement, and a magic-byte content-signature check that the file's
    actual bytes match its claimed container format. ``VideoValidationError``
    is handled centrally by the app-level exception handler (400 Bad Request).
    Requires the ``upload`` permission when ``AUTH_ENABLED=true``.
    """
    content_length_header = request.headers.get("content-length")
    content_length = int(content_length_header) if content_length_header else None
    video = service.save_upload(file, content_length=content_length)
    AuthService(db).record_audit(
        action="upload",
        username=principal.username,
        resource=f"video:{video.id}",
        ip_address=_client_ip(request),
        detail=video.original_name,
    )
    return to_video_detail(video, service)


@router.get(
    "/videos",
    response_model=list[VideoRead],
    summary="List uploaded videos (paginated)",
    response_description=(
        "A page of videos, newest first. Total/limit/offset are additionally "
        "carried in X-Total-Count / X-Limit / X-Offset response headers."
    ),
)
def list_videos(
    response: Response,
    service: VideoService = Depends(get_video_service),
    limit: int = Query(default=100, ge=1, le=500, description="Max videos to return."),
    offset: int = Query(default=0, ge=0, description="Number of videos to skip."),
    status_filter: str | None = Query(
        default=None, alias="status", description="Filter by status (e.g. 'processing', 'completed')."
    ),
) -> list[VideoRead]:
    """List uploaded videos, newest first.

    Pagination is additive and non-breaking: the response body is still a
    plain JSON array (unchanged shape for existing clients); paging metadata
    is exposed via ``X-Total-Count``, ``X-Limit`` and ``X-Offset`` response
    headers for clients that want it. Read endpoints are never
    permission-gated — every authenticated (or, with auth disabled, every)
    caller can view videos; only mutating actions are role-restricted.
    """
    status_enum = None
    if status_filter:
        try:
            status_enum = VideoStatus(status_filter)
        except ValueError:
            status_enum = None  # unrecognised filter -> no filtering, not an error

    page = service.list_page(limit=limit, offset=offset, status=status_enum)
    response.headers["X-Total-Count"] = str(page.total)
    response.headers["X-Limit"] = str(limit)
    response.headers["X-Offset"] = str(offset)
    return [VideoRead.model_validate(v) for v in page.items]


@router.get(
    "/stats",
    response_model=GlobalStats,
    summary="Aggregate statistics across every uploaded video",
)
def get_global_stats(service: VideoService = Depends(get_video_service)) -> GlobalStats:
    """Dashboard-overview counters: totals by status, events and disk headroom."""
    return GlobalStats.model_validate(service.global_stats())


@router.get("/video/{video_id}", response_model=VideoDetail)
def get_video(
    video: Video = Depends(get_video_or_404),
    service: VideoService = Depends(get_video_service),
) -> VideoDetail:
    """Retrieve a single video with its analysis metadata and processing stats."""
    return to_video_detail(video, service)


@router.delete("/video/{video_id}", response_model=MessageResponse)
def delete_video(
    request: Request,
    video: Video = Depends(get_video_or_404),
    service: VideoService = Depends(get_video_service),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permission("delete")),
) -> MessageResponse:
    """Delete a video and every associated artefact and database row.

    Requires the ``delete`` permission when ``AUTH_ENABLED=true``.
    """
    video_id = video.id
    original_name = video.original_name
    service.delete(video)
    AuthService(db).record_audit(
        action="delete",
        username=principal.username,
        resource=f"video:{video_id}",
        ip_address=_client_ip(request),
        detail=original_name,
    )
    return MessageResponse(message=f"Video {video_id} deleted")


@router.post("/video/{video_id}/cancel", response_model=MessageResponse)
def cancel_video_analysis(
    request: Request,
    video: Video = Depends(get_video_or_404),
    service: VideoService = Depends(get_video_service),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permission("cancel")),
) -> MessageResponse:
    """Request cancellation of an in-progress or queued analysis run.

    Cancellation is cooperative (see ``Video.cancel_requested`` and
    ``AnalysisPipeline._check_cancelled``): this sets a flag that the
    background worker polls and honours at its next checkpoint, then marks
    the video ``cancelled``. Returns 409 if the video isn't currently
    queued or processing. Requires the ``cancel`` permission when
    ``AUTH_ENABLED=true``.
    """
    if not service.request_cancel(video):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Video is {video.status.value}, not queued or processing; nothing to cancel.",
        )
    AuthService(db).record_audit(
        action="cancel",
        username=principal.username,
        resource=f"video:{video.id}",
        ip_address=_client_ip(request),
    )
    return MessageResponse(message=f"Cancellation requested for video {video.id}")
