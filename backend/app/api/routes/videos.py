"""Video upload, listing, retrieval and deletion endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.api.deps import get_video_or_404, get_video_service
from app.core.logging_config import get_logger
from app.models.video import Video
from app.schemas.video import MessageResponse, VideoDetail, VideoRead
from app.services.video_service import VideoService, VideoValidationError

logger = get_logger(__name__)
router = APIRouter(tags=["videos"])


def _to_detail(video: Video, service: VideoService) -> VideoDetail:
    detail = VideoDetail.model_validate(video)
    detail.event_count = service.event_count(video.id)
    return detail


@router.post("/upload", response_model=VideoDetail, status_code=status.HTTP_201_CREATED)
def upload_video(
    file: UploadFile = File(...),
    service: VideoService = Depends(get_video_service),
) -> VideoDetail:
    """Upload a video file (mp4/avi/mov/mkv) and extract its metadata."""
    try:
        video = service.save_upload(file)
    except VideoValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _to_detail(video, service)


@router.get("/videos", response_model=list[VideoRead])
def list_videos(service: VideoService = Depends(get_video_service)) -> list[VideoRead]:
    """List all uploaded videos, newest first."""
    return [VideoRead.model_validate(v) for v in service.list()]


@router.get("/video/{video_id}", response_model=VideoDetail)
def get_video(
    video: Video = Depends(get_video_or_404),
    service: VideoService = Depends(get_video_service),
) -> VideoDetail:
    """Retrieve a single video with its analysis metadata."""
    return _to_detail(video, service)


@router.delete("/video/{video_id}", response_model=MessageResponse)
def delete_video(
    video: Video = Depends(get_video_or_404),
    service: VideoService = Depends(get_video_service),
) -> MessageResponse:
    """Delete a video and every associated artefact and database row."""
    video_id = video.id
    service.delete(video)
    return MessageResponse(message=f"Video {video_id} deleted")
