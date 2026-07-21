"""Heatmap retrieval endpoints."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse

from app.api.deps import get_video_or_404
from app.core.config import settings
from app.models.video import Video
from app.schemas.analytics import HeatmapResponse
from app.utils.files import to_relative_url

router = APIRouter(tags=["heatmap"])


@router.get("/heatmap/{video_id}", response_model=HeatmapResponse)
def get_heatmap(video: Video = Depends(get_video_or_404)) -> HeatmapResponse:
    """Return metadata (and served URL) for a video's motion heatmap."""
    generated = bool(video.heatmap_path and Path(video.heatmap_path).exists())
    return HeatmapResponse(
        video_id=video.id,
        heatmap_url=to_relative_url(video.heatmap_path, settings.storage_dir) if generated else None,
        width=video.width,
        height=video.height,
        generated=generated,
    )


@router.get("/heatmap/{video_id}/download")
def download_heatmap(video: Video = Depends(get_video_or_404)) -> FileResponse:
    """Download the heatmap PNG as an attachment."""
    if not video.heatmap_path or not Path(video.heatmap_path).exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Heatmap not generated")
    return FileResponse(
        video.heatmap_path,
        media_type="image/png",
        filename=f"heatmap_video{video.id}.png",
    )
