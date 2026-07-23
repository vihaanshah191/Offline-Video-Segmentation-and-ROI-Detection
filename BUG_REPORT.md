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

## Follow-up bug hunt (post-CI-fix pass)

Found via a targeted backend + frontend audit of the existing (already
"hardened") codebase, independent of any specific feature being added.
Each was verified by reading the exact failure path, then fixed and
covered by a regression test where practical.

### 5. Frame-by-frame stepping in the video player immediately un-pauses

**Severity:** Medium (a documented, user-facing feature was completely non-functional)

**Found:** Reading `VideoPlayer.tsx`'s `stepFrame` alongside
`VideoDetailPage.tsx`'s `seekTo`.

**Root cause:** `stepFrame` calls `el.pause()` then `onSeek(next)` to hold
a single frame. But the `onSeek` prop is `VideoDetailPage.seekTo`, which
unconditionally does `el.currentTime = time; void el.play()` — used
correctly for timeline clicks and event-jump (which *should* resume
playback), but wrong for the explicit pause-then-step case. Every click of
the previous/next-frame buttons paused and then immediately resumed
playback in the same call chain, so the video never actually held on a
single frame.

**Fix:** `stepFrame` now calls `onTimeUpdate(next)` (a plain state-sync
callback with no play side effect) instead of `onSeek(next)`.

### 6. Dropping more files mid-batch-upload silently stalls the new files forever

**Severity:** High (silent stuck-upload in the primary upload flow)

**Found:** Reading `VideoUpload.tsx`'s `processQueue`/`handleFiles`.

**Root cause:** `processQueue(items)` took a snapshot array and looped
only over it, guarded by a `processingRef` lock. If the user dropped more
files while a batch was still uploading, the new call returned immediately
(lock held) and its items were never picked up by the first call's loop
(which only ever iterated its own original snapshot) — they sat at
`status: "pending"` with a permanently spinning loader, no upload attempt
ever made, no error, no retry path.

**Fix:** Replaced the snapshot-array approach with a shared `pendingRef`
queue that `handleFiles` pushes onto and the (single) running
`processQueue` loop drains until empty, so newly dropped files during an
active upload are picked up instead of stalling.

### 7. Frame-reader thread + `VideoCapture` leaked on pipeline cancellation/abort

**Severity:** High (unbounded thread/file-descriptor leak in a long-running server process)

**Found:** Reading `pipeline.py`'s `_FrameReaderThread` alongside the
cancellation and corrupt-frame-abort paths.

**Root cause:** The reader thread decodes frames on a background thread
and blocks on `frame_queue.put()` whenever the bounded queue is full —
normal, since CV processing is usually slower than raw decode. When the
consumer loop exits early (`PipelineCancelled`, or the
too-many-corrupt-frames abort), nothing calls `.get()` on the queue again,
so a reader blocked on `put()` stayed blocked for the rest of the
process's life — leaking its thread and open `VideoCapture` on every
cancellation of a typical (processing-bound) video. `reader.join(timeout=5)`
only timed out and gave up; it never actually stopped the thread.

**Fix:** Added a `stop()` method (a `threading.Event`) that the reader's
`put()` loop polls every 0.5s instead of blocking indefinitely; `stop()`
is called before `join()` on every exit path from the frame loop (a no-op
if the reader already finished normally).

**Regression test:** `tests/test_pipeline.py::test_frame_reader_thread_stop_unblocks_a_full_queue`
— starts a reader with `queue_size=1` and no consumer (reproducing "queue
full, producer blocked" almost immediately), calls `stop()`, and asserts
`join(timeout=2.0)` actually finishes.

### 8. A cancel request racing with an unrelated failure could auto-cancel the next, unrelated run

**Severity:** Medium (confusing, hard-to-diagnose false "cancelled" result on retry)

**Found:** Reading `workers/tasks.py`'s generic failure handler against
`Video.cancel_requested`'s lifecycle.

**Root cause:** `cancel_requested` was only ever cleared on the
`PipelineCancelled` path. If a run failed for an unrelated reason (e.g.
the corrupt-frame abort) at the same moment a user requested cancellation,
the generic `except Exception` handler marked the video `FAILED` but left
`cancel_requested=True` in the DB. The next time the user re-ran analysis
on that video, its very first cancellation checkpoint would see the stale
flag and immediately abort the *new* run as cancelled — even though the
user never cancelled it.

**Fix:** Two independent layers: the generic failure handler now also
resets `cancel_requested = False`, and (defense in depth)
`VideoService.try_mark_queued`'s atomic UPDATE resets it too, so every
transition to `QUEUED` starts with a clean flag regardless of which path
got it there.

**Regression test:** `tests/test_cancellation.py::test_try_mark_queued_resets_stale_cancel_flag`.

### 9. (Latent, now fixed) `cut_clip`'s OpenCV fallback didn't receive its own duration floor

**Severity:** Low (not reachable through normal segmentation output today, which
already guarantees `end_time >= start_time`; would only matter if that
invariant were ever violated by a future change)

**Found:** Reading `cut_clip` against its own OpenCV fallback,
`_cut_clip_opencv`.

**Root cause:** `cut_clip` computes `duration = max(0.1, end - start)` and
uses it for the ffmpeg `-t` argument, but passed the original, unclamped
`end` through to `_cut_clip_opencv` on the fallback path. A degenerate
`end <= start` reaching that fallback would let its bounds-check loop exit
before writing a single frame — `VideoWriter.release()` still leaves a
file on disk, so `cut_clip` would report success for a zero-frame,
unplayable clip.

**Fix:** `end = start + duration` before either path runs, so the floor
applies uniformly.

**Regression test:** `tests/test_video_io.py::test_cut_clip_degenerate_range_still_writes_a_playable_clip`
— forces the OpenCV fallback (`ffmpeg_available` monkeypatched to `False`)
with `start == end` and asserts the output file has a readable frame.
