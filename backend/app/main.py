"""FastAPI application factory and entry point.

Wires together configuration, logging, the database, static file serving for
generated artefacts, CORS and the API router.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import api_router
from app.core.config import settings
from app.core.logging_config import configure_logging, get_logger
from app.database.session import init_db

configure_logging(settings.log_level)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise storage directories and database schema on startup."""
    settings.ensure_directories()
    init_db()
    logger.info("%s v%s started", settings.app_name, settings.app_version)
    yield
    logger.info("Shutting down")


def create_app() -> FastAPI:
    """Application factory."""
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Offline video analytics: motion detection, ROI detection, "
            "segmentation, object detection, heatmaps, timelines and event logs."
        ),
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Serve generated artefacts (heatmaps, clips, thumbnails) statically.
    settings.ensure_directories()
    app.mount("/storage", StaticFiles(directory=str(settings.storage_dir)), name="storage")

    app.include_router(api_router, prefix=settings.api_prefix)

    @app.get("/", tags=["system"])
    def root() -> dict:
        return {
            "name": settings.app_name,
            "version": settings.app_version,
            "docs": "/docs",
            "api_prefix": settings.api_prefix,
        }

    return app


app = create_app()
