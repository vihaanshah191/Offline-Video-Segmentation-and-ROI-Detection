# Deployment Guide

## 1. Docker Compose (single host)

The simplest production deployment.

```bash
git clone <repo> && cd offline-video-segmentation-and-roi-detection
docker compose up --build -d
```

- Frontend (nginx) on `:8080`, backend on `:8000`.
- The `storage` named volume persists all data.
- Put a TLS-terminating reverse proxy (Caddy, Traefik, nginx) in front for
  HTTPS and a public domain.

### Scaling analysis with Celery

For heavier workloads, run the distributed worker profile and scale workers:

```bash
TASK_BACKEND=celery docker compose --profile celery up -d --scale worker=3
```

## 2. Environment configuration

Configure via environment variables (see `backend/.env.example`). Key production
settings:

| Variable | Recommended | Why |
|----------|-------------|-----|
| `DEBUG` | `false` | Never enable in production. |
| `CORS_ORIGINS` | your frontend origin(s), never `*` + explicit origins mixed | Lock down cross-origin access (startup fails fast if misconfigured). |
| `LOG_FORMAT` | `json` behind a log aggregator, `text` for local | Structured logs for CloudWatch/ELK/Loki. |
| `TASK_BACKEND` | `celery` (multi-node) or `thread` | Job execution model. |
| `YOLO_DEVICE` | `cuda` if GPU present | Faster object detection. |
| `MAX_UPLOAD_MB` | size to your needs (default 8192) | Guard disk usage; 3h+ 1080p needs headroom. |
| `DATABASE_URL` | Postgres URL for scale | SQLite is fine for single-node. |
| `DATA_DIR` | a path outside `STORAGE_DIR` | **Security-critical**: the DB must never live under a publicly-served directory. |
| `RATE_LIMIT_ENABLED` / `UPLOAD_RATE_LIMIT_PER_MINUTE` / `ANALYZE_RATE_LIMIT_PER_MINUTE` | tune to expected traffic | Best-effort, single-process only — see § Multi-worker rate limiting below. |

### Moving off SQLite

SQLAlchemy makes this a config change. Point `DATABASE_URL` at Postgres:

```
DATABASE_URL=postgresql+psycopg://user:pass@db:5432/analytics
```

(Add `psycopg[binary]` to requirements.) Tables are created on startup.

## 3. Storage

Generated artefacts and uploads live under `STORAGE_DIR` (the `storage`
volume); only its `videos/`, `clips/`, `heatmaps/` and `thumbnails/`
subdirectories are ever mounted for public HTTP access (`app.main`) — never
the storage root. The SQLite database lives under a separate `DATA_DIR`,
which must **never** overlap or live inside `STORAGE_DIR`; this is enforced
by convention (default paths are already disjoint) but not by a runtime
check, so don't override `DATA_DIR` to point inside `STORAGE_DIR`.

For durability/scale, back both with network or object storage and ensure
all backend + worker replicas share the same mounts.

## 3b. Security & multi-worker considerations

- **No authentication is built in.** Anyone who can reach the API can
  upload, analyze, download, and delete any video. Put this behind a
  trusted network boundary (VPN, internal-only ingress) or add an auth
  layer (API key middleware, OAuth2 proxy in front of nginx, etc.) before
  exposing it publicly. See `SYSTEM_DESIGN.md` → Known Limitations.
- **Rate limiting is single-process/in-memory.** It's correct and useful
  behind a single Uvicorn worker or the default thread-backend deployment,
  but each additional worker process or replica enforces its own
  independent budget rather than a shared one. For a horizontally-scaled,
  multi-worker deployment, replace `app/core/rate_limit.py`'s middleware
  with a Redis-backed limiter (the `celery` profile already provisions
  Redis, so that infrastructure is available to extend).
- **Upload validation** already checks file extension, `Content-Length`,
  streamed size, and a magic-byte content-signature match — no additional
  proxy-level validation is required, though a reverse proxy body-size limit
  (see § Reverse proxy below) is still good practice as a first line of
  defense.

## 4. GPU deployment

Install the NVIDIA Container Toolkit on the host and add a GPU reservation to
the `backend`/`worker` services (see [DOCKER.md](DOCKER.md)), then set
`YOLO_DEVICE=cuda`.

## 5. Reverse proxy example (nginx)

```nginx
server {
    listen 443 ssl;
    server_name analytics.example.com;
    # ssl_certificate ... ; ssl_certificate_key ... ;

    client_max_body_size 8192M;  # match MAX_UPLOAD_MB

    location / {
        proxy_pass http://127.0.0.1:8080;   # frontend
        proxy_set_header Host $host;
    }
}
```

The bundled frontend nginx already proxies `/api` and `/storage` to the backend,
so only the frontend needs to be publicly exposed.

## 6. Health checks & monitoring

- Backend liveness: `GET /api/health`.
- Backend capabilities: `GET /api/system` (FFmpeg present, CUDA available,
  object detection loadable, free disk space).
- Dashboard-overview counters: `GET /api/stats`.
- Both container images define Docker `HEALTHCHECK`s.
- Logs go to stdout, structured and timestamped; set `LOG_FORMAT=json` to
  emit single-line JSON records (with per-stage pipeline timing/throughput
  as structured fields) instead of human-readable text — collect either with
  your platform's log driver.

## 7. Upgrades

```bash
git pull
docker compose build
docker compose up -d
```

Schema changes are applied automatically on startup (`init_db`). For production
Postgres, introduce Alembic migrations before making breaking schema changes.
