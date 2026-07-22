# Bug Report

Real defects found and fixed during this work pass (the 18-task
production-readiness pass). Each was found through either live browser
testing against a running backend or careful code reading while wiring a
related feature — not hypothetical/theoretical issues.

## 1. CORS: `Authorization` header not allow-listed

**Severity:** High (breaks the entire auth feature for any cross-origin deployment)

**Found:** While live-testing the new login flow in a real browser
(`AUTH_ENABLED=true`, frontend and backend on different origins/ports, as
any real deployment with separate frontend/backend hosting would be). The
login POST itself succeeded, but every subsequent authenticated request
(`GET /auth/me`, `GET /videos`, etc.) failed with a browser CORS error:

```
Access to XMLHttpRequest at '.../auth/me' from origin '...' has been
blocked by CORS policy: Response to preflight request doesn't pass
access control check: It does not have HTTP ok status.
```

**Root cause:** `app/main.py`'s `CORSMiddleware` configuration had
`allow_headers=["Content-Type", "Accept"]` — no `Authorization`. A
browser's preflight `OPTIONS` request for any fetch/XHR carrying a Bearer
token advertises `Access-Control-Request-Headers: authorization`; without
it in the allow-list, the preflight itself fails and the browser never
even sends the real request. This means the request never reached a
FastAPI route at all — no amount of route-level logic could have caught it.

**Fix:** Added `"Authorization"` to `allow_headers` in `main.py`.

**Regression test:** `tests/test_api.py::test_cors_preflight_allows_authorization_header`
— asserts a preflight `OPTIONS` request with
`Access-Control-Request-Headers: authorization` gets a 200 with
`Authorization` present in `Access-Control-Allow-Headers`. Verified the
test fails without the fix (reverted the fix, watched it fail with 400,
restored it) before committing.

## 2. CORS: `PUT` method not allow-listed

**Severity:** High (breaks the new Settings page's save button for any cross-origin deployment)

**Found:** Same live-testing pattern, this time exercising the new
Settings page's Save button. `PUT /api/settings` failed identically —
CORS preflight rejected before the request reached the route.

**Root cause:** Same middleware config, `allow_methods=["GET", "POST",
"DELETE", "OPTIONS"]` — no `PUT`, even though the new settings-update
endpoint uses it.

**Fix:** Added `"PUT"` to `allow_methods`.

**Regression test:** `tests/test_api.py::test_cors_preflight_allows_put_for_settings`.

**Process note:** both CORS bugs were only catchable by testing in an
actual browser against a genuinely cross-origin setup — `TestClient`
(used by the whole pytest suite) doesn't enforce or simulate CORS at all,
so 198 passing backend tests gave zero signal on either bug. This is the
concrete argument for the "verify live in a browser" requirement applied
throughout this pass, not a formality.

## 3. `PipelineConfig.__dict__` — Celery task backend silently never ran

**Severity:** Medium (a configured-but-unused code path; no impact on the
default thread backend, but the Celery backend was completely non-functional)

**Found:** While extending `PipelineConfig` with two new fields
(`object_detection_confidence`, `object_detection_classes`) for the
confidence-slider/class-filter feature, traced how the config crosses the
Celery task boundary and found `workers/tasks.py::enqueue_analysis` calling
`analyze_video_task.delay(video_id, config.__dict__)`.

**Root cause:** `PipelineConfig` is declared `@dataclass(slots=True)`.
Slotted dataclasses have no `__dict__` — accessing `.__dict__` on an
instance raises `AttributeError`. This was wrapped in a broad
`try/except Exception` in `enqueue_analysis` whose only visible effect is
a `logger.warning(...)` and a silent fallback to the thread backend. Net
effect: setting `TASK_BACKEND=celery` never actually dispatched a single
job to Celery — every "Celery" run silently ran on a local thread instead,
with only a warning-level log line (easy to miss) as evidence.

**Fix:** `dataclasses.asdict(config)` instead of `config.__dict__` —
correct for a slotted dataclass, and still round-trips through
`PipelineConfig(**config_dict)` on the Celery worker side exactly as
`celery_app.py` already expected.

**Regression test:**
`tests/test_pipeline.py::test_pipeline_config_survives_celery_style_serialization`
— asserts `dataclasses.asdict()` produces a plain dict and that
`PipelineConfig(**that_dict) == original`.

## 4. (Non-bug, process note) Ad-hoc smoke-test directory layout masked working heatmap code

Not a product defect, but worth recording: this session's manual
Playwright smoke-test scripts set `HEATMAPS_DIR`/`CLIPS_DIR`/`THUMBNAILS_DIR`
as flat siblings of `STORAGE_DIR` (mirroring `tests/conftest.py`'s
layout), rather than production's nested `storage/{videos,clips,heatmaps,
thumbnails}` layout. `to_relative_url()` correctly falls back to a
bare filename when a path isn't actually under `storage_dir`, which is
safe but produces a URL that doesn't match any of the four
per-subdirectory static mounts in `main.py` — so heatmap images 404'd in
those specific smoke runs. Several early screenshots showed a black
heatmap panel that was mis-read as "the sample video is just dark"
rather than "the image request failed." Caught and corrected by re-running
the same verification with a properly nested directory layout, which
confirmed the actual code (and the pytest suite, which uses `to_relative_url`
correctly in both the flat and nested case per `test_schemas.py`) was
always correct — only the throwaway verification harness was misleading
itself. No code change was needed; noted here for transparency about how
the heatmap features were actually confirmed working.

---

**Not found / not applicable:** no data-loss, security-bypass, or
crash-level bugs were found in the pre-existing (pre-this-pass) codebase
during this work. All three real bugs above were introduced by this
pass's own new code (auth, settings-update, extended `PipelineConfig`) and
caught by this pass's own verification discipline before being merged to
the branch.
