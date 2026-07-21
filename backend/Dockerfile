# ---- Backend image: FastAPI + OpenCV + FFmpeg + (optional) YOLOv11 --------
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System dependencies: FFmpeg for clip cutting, libs required by OpenCV.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        libglib2.0-0 \
        libgl1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first for better layer caching.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Application code.
COPY . .

# Non-root runtime user.
# NOTE: /data (the database) and /storage (public artefacts) are deliberately
# separate top-level directories — only /storage's videos/clips/heatmaps/
# thumbnails subdirectories are ever mounted for public HTTP access (see
# app/main.py), and the database must never be placed under a directory that
# could be served that way, now or after a future refactor. See
# SYSTEM_DESIGN.md Section 8.5 for the vulnerability this structure prevents.
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /storage /data \
    && chown -R appuser:appuser /app /storage /data
USER appuser

ENV DATA_DIR=/data \
    DATABASE_URL=sqlite:////data/app.db \
    STORAGE_DIR=/storage \
    VIDEOS_DIR=/storage/videos \
    CLIPS_DIR=/storage/clips \
    HEATMAPS_DIR=/storage/heatmaps \
    THUMBNAILS_DIR=/storage/thumbnails \
    REPORTS_DIR=/storage/reports

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
