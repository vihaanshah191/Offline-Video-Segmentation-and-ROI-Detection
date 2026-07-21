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
| `CORS_ORIGINS` | your frontend origin(s) | Lock down cross-origin access. |
| `TASK_BACKEND` | `celery` (multi-node) or `thread` | Job execution model. |
| `YOLO_DEVICE` | `cuda` if GPU present | Faster object detection. |
| `MAX_UPLOAD_MB` | size to your needs | Guard disk usage. |
| `DATABASE_URL` | Postgres URL for scale | SQLite is fine for single-node. |

### Moving off SQLite

SQLAlchemy makes this a config change. Point `DATABASE_URL` at Postgres:

```
DATABASE_URL=postgresql+psycopg://user:pass@db:5432/analytics
```

(Add `psycopg[binary]` to requirements.) Tables are created on startup.

## 3. Storage

Generated artefacts and uploads live under `STORAGE_DIR` (the `storage` volume).
For durability/scale, back this with network or object storage and ensure all
backend + worker replicas share the same mount.

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

    client_max_body_size 4096M;

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
- Backend capabilities: `GET /api/system`.
- Both container images define Docker `HEALTHCHECK`s.
- Logs go to stdout (structured, timestamped) — collect with your platform's log
  driver.

## 7. Upgrades

```bash
git pull
docker compose build
docker compose up -d
```

Schema changes are applied automatically on startup (`init_db`). For production
Postgres, introduce Alembic migrations before making breaking schema changes.
