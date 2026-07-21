# Developer Guide

## Local setup

See [INSTALLATION.md](INSTALLATION.md). TL;DR:

```bash
# backend
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload

# frontend
cd frontend && npm install && npm run dev
```

## Repository layout

```
backend/    FastAPI app + AI pipeline + tests
frontend/   React + TS dashboard
scripts/    sample data generator
docs/       documentation
```

## Backend conventions

- **Config** — all tunables live in `app/core/config.py` (`Settings`, loaded
  from env / `.env`). Never hard-code paths or thresholds; add a setting.
- **Logging** — use `get_logger(__name__)`; do not use `print`.
- **Type hints & docstrings** — required on public functions/classes.
- **Services are pure-ish** — they take a DB session and typed inputs; the API
  layer stays thin.
- **Errors** — raise `HTTPException` in routes; services raise domain errors
  (e.g. `VideoValidationError`).

### Adding a new motion algorithm

1. Add a branch in `MotionDetector` (`app/services/motion_detection.py`) and a
   constant to `SUPPORTED_ALGORITHMS`.
2. That's it — the pipeline, API validation and frontend selector read from the
   same source of truth.

### Adding a new API endpoint

1. Create/extend a router in `app/api/routes/`.
2. Register it in `app/api/routes/__init__.py`.
3. Add a Pydantic schema in `app/schemas/` if returning structured data.
4. Add a test in `tests/`.

## Frontend conventions

- **Strict TypeScript** — `tsconfig.app.json` enables `strict`,
  `noUnusedLocals`, `noUnusedParameters`. `npm run build` type-checks.
- **Data fetching** — all server state goes through React Query hooks in
  `src/hooks/useVideos.ts`. Components never call axios directly except through
  `src/api/`.
- **Types mirror the backend** — keep `src/types/index.ts` in sync with the
  Pydantic schemas.
- **UI primitives** — shadcn-style components in `src/components/ui/` built on
  Radix; feature components compose them.
- **Path alias** — import with `@/...` (maps to `src/`).

## Testing

```bash
cd backend
pytest                     # all tests
pytest tests/test_api.py   # a single file
pytest --cov=app --cov-report=term-missing
ruff check app tests       # lint
```

Tests run with an isolated temp storage dir + SQLite DB (see
`tests/conftest.py`) and with object detection disabled, so they need no model
weights or GPU.

Frontend:

```bash
cd frontend
npm run build              # type-check + production build (used by CI)
```

## The sample video

`scripts/generate_sample_video.py` renders a synthetic exam-hall clip with
distinct motion windows — handy for manual testing and demos without real
footage.

```bash
python scripts/generate_sample_video.py out.mp4 --seconds 20 --fps 15
```

## CI

`.github/workflows/ci.yml` runs three jobs on every push/PR:

1. **backend** — ruff lint + pytest (with coverage).
2. **frontend** — `npm ci` + `npm run build` (strict type-check).
3. **docker** — builds both images.

Keep all three green.

## Git workflow

- Feature branches; small, focused commits with descriptive messages.
- Do not commit generated artefacts (`storage/*`, `dist/`, `node_modules/`,
  `*.pt`) — they are gitignored.
