# Docker Setup

The stack ships with production-ready Docker images and a Compose file.

## Services

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| `backend` | `python:3.12-slim` + FFmpeg | `8000` | FastAPI API + thread worker. |
| `frontend` | `nginx:alpine` (multi-stage) | `8080` | Static SPA, proxies `/api` & `/storage`. |
| `redis` | `redis:7-alpine` | `6379` | Broker (only with `--profile celery`). |
| `worker` | same as backend | — | Celery worker (only with `--profile celery`). |

Two named volumes persist state across restarts: `storage` (uploads, clips,
heatmaps, thumbnails — only these specific subdirectories are ever mounted
for public HTTP access) and `data` (the SQLite database). They're
deliberately separate: the database must never live under a directory that
could be served over HTTP, now or after a future change — see
`SYSTEM_DESIGN.md` Section 8.5 for the vulnerability this prevents.

## Basic usage

```bash
# Build and start backend + frontend (thread worker, no broker needed)
docker compose up --build

# Dashboard:  http://localhost:8080
# API docs:   http://localhost:8000/docs
```

## Distributed worker (optional)

```bash
TASK_BACKEND=celery docker compose --profile celery up --build
```

This adds Redis and a dedicated Celery worker; the backend enqueues analysis
jobs onto the broker instead of running them in-process.

## Configuration

Override any setting via environment variables (see `backend/.env.example`).
Common ones:

```bash
DEFAULT_MOTION_ALGORITHM=optical_flow \
ENABLE_OBJECT_DETECTION=true \
YOLO_DEVICE=cpu \
docker compose up --build
```

## GPU acceleration

To use an NVIDIA GPU, install the NVIDIA Container Toolkit and add a device
reservation to the `backend` (and `worker`) service:

```yaml
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

Set `YOLO_DEVICE=cuda`. The default `auto` already selects CUDA when visible.

## Rebuilding after code changes

```bash
docker compose build backend      # or frontend
docker compose up -d
```

## Logs & health

```bash
docker compose logs -f backend
docker compose ps                 # HEALTHCHECK status
```

Both images define health checks (`/api/health` for the backend, root for the
frontend).
