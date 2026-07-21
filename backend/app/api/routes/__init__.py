"""API route modules aggregated into a single router."""
from fastapi import APIRouter

from app.api.routes import (
    analysis,
    clips,
    events,
    health,
    heatmap,
    reports,
    timeline,
    videos,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(videos.router)
api_router.include_router(analysis.router)
api_router.include_router(events.router)
api_router.include_router(clips.router)
api_router.include_router(heatmap.router)
api_router.include_router(timeline.router)
api_router.include_router(reports.router)

__all__ = ["api_router"]
