"""API route modules aggregated into a single router."""
from fastapi import APIRouter

from app.api.routes import (
    analysis,
    auth,
    clips,
    demo,
    events,
    health,
    heatmap,
    reports,
    settings as settings_routes,
    timeline,
    videos,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(videos.router)
api_router.include_router(analysis.router)
api_router.include_router(events.router)
api_router.include_router(clips.router)
api_router.include_router(heatmap.router)
api_router.include_router(timeline.router)
api_router.include_router(reports.router)
api_router.include_router(settings_routes.router)
api_router.include_router(demo.router)

__all__ = ["api_router"]
