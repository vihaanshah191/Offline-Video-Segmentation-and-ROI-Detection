"""FastAPI application factory and entry point.

Wires together configuration, logging, the database, static file serving for
generated artefacts, CORS, rate limiting, global error handling and the API
router.
"""
from __future__ import annotations

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import SQLAlchemyError

from app.api import api_router
from app.core.config import settings
from app.core.logging_config import configure_logging, get_logger
from app.core.rate_limit import RateLimitMiddleware
from app.database.session import SessionLocal, init_db
from app.services.auth_service import AuthService
from app.services.video_service import VideoValidationError

configure_logging(settings.log_level, log_format=settings.log_format)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise storage directories, database schema, and (if auth is
    enabled) the seed admin account on startup."""
    settings.ensure_directories()
    init_db()
    if settings.auth_enabled:
        db = SessionLocal()
        try:
            AuthService(db).ensure_seed_admin(settings.admin_username, settings.admin_password)
        finally:
            db.close()
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
            "segmentation, object detection, heatmaps, timelines and event logs.\n\n"
            "All processing runs asynchronously in the background after "
            "`POST /analyze/{id}`; poll `GET /video/{id}` for progress."
        ),
        lifespan=lifespan,
        contact={"name": "Offline Video Analytics"},
        license_info={"name": "MIT"},
    )

    # Explicit method/header allow-lists rather than "*" — the frontend only
    # ever needs GET/POST/PUT/DELETE/OPTIONS and a Content-Type/Authorization
    # header, so there is no reason to widen the CORS surface further.
    # "Authorization" is required for the Bearer-token auth flow, and "PUT"
    # for the settings-update endpoint: without either in these allow-lists,
    # a browser's CORS preflight for the corresponding cross-origin request
    # fails outright (the request never even reaches the route) whenever the
    # frontend and backend are on different origins.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials="*" not in settings.cors_origin_list,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Accept", "Authorization"],
        expose_headers=["X-Total-Count", "X-Limit", "X-Offset", "X-Process-Time"],
    )

    if settings.rate_limit_enabled:
        app.add_middleware(RateLimitMiddleware)

    @app.middleware("http")
    async def add_process_time_header(request: Request, call_next):
        """Time every request and log slow ones; exposes X-Process-Time."""
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Process-Time"] = f"{elapsed_ms:.2f}ms"
        if elapsed_ms > 1000:
            logger.warning(
                "Slow request: %s %s took %.0fms", request.method, request.url.path, elapsed_ms
            )
        return response

    settings.ensure_directories()

    # Mount ONLY the specific public artefact subdirectories — never the whole
    # ``storage_dir`` root. This is a deliberate security boundary: the SQLite
    # database and any future non-public files must never be reachable over
    # HTTP even if a future change accidentally colocates them under storage.
    for name, directory in (
        ("videos", settings.videos_dir),
        ("clips", settings.clips_dir),
        ("heatmaps", settings.heatmaps_dir),
        ("thumbnails", settings.thumbnails_dir),
    ):
        app.mount(f"/storage/{name}", StaticFiles(directory=str(directory)), name=f"storage-{name}")

    app.include_router(api_router, prefix=settings.api_prefix)

    @app.exception_handler(VideoValidationError)
    async def handle_video_validation_error(request: Request, exc: VideoValidationError):
        """Centralised handling for upload/validation errors raised by services."""
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": str(exc), "error_type": "validation_error"},
        )

    @app.exception_handler(SQLAlchemyError)
    async def handle_database_error(request: Request, exc: SQLAlchemyError):
        """Never leak raw SQL/driver internals; log full detail server-side."""
        logger.exception("Database error handling %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "detail": "The database is temporarily unavailable. Please retry.",
                "error_type": "database_error",
            },
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception):
        """Catch-all: never let an unhandled exception crash the ASGI worker
        or leak a stack trace to the client."""
        logger.exception("Unhandled error handling %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "An unexpected error occurred.", "error_type": "internal_error"},
        )

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
