"""Video upload, listing, retrieval, deletion and aggregate-stats endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Query, Request, Response, UploadFile, status

from app.api.deps import get_video_or_404, get_video_service, to_video_detail
from app.core.logging_config import get_logger
from app.models.video import Video
from app.schemas.video import GlobalStats, MessageResponse, VideoDetail, VideoRead
from app.services.video_service import VideoService

logger = get_logger(__name__)
router = APIRouter(tags=["videos"])


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
) -> VideoDetail:
    """Upload a video file and extract its metadata.

    Validation performed (see ``docs/SYSTEM_DESIGN.md`` → Security):
    extension allow-list, ``Content-Length`` pre-check, streamed size
    enforcement, and a magic-byte content-signature check that the file's
    actual bytes match its claimed container format. ``VideoValidationError``
    is handled centrally by the app-level exception handler (400 Bad Request).
    """
    content_length_header = request.headers.get("content-length")
    content_length = int(content_length_header) if content_length_header else None
    video = service.save_upload(file, content_length=content_length)
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
) -> list[VideoRead]:
    """List uploaded videos, newest first.

    Pagination is additive and non-breaking: the response body is still a
    plain JSON array (unchanged shape for existing clients); paging metadata
    is exposed via ``X-Total-Count``, ``X-Limit`` and ``X-Offset`` response
    headers for clients that want it.
    """
    page = service.list_page(limit=limit, offset=offset)
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
    video: Video = Depends(get_video_or_404),
    service: VideoService = Depends(get_video_service),
) -> MessageResponse:
    """Delete a video and every associated artefact and database row."""
    video_id = video.id
    service.delete(video)
    return MessageResponse(message=f"Video {video_id} deleted")
