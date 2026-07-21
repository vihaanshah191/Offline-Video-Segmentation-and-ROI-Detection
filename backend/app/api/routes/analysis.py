"""Analysis trigger endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_video_or_404, get_video_service, to_video_detail
from app.core.config import settings
from app.core.logging_config import get_logger
from app.models.video import Video
from app.schemas.video import AnalyzeRequest, VideoDetail
from app.services.motion_detection import SUPPORTED_REQUEST_VALUES
from app.services.pipeline import PipelineConfig
from app.services.video_service import VideoService
from app.workers.tasks import enqueue_analysis

logger = get_logger(__name__)
router = APIRouter(tags=["analysis"])


@router.post(
    "/analyze/{video_id}",
    response_model=VideoDetail,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue an offline analysis run",
    response_description="The video, now in a 'queued' state.",
)
def analyze_video(
    request: AnalyzeRequest | None = None,
    video: Video = Depends(get_video_or_404),
    service: VideoService = Depends(get_video_service),
) -> VideoDetail:
    """Queue an offline analysis run for the given video.

    Returns immediately (202 Accepted) with the video in a ``queued`` state;
    poll ``GET /video/{id}`` for ``progress`` (0-100) and ``status``
    (``queued`` -> ``processing`` -> ``completed``/``failed``). Passing
    ``motion_algorithm: "auto"`` pre-scans the video and picks whichever
    concrete algorithm (mog2/frame_diff/optical_flow) best fits its lighting
    and noise characteristics; the resolved choice is recorded on the video.
    """
    req = request or AnalyzeRequest()

    if req.motion_algorithm not in SUPPORTED_REQUEST_VALUES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported motion_algorithm. Choose from {list(SUPPORTED_REQUEST_VALUES)}.",
        )

    # Atomic compare-and-swap transition — see try_mark_queued() docstring.
    # This closes a TOCTOU race where two near-simultaneous requests could
    # otherwise both pass a plain status check and double-enqueue analysis
    # for the same video.
    if not service.try_mark_queued(video):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Analysis is already {video.status.value} for this video.",
        )

    config = PipelineConfig.from_settings(
        settings,
        motion_algorithm=req.motion_algorithm,
        enable_object_detection=req.enable_object_detection,
        frame_sample_step=req.frame_sample_step,
        min_motion_area=req.min_motion_area,
    )
    enqueue_analysis(video.id, config)

    return to_video_detail(video, service)
