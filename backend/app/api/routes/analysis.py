"""Analysis trigger endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_video_or_404, get_video_service
from app.core.config import settings
from app.core.logging_config import get_logger
from app.models.video import Video, VideoStatus
from app.schemas.video import AnalyzeRequest, VideoDetail
from app.services.motion_detection import SUPPORTED_ALGORITHMS
from app.services.pipeline import PipelineConfig
from app.services.video_service import VideoService
from app.workers.tasks import enqueue_analysis

logger = get_logger(__name__)
router = APIRouter(tags=["analysis"])


@router.post("/analyze/{video_id}", response_model=VideoDetail, status_code=status.HTTP_202_ACCEPTED)
def analyze_video(
    request: AnalyzeRequest | None = None,
    video: Video = Depends(get_video_or_404),
    service: VideoService = Depends(get_video_service),
) -> VideoDetail:
    """Queue an offline analysis run for the given video.

    Returns immediately with the video in a ``queued`` state; poll
    ``GET /video/{id}`` for ``progress`` and ``status``.
    """
    req = request or AnalyzeRequest()

    if req.motion_algorithm not in SUPPORTED_ALGORITHMS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported motion_algorithm. Choose from {list(SUPPORTED_ALGORITHMS)}.",
        )
    if video.status == VideoStatus.PROCESSING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Analysis is already in progress for this video.",
        )

    config = PipelineConfig.from_settings(
        settings,
        motion_algorithm=req.motion_algorithm,
        enable_object_detection=req.enable_object_detection,
        frame_sample_step=req.frame_sample_step,
        min_motion_area=req.min_motion_area,
    )

    service.mark_status(
        video,
        VideoStatus.QUEUED,
        progress=0.0,
        message="Queued for analysis",
        error=None,
    )
    enqueue_analysis(video.id, config)

    detail = VideoDetail.model_validate(video)
    detail.event_count = service.event_count(video.id)
    return detail
