# Judge Q&A

140 likely questions a judge (or a skeptical engineer) might ask, with direct
technical answers. Organized by topic. Cross-references point to
[`SYSTEM_DESIGN.md`](SYSTEM_DESIGN.md) for longer discussion.

---

## General / Architecture

**1. What does this system actually do, in one sentence?**
Given a recorded video, it offline-detects motion, groups it into
discrete "events" with bounding regions, optionally runs object detection on
those events, and presents everything (timeline, heatmap, event log,
analytics, clips) in a dashboard — without any live/real-time constraint.

**2. Why offline instead of real-time?**
Because the target use case (reviewing exam-hall recordings after the fact)
doesn't need real-time; offline lets the pipeline decode once for motion
analysis and only touch a handful of representative frames for the expensive
parts (object detection, clip cutting), which would be wasteful in a
real-time system that has to process every frame regardless.

**3. What's the tech stack?**
Backend: Python 3.12, FastAPI, OpenCV, Ultralytics YOLOv11, NumPy, FFmpeg,
SQLAlchemy on SQLite (Postgres-ready), optional Celery/Redis. Frontend:
React, TypeScript (strict), Vite, Tailwind, Radix-based UI components, React
Query, Recharts. Docker + Docker Compose + GitHub Actions CI.

**4. Why FastAPI over Flask/Django?**
Native async support, automatic OpenAPI/Swagger docs from type-annotated
routes, Pydantic validation built in (which we lean on heavily for both
request validation and response schemas), and a dependency-injection system
that keeps route handlers thin (`Depends(get_video_service)` etc.).

**5. Why is the architecture layered the way it is (api/services/models)?**
Single-responsibility separation: `api/` is HTTP-only (parsing requests,
building responses, status codes), `services/` holds all business logic and
the CV pipeline, `models/` is pure data. This means the pipeline is fully
testable without spinning up FastAPI at all (see `tests/test_pipeline.py`),
and routes stay thin enough to read at a glance.

**6. Could this scale to a SaaS product serving many organizations?**
Architecturally, yes, with three additions this version deliberately doesn't
include: authentication/authorization (§ Known Limitations), a distributed
rate limiter (Redis-backed, since the in-process one is single-node), and
Postgres instead of SQLite for concurrent-write scale. See
`docs/DEPLOYMENT.md`.

**7. Why SQLite by default instead of Postgres?**
Zero setup for a hackathon demo or single-node deployment — no separate
database server to run. `DATABASE_URL` is a one-line config change to
Postgres (SQLAlchemy abstracts the dialect); the schema, constraints and
queries are all portable.

**8. What happens if I run this on a video longer than 3 hours?**
It's designed for exactly this: motion detection decodes once
(`_FrameReaderThread`, bounded queue — memory doesn't grow with duration),
the heatmap accumulator is a fixed-size array (frame resolution, not
duration-dependent), and the sample list is bisect-indexed rather than
linearly scanned per event. See § Performance below for the numbers.

**9. What's the single most important bug you found and fixed in the audit?**
The SQLite database file lived inside `storage_dir`, the same directory
mounted wholesale as a public static file server — `GET /storage/app.db`
would have downloaded the entire database, including every video's metadata.
Fixed by moving the DB to a separate `data_dir` never mounted, and by
mounting only named public subdirectories (`videos/`, `clips/`, `heatmaps/`,
`thumbnails/`) rather than the storage root, as defense in depth. See
`SYSTEM_DESIGN.md` §8.5 and the regression test
`test_database_file_not_reachable_via_storage_mount`.

**10. How is state shared between the API process and the background analysis thread?**
Both use the same SQLAlchemy engine/connection pool
(`pool_pre_ping=True`, SQLite opened with `check_same_thread=False`
specifically because of this); the background thread creates its own
`Session` via `SessionLocal()` rather than reusing the request-scoped one,
which would be unsafe to share across threads.

**11. Why a thread-based worker by default instead of Celery-only?**
Zero external dependencies (no Redis) for the default deployment. Both
paths (`thread` and `celery`) call the exact same `run_analysis()` function
in `app/workers/tasks.py` — nothing about the pipeline logic is duplicated
between them, only the dispatch mechanism differs.

**12. What would you change if you had one more week?**
Fine-tune a custom YOLO model on exam-hall-specific footage for loose
paper/chit detection (the single highest-value gap — see § Object Detection),
then authentication, then a distributed rate limiter. See
`SYSTEM_DESIGN.md` § Future Improvements for the full list.

---

## Motion Detection / Computer Vision

**13. What three motion algorithms are implemented, and how do they differ?**
MOG2 (adaptive Gaussian-mixture background subtraction — robust to gradual
lighting change), frame differencing (consecutive-frame absolute delta,
cheap and sensitive but has no memory of a stopped object), and Farneback
dense optical flow (per-pixel motion vectors, best at distinguishing true
movement from noise in textured/busy scenes, most expensive). All three
implement the same `MotionDetector.process(frame) -> MotionResult`
interface (Strategy pattern).

**14. How does "auto" algorithm selection work?**
`select_best_algorithm()` pre-scans ~40 evenly-strided frames, computes
illumination stability (stddev of mean frame brightness across the sample)
and inter-frame noise (median pixel delta), and picks MOG2 if lighting is
unstable, optical flow if noise/texture is high, else frame differencing.
It's a fast heuristic (one small pre-scan, not a full second pass), not a
trained classifier — see limitations.

**15. Is "auto" a machine-learned model?**
No — it's a rule-based heuristic over two measured signals. A trained
classifier would need labeled training data across many video
characteristics that doesn't exist for this project; the heuristic is
transparent (its reasoning is logged: `select_best_algorithm: chose 'X' —
<reason>`) and fast.

**16. How is noise filtered out of the motion mask?**
Three layers: (1) Otsu-adaptive or fixed thresholding on the raw
foreground signal, (2) morphological open+dilate with a resolution-scaled
kernel, (3) connected-component area filtering that zeroes out any blob
below `min_area` / `min_area_fraction` entirely from the mask (not just from
downstream boxes — see next question).

**17. Why does noise filtering matter for the *score*, not just the boxes?**
Because the motion score (fraction of frame pixels flagged as moving) drives
every segmentation threshold decision. If only the ROI boxes were filtered
downstream but the mask itself still counted noise pixels, the score used to
decide "is this frame active" would be silently polluted by noise the system
otherwise claims to filter. This was an actual bug found in the audit — see
`SYSTEM_DESIGN.md` §8.1 and the regression test
`test_min_area_filters_score_not_just_boxes`.

**18. What is adaptive (Otsu) thresholding and why use it here?**
Otsu's method picks a threshold that best separates a bimodal
intensity distribution (foreground vs. background) *per frame*, rather than
using one fixed constant for every frame regardless of lighting/noise
conditions. Applied to both MOG2's shadow-rejection cutoff and frame
differencing's delta threshold, with a floor value so Otsu can't classify
ordinary sensor noise on a static frame as widespread motion.

**19. Why scale the morphological kernel to resolution?**
A fixed 5×5 kernel over-smooths low-resolution footage (blurring away real
small motion) and under-cleans high-resolution footage (leaving speckle
noise). Kernel size is computed as `frame_diagonal / 400` (odd-ized, min 3)
so the *relative* noise-removal strength stays consistent from 480p through
4K.

**20. What is the MOG2 "warm-up" period?**
MOG2's background model needs several frames of history to become reliable;
the first 15 frames (`MOG2_WARMUP_FRAMES`) are still scored (for
visibility/logging) but flagged `is_warming_up=True`, and the pipeline
treats warm-up frames as unable to *start* a segment — preventing a spurious
motion "event" at t=0 while the model initializes.

**21. How does the system handle a moving/panning camera?**
It doesn't, currently — background subtraction and frame differencing both
assume a fixed viewpoint. A panning camera would register as motion
everywhere. This is a documented limitation; a fix would need feature-based
frame registration/stabilization before motion detection.

**22. What's the difference between `min_area` and `min_area_fraction`?**
`min_area` is a fixed pixel-area threshold (e.g. 800px²); `min_area_fraction`
is a fraction of total frame area (e.g. 0.0008 = 0.08%). The fraction is
resolution-relative and preferred (takes precedence when > 0): the same
`min_area` behaves very differently at 480p vs. 4K, while the fraction
behaves consistently.

**23. Why Farneback specifically, not a modern deep-learning optical flow model (RAFT etc.)?**
Farneback (`cv2.calcOpticalFlowFarneback`) needs no model weights, no GPU,
and no training data — it's a classical dense optical flow algorithm
shipped in OpenCV. A learned flow model would likely be more accurate on
hard cases but adds a dependency and inference cost disproportionate to
this use case (mostly-static scenes with localized motion).

**24. Can I add a fourth motion algorithm?**
Yes — add a branch in `MotionDetector._process_<name>()`, register it in
`SUPPORTED_ALGORITHMS`, and the pipeline, API validation (`AnalyzeRequest`)
and frontend selector all pick it up from that single source of truth. No
other code changes needed.

**25. How does the system avoid double-counting the same physical motion across frames?**
It doesn't need to — each sampled frame's score is independent; segmentation
(not motion detection) is what groups a *sequence* of active frames into one
event, so a single continuous motion doesn't get counted as multiple events
unless it genuinely pauses for longer than `segment_merge_gap_sec`.

**26. What does `frame_sample_step` control, and what's the speed/accuracy trade-off?**
It processes every Nth frame instead of every frame (default 2). Higher
values are faster but coarser temporally — a very brief motion could be
missed entirely if it falls entirely within skipped frames. Configurable per
analysis run via `AnalyzeRequest.frame_sample_step` (1-60).

**27. Does frame skipping still decode every frame?**
Yes — most video codecs don't support cheap arbitrary frame-skipping via
`cv2.VideoCapture.read()` (compressed formats decode sequentially
internally), so the reader thread still calls `.read()` every frame but only
*pushes* sampled frames onto the processing queue, discarding the rest
immediately without leaving the reader thread. The savings are in CV
compute, not decode I/O.

---

## ROI Detection

**28. How are ROI boxes extracted from the motion mask?**
`cv2.findContours` on the cleaned binary mask, filter by area, then
`cv2.boundingRect` per surviving contour.

**29. How are overlapping ROI boxes merged?**
`merge_boxes()` greedily and repeatedly merges any pair of boxes whose IoU
exceeds `roi_merge_iou` (default 0.2) into their union bounding box, looping
until no further merges are possible — so a *chain* of overlapping regions
(A overlaps B, B overlaps C, A doesn't directly overlap C) still collapses
into one box.

**30. What stops a pathologically noisy frame from making ROI detection slow?**
`max_raw_contours` (default 200): if a frame produces more raw contours than
this, only the largest are kept *before* the O(n²) merge pass runs, bounding
worst-case per-frame cost regardless of how noisy a single frame gets.

**31. What does an ROI box's `confidence` mean?**
The fraction of pixels *within that box* that are flagged as moving in the
mask — a measure of how "solid" vs. "sparse" the motion region is, not a
learned-model confidence.

**32. Is there a maximum number of ROI boxes per frame?**
Yes, `max_boxes` (default 25) — if more survive filtering/merging, only the
largest (by area) are kept.

---

## Segmentation

**33. How does raw per-frame motion become discrete "events"?**
Three steps in `build_segments()`: temporal smoothing (trailing moving
average), hysteresis thresholding (enter/exit at two different levels), then
gap-bridging + minimum-duration filtering. See `SYSTEM_DESIGN.md` §3.4.

**34. What is hysteresis thresholding and why not just use one threshold?**
Two thresholds instead of one: a higher one to *start* being "active," a
lower one to *stop*. A single threshold with a score that dithers around it
(common with real noisy sensor data) would flicker active/inactive rapidly,
fragmenting one real event into many spurious tiny ones. Hysteresis (the
same fix Canny edge detection uses for its double threshold) means the score
has to drop meaningfully below where it started before the event is
considered over.

**35. What's the default hysteresis ratio and can I change it?**
`exit_threshold = enter_threshold * motion_hysteresis_ratio`, default ratio
0.6. It's a system-tuned setting (`MOTION_HYSTERESIS_RATIO` env var), not
currently exposed per-API-request — a deliberate choice to keep the
request schema focused on user-facing choices (which algorithm, object
detection on/off) rather than every internal DSP knob.

**36. Why smooth the score before thresholding instead of after?**
Smoothing has to happen before the active/inactive decision, since the whole
point is to prevent noise in the *raw* signal from flipping that decision
rapidly. Smoothing an already-binary active/inactive series wouldn't
meaningfully reduce fragmentation.

**37. What is "motion score normalization" and why does it matter?**
Segments carry both a raw score (tiny, algorithm-dependent — e.g. 0.02, used
for threshold decisions) and a video-relative min-max normalized score
(0..1, where 1.0 = the most active moment in *this* recording). The
normalized score is what's actually stored/displayed (`Event.motion_score`)
— raw fractions aren't legible to a human reviewer, and normalizing against
each video's own observed range makes the numbers meaningful without
affecting the threshold logic that produced the segments in the first place.

**38. Could two genuinely separate events ever get merged into one?**
Yes, if the gap between them is shorter than `segment_merge_gap_sec`
(default 1.5s) — this is intentional (a person briefly pausing mid-motion
shouldn't fragment into two events) but means very rapid distinct movements
close together in time will be reported as one event. Tunable via
`SEGMENT_MERGE_GAP_SEC`.

**39. What happens to a 0.3-second motion blip?**
Filtered out by `min_segment_duration_sec` (default 1.0s) — it's treated as
noise, not a real event.

**40. Does segmentation run per-frame or as a post-process over the whole video?**
Post-process: the full sample list (time, score, roi_present per sampled
frame) is collected during the single motion-detection pass, then
`build_segments()` runs once over the complete NumPy-vectorized series
(smoothing is a vectorized convolution, not a Python loop per frame).

**41. Why does a segment need `roi_present=True` to start, not just a high score?**
Defense against a false-positive global score spike (e.g. a lighting flicker
that raises the pixel-fraction score everywhere) with no actual localized
object — requiring at least one detected ROI box means the score elevation
has to correspond to an actual spatial region, not just aggregate noise.
Verified by `test_roi_absence_prevents_segment_start`.

**42. How would you detect if segmentation is under- or over-fragmenting on real footage?**
Look at `Event` count and average duration relative to video length — many
very short events close together suggests fragmentation (increase
`motion_hysteresis_ratio` toward 1.0, or increase `segment_merge_gap_sec`);
one very long event covering unrelated activity suggests
under-segmentation (decrease the gap, increase `motion_threshold`).

---

## Object Detection

**43. What model is used?**
YOLOv11 nano (`yolo11n.pt`) via the `ultralytics` package by default,
pretrained on COCO. Swappable per-instance via `custom_yolo_model_path`.

**44. Does object detection run on every frame?**
No — only on up to three representative frames (segment start, peak-motion
time, segment end) per *detected motion segment*, never on frames outside a
segment and never on the whole video. This is both a performance decision
(YOLO is the most expensive stage) and a correctness one (no point running
detection where there's no motion).

**45. Why "book" and not "paper" for prohibited-item detection?**
Because COCO — the dataset YOLOv11's pretrained weights were trained on —
has no class for loose paper, folded notes, or chits. An earlier version of
this codebase silently relabelled the `book` class as `"paper"`, which
overstated the system's actual capability. This version reports `book`
honestly and flags it `heuristic: true` (a proxy signal, not a direct
detection) — see `SYSTEM_DESIGN.md` §5 and §8.2 for the full rationale. This
was one of the most important fixes in this audit.

**46. So can this system detect exam chits/cheat sheets at all?**
Not reliably out of the box — that's the honest answer. `book` is used as an
imperfect proxy (a book *might* contain notes; it also might just be a
book), clearly labeled as heuristic in both the API response and the UI
(dashed border, "possible" prefix). Reliable chit detection requires a model
fine-tuned on exam-specific imagery — a hook for exactly that is built in
(`custom_yolo_model_path`), but no such model ships with this project.

**47. What objects ARE reliably detected?**
`phone` (COCO's `cell phone` — a strong, direct signal), `person`, `bag`
(backpack/handbag/suitcase), `bottle`, `laptop`. These map to real,
unambiguous COCO classes.

**48. How would I plug in a custom fine-tuned model?**
Set `CUSTOM_YOLO_MODEL_PATH` to the weights file and (optionally)
`CUSTOM_LABEL_MAP_PATH` to a JSON file mapping the custom model's class
names to normalized labels and marking which are prohibited. No code
changes required — `ObjectDetector` reads both at construction time.

**49. What confidence threshold and NMS IoU are used?**
`yolo_confidence` (default 0.35) and `yolo_iou` (default 0.5), both passed
directly to `model.predict(conf=..., iou=...)` — Ultralytics applies
NMS internally using the IoU value. A defensive re-filter also re-checks
confidence in Python after extraction, in case a model/export format doesn't
strictly enforce `conf` internally.

**50. How is batching implemented, and why does it matter?**
`detect_batch(frames: list) -> list[list[Detection]]` collects all
representative frames for a segment and passes them to a single
`model.predict(frames, ...)` call, rather than looping single-frame
`.detect()` calls. This amortizes Python dispatch and (on GPU) kernel-launch
overhead across the batch instead of paying it per frame.

**51. What is the perceptual-hash detection cache?**
An 8×8 average-hash (`_average_hash`) of each frame is used as an LRU cache
key (`yolo_cache_size` entries, default 256). A near-identical frame — common
when a segment's start/peak/end representative frames land close together in
time — skips re-inference entirely. An *exact*-byte cache would almost never
hit real video frames due to sensor/compression noise; the perceptual hash
is invariant to that noise while still sensitive to genuine content changes.

**52. What happens on GPU out-of-memory?**
The detector catches the error, calls `torch.cuda.empty_cache()`, downgrades
`self.device` to `"cpu"` **permanently for the rest of that run**, and
retries the failed batch once on CPU — rather than silently dropping
detections for every subsequent frame for the remainder of a multi-hour
analysis, which is what a bare try/except around a single inference call
would do.

**53. What happens if `ultralytics`/PyTorch aren't installed, or weights can't download?**
`ObjectDetector._ensure_model()` catches the import/load failure, logs a
warning, sets `_load_failed=True` permanently (so it doesn't retry-and-fail
on every frame), and `.available` returns `False`. The rest of the pipeline
(motion, ROI, segmentation, heatmap, clips) continues completely unaffected
— object detection is the one stage designed to degrade gracefully to "off"
rather than crash the run. This is also how the test suite runs without any
model weights or GPU.

**54. Is the model loaded eagerly at startup or lazily?**
Lazily, on first actual use, guarded by a lock so concurrent threads
attempting to trigger the load don't race each other into loading it twice.

**55. How is device selection (`YOLO_DEVICE=auto`) resolved?**
At `ObjectDetector` construction, if `device == "auto"`, it imports `torch`
and checks `torch.cuda.is_available()`, falling back to `"cpu"` on any
import/check failure — so a machine without CUDA (or without torch's CUDA
build) never crashes, it just runs on CPU.

**56. Why is `heuristic` a field on Detection instead of inferring it from the label at render time?**
Because "is this label heuristic" depends on *which detector configuration*
produced it — a custom fine-tuned model's own `book`-equivalent class (if it
has one) might be a direct, confident detection, not a proxy. Storing it per
row (set at detection time from `self.is_custom_model` and the label) keeps
that distinction correct regardless of which detector config analyzed a
given video.

**57. How does the frontend visually distinguish heuristic detections?**
Dashed (vs. solid) bounding-box stroke, a "possible" label prefix, and a
distinct warning-colored badge ("Possible prohibited item") instead of the
solid destructive-red badge used for confirmed (non-heuristic) prohibited
detections. See `VideoPlayer.tsx` and `EventTable.tsx`.

---

## Performance & Scalability

**58. How does the system avoid decoding a 3-hour video twice?**
The motion-detection pass is the only full decode; object detection, clip
cutting and thumbnails only re-seek to a handful of specific timestamps per
segment (typically 3-5 targeted seeks, not a second linear decode).

**59. What bounds memory usage on a very long recording?**
Three things: (1) the frame-reader thread's queue is bounded
(`frame_buffer_size`, default 64 frames) so decode can't run arbitrarily far
ahead of processing; (2) the heatmap accumulator is a fixed-size `float32`
array sized to frame *resolution*, not duration; (3) the per-sample list
grows with duration but stays lightweight (a few fields per sample, no
frame data retained).

**60. What was the biggest algorithmic complexity fix in this audit?**
Three, in different subsystems: `_materialise_events` used to linearly scan
the *entire* sample list for every event (`O(events × samples)`) — replaced
with `bisect_left`/`bisect_right` on the (already time-sorted) sample times,
`O(events × log(samples))`. `compute_timeline` used to re-scan all events for
every timeline point (`O(events × points)`) — replaced with a single
forward-advancing two-pointer sweep, `O(events + points)`. `compute_analytics`
used to load every event's full ORM graph (including all ROIs/detections)
just to sum/average in Python — replaced with SQL-side aggregation
(`func.sum`, `func.avg`, `GROUP BY`).

**61. How is decode I/O overlapped with CV compute?**
A background thread (`_FrameReaderThread`) does nothing but decode frames
and push sampled ones onto a queue; the main thread pulls and runs motion
detection. OpenCV's C++ implementations release Python's GIL for both
`VideoCapture.read()` and the per-frame CV operations, so this achieves real
wall-clock parallelism between I/O and compute, not just cooperative
scheduling.

**62. Why not use `multiprocessing` for true parallel motion detection across frames?**
MOG2's background model is inherently sequential — each frame's processing
depends on the accumulated state from all previous frames, so frame-level
parallelism isn't available for that algorithm without changing its
semantics. The thread-based I/O/compute overlap captures the real, safe
parallelism opportunity here without introducing cross-process state-sharing
complexity for a stateful, sequential algorithm.

**63. What performance telemetry does the system record?**
Per-run: motion-detection stage duration and throughput (fps), total
pipeline duration, resolved algorithm (especially relevant for `auto`),
frames processed vs. frames skipped due to errors, and object-detection
cache hit/miss counts — stored as JSON in `Video.processing_stats` and shown
on the dashboard's Performance tab.

**64. How fast is it, roughly?**
On the bundled synthetic sample (640×360, 15fps, 20s, MOG2/frame_diff, CPU,
no object detection): motion detection alone runs at 500-700+ fps throughput
(i.e. processes a 20-second clip's sampled frames in a fraction of a
second). Real-world throughput depends heavily on resolution, algorithm
choice (optical flow is the slowest), and whether object detection is
enabled (the dominant cost when it is).

**65. What's the largest practical video size?**
`MAX_UPLOAD_MB` defaults to 8192 (8GB), comfortably covering a 3-hour 1080p
recording at typical bitrates. It's a config value, not a hard architectural
ceiling — increase it (and ensure disk space) for larger files.

**66. Does the frontend struggle with a video that has hundreds of events?**
No — the event log is paginated server-side (`GET /events/{id}?limit=&offset=`,
default page size 25 in the UI), and the video-player overlay only needs to
find the single active event at the current playback time (a linear scan
over up to 1000 fetched events, negligible cost).

---

## Database

**67. What's the schema?**
Four tables: `videos` → many `events` → many `rois` and many `detections`.
See the ER diagram in `SYSTEM_DESIGN.md` §6.

**68. What CHECK constraints exist, and why add them if Python already validates?**
Progress 0-100, `end_time >= start_time`, all scores/confidence in 0..1,
non-negative durations/dimensions, positive ROI width/height. They exist at
the DB layer as defense in depth — Python validation only protects paths
that go through the application code; a future raw SQL script, a migration,
or a bug in a new code path wouldn't be caught by Python-level checks alone.

**69. What indexes exist and why those specifically?**
Every column that appears in a `WHERE`, `ORDER BY`, or `sort_by` parameter
anywhere in the API: `Video.status`, `Video.created_at`, `Event.start_time`,
`Event.duration`, `Event.motion_score`, `Event.confidence`, plus the
pre-existing foreign keys and `Detection.label`. Chosen by auditing every
route's query, not added speculatively.

**70. How does cascade delete work?**
Two layers: the ORM declares `cascade="all, delete-orphan"` on every parent
relationship, so `session.delete(video)` issues explicit DELETE statements
for its events/ROIs/detections regardless of the database's own FK
enforcement. Additionally, `PRAGMA foreign_keys=ON` is enabled for every
SQLite connection (off by default in SQLite!) so the `ondelete="CASCADE"`
declared on each `ForeignKey` is *also* enforced at the database level —
defense in depth against any future code path that bypasses the ORM.

**71. Why is `PRAGMA foreign_keys=ON` not the SQLite default, and why does it matter here?**
SQLite disables FK enforcement by default for backward compatibility with
older SQLite versions/schemas. It matters here because without it, a raw
DELETE that bypasses the ORM (a future migration script, a manual `sqlite3`
session) could leave orphaned `events`/`rois`/`detections` rows with no
parent video — silently corrupting referential integrity in a way the
application would never notice until it tried to join against the missing
parent.

**72. Why store `processing_stats` as a JSON text column instead of a proper JSON column type?**
SQLite/Postgres portability — SQLAlchemy's native JSON column type behaves
differently (and isn't available at all pre-3.9) across SQLite versions,
while text + `json.dumps`/`json.loads` is universally portable and simple. A
Pydantic `field_validator` transparently parses it back to a dict for API
responses.

**73. How would this scale past SQLite's single-writer limitation?**
Change `DATABASE_URL` to a Postgres connection string — the schema,
constraints, and every query used are standard SQL/SQLAlchemy Core with no
SQLite-specific syntax (the one SQLite-specific piece, the FK pragma, is
gated behind a `startswith("sqlite")` check and simply doesn't apply to
Postgres, which enforces FKs by default anyway).

**74. Are there N+1 query problems anywhere?**
Explicitly guarded against with `selectinload()` on every route that returns
events with their ROIs/detections (`_events_for` in `analytics.py`,
`list_events` in the events route) — one extra query per related collection,
not one per row.

**75. How is pagination implemented at the database level?**
Standard SQL `LIMIT`/`OFFSET` via SQLAlchemy, with a separate
`SELECT COUNT(*)` (using the same filtered subquery) for the total count
surfaced in the `X-Total-Count` response header.

**76. What's the biggest risk of LIMIT/OFFSET pagination at scale, and does it matter here?**
OFFSET pagination gets slower as the offset grows (the database still has to
scan/skip the offset rows). At the scale this system operates at (a single
video's events, typically hundreds not millions), this is a non-issue;
keyset/cursor pagination would be the fix if a video ever had truly massive
event counts.

---

## API Design

**77. Is the API RESTful?**
Broadly yes — resource-oriented URLs (`/video/{id}`, `/events/{video_id}`),
standard HTTP verbs and status codes (201 on create, 202 on
async-job-accepted, 404/400/409/429/503/500 for their standard meanings).

**78. How is pagination exposed without breaking existing clients?**
Additively: `limit`/`offset` are optional query parameters with sane
defaults, and paging metadata (`X-Total-Count`, `X-Limit`, `X-Offset`) rides
in response *headers*, not the JSON body — so the response body shape is
completely unchanged and any client written against the pre-pagination API
keeps working exactly as before.

**79. Why headers instead of a wrapped envelope (`{items: [...], total: ...}`) for pagination?**
An envelope would be a breaking change to the response schema (every
existing client expecting a plain array would break). Headers let old and
new clients coexist without a version bump or a breaking migration.

**80. How are analysis jobs made asynchronous over HTTP?**
`POST /analyze/{id}` returns `202 Accepted` immediately with the video in a
`queued` state; the client polls `GET /video/{id}` for `status` and
`progress` (0-100) until it reaches `completed`/`failed`. This matches the
system's actual async nature (analysis can take much longer than an HTTP
request timeout) rather than blocking the request.

**81. What stops two simultaneous `POST /analyze` calls for the same video from both succeeding?**
An atomic conditional `UPDATE videos SET status='queued', ... WHERE id=? AND
status NOT IN ('queued','processing')`, checking `rowcount` to determine
which request "won." A plain read-then-write status check has a TOCTOU race
(see § General Q9's sibling, `SYSTEM_DESIGN.md` §8.4) that this closes.

**82. What does the API return on validation failure, a 404, a conflict, an internal error?**
Consistently `{"detail": "...", "error_type": "..."}` — validation errors
(400, `error_type: validation_error`), not-found (404), conflicts like
double-analyze (409, `error_type: rate_limited` reuses the same envelope
shape for 429), database issues (503, `database_error`, with the real
exception logged server-side but never leaked to the client), and anything
truly unexpected (500, `internal_error`) — via global FastAPI exception
handlers registered once in `main.py`, not scattered per-route try/excepts.

**83. Is rate limiting applied to every endpoint the same way?**
No — `/upload` and `/analyze/*` have their own (stricter) per-minute
budgets since they're the expensive/abusable endpoints; everything else
shares a higher default budget. Configured via `UPLOAD_RATE_LIMIT_PER_MINUTE`
etc.

**84. What does a 429 response look like?**
`{"detail": "Rate limit exceeded (10 requests/minute for this endpoint).
Retry after 23s.", "error_type": "rate_limited"}` with a standard
`Retry-After` header.

**85. Is the OpenAPI/Swagger documentation auto-generated or hand-written?**
Auto-generated by FastAPI from the route/schema type annotations, enriched
with explicit `summary`, `response_description` and `Field(description=...)`
on the routes/schemas that benefit from more context than the type alone
conveys (e.g. explaining the "auto" motion algorithm option, or the
pagination-via-headers behavior). View it live at `/docs`.

**86. What new endpoint was added specifically for dashboard/statistics purposes?**
`GET /stats` — aggregate counts across every uploaded video (total, by
status, total events, total footage duration, free disk space), for the
dashboard's top-level overview cards, computed via `func.count`/`func.sum`
aggregate queries rather than loading every video row into Python.

---

## Security

**87. What was the most severe security issue found, and how was it fixed?**
The database being publicly downloadable via the static file mount (§
General Q9 / `SYSTEM_DESIGN.md` §8.5). Fixed by relocating the DB outside
any served directory and mounting only specific named public subdirectories.

**88. How are uploaded files validated?**
Four layers: (1) extension allow-list (`mp4`/`avi`/`mov`/`mkv`), (2) a
`Content-Length` header pre-check to reject obviously oversized uploads
before writing any bytes, (3) streamed size enforcement while writing (never
holds the full file in memory), (4) a **magic-byte content-signature check**
(`validate_video_signature`) that the file's actual bytes match a real video
container (ISO-BMFF `ftyp`/`moov` for mp4/mov, RIFF+`AVI ` for avi, EBML
header for mkv) — not just its claimed extension.

**89. Why does the extension allow-list alone not suffice?**
A malicious or corrupt file can be named `payload.mp4` while containing
arbitrary bytes; without content validation this would only get rejected
indirectly (and later) when OpenCV fails to open it as a video, if it fails
cleanly at all. The magic-byte check rejects it immediately and precisely,
before any further processing.

**90. How is path traversal in uploaded filenames prevented?**
`sanitize_filename()` strips all path components via `Path(name).name`
(handles `../` and absolute paths), then a character allow-list regex
(`[^A-Za-z0-9._-]+` → `_`) strips anything else including Windows-style
backslashes (which aren't path separators on POSIX and so wouldn't be
stripped by `Path().name` alone) — verified by
`test_sanitize_filename_handles_windows_style_traversal` and an end-to-end
API test that actually attempts `../../../etc/passwd.mp4` as an upload
filename.

**91. What CORS policy is in place?**
An explicit origin allow-list (`CORS_ORIGINS` env var, defaults to
localhost dev origins), explicit method allow-list (`GET, POST, DELETE,
OPTIONS` — not wildcard), explicit header allow-list (`Content-Type,
Accept`), and credentials are automatically disabled if `*` is ever used as
an origin (browsers reject that combination anyway, but the app validates
it explicitly at startup too — see next question).

**92. What happens if I set `CORS_ORIGINS=*` alongside other explicit origins?**
The app refuses to start — a Pydantic model validator rejects mixing `*`
with explicit origins at config-load time, since that combination is either
meaningless or a misconfiguration, and CORS bugs are exactly the kind of
thing that should fail loudly at startup rather than silently at runtime.

**93. Is there rate limiting? What are its limits as a security control?**
Yes, a sliding-window in-process limiter on `/upload` and `/analyze`.
Explicitly documented as **not** a distributed/multi-worker-safe control —
each process enforces its own independent budget. Adequate for the default
single-node deployment; a horizontally-scaled production deployment should
swap in a Redis-backed limiter.

**94. Is there authentication?**
No — explicitly out of scope for this upgrade (adding real auth is separable,
significant work, and the instructions were to upgrade the existing system,
not introduce a new architectural layer). Documented plainly as a known
limitation rather than silently absent; deploy behind a trusted network
boundary or add an auth layer before public exposure.

**95. How are environment variables validated?**
Every numeric setting with a meaningful valid range has Pydantic `Field`
bounds (e.g. `motion_threshold: float = Field(ge=0.0, le=1.0)`) or a
`field_validator` (e.g. `default_motion_algorithm` must be one of the
supported values). A misconfigured `.env` fails fast at process startup with
a clear Pydantic `ValidationError`, rather than causing subtle wrong
behavior deep inside the CV pipeline at analysis time.

**96. Does the API leak stack traces or internal details on error?**
No — a global exception handler for unhandled exceptions logs the full
traceback server-side (`logger.exception(...)`) but returns only
`{"detail": "An unexpected error occurred.", "error_type": "internal_error"}`
to the client. Same pattern for database errors (503, generic message,
detail logged not returned).

**97. What about SQL injection?**
Not applicable in practice — every query goes through SQLAlchemy's Core/ORM
query builder with parameterized values; there is no raw string-interpolated
SQL anywhere in the codebase (the one raw SQL statement, `PRAGMA
foreign_keys=ON`, takes no user input).

**98. What about the video/report download endpoints — can I access another user's files by guessing IDs?**
There's no per-user ownership model in this version (see auth limitation,
Q94) — any client that can reach the API can access any video's clips,
heatmap, or reports by ID. This is a direct consequence of having no
authentication layer, not a separate bug; fixing it requires the auth work
noted as future scope.

---

## Frontend / UX

**99. What's the tech stack and why?**
React + strict TypeScript + Vite (fast dev server, small config surface),
Tailwind for styling, Radix UI primitives wrapped in shadcn-style components
for accessible, unstyled-by-default building blocks, React Query for all
server state (caching, polling, invalidation) instead of hand-rolled
fetch/useEffect state management, Recharts for the timeline and analytics
charts.

**100. How does the UI know when a background analysis job finishes?**
React Query polling: `useVideo(id)` and `useVideos()` both set
`refetchInterval` conditionally — only while a video's status is
`queued`/`processing` — so the dashboard and detail page update
automatically without a manual refresh, and polling stops (zero unnecessary
requests) once a job completes.

**101. What is the ROI/detection overlay on the video player, technically?**
An SVG layer absolutely positioned over the `<video>` element, using
`viewBox` set to the video's native pixel dimensions with
`preserveAspectRatio="xMidYMid meet"` — so ROI/detection boxes (stored in
native pixel coordinates from the backend) render correctly aligned
regardless of how the video element itself is scaled/letterboxed by CSS.

**102. How does the UI distinguish heuristic vs. confirmed detections?**
Dashed stroke instead of solid, a "possible" label prefix, opacity scaled by
detection confidence, and — at the event level — a distinct amber "Possible
prohibited item" badge versus the solid red "Prohibited object" badge used
only when a *non-heuristic* prohibited detection exists for the active
event.

**103. What is the timeline "zoom" feature?**
A Recharts `Brush` control beneath the motion-intensity chart — dragging its
handles narrows the main chart's X-axis domain to that range, useful for
inspecting a specific few seconds of a long recording without losing the
full-video context (the brush strip itself still shows the whole timeline).

**104. What is frame-by-frame inspection?**
Previous/next-frame step buttons next to the video player that pause
playback and advance `currentTime` by exactly `1/fps` seconds — for
precisely examining the single frame where a detection/ROI appears, rather
than only being able to scrub via the video's native (coarser) seek bar.

**105. How does pagination work in the frontend event table?**
`EventTable` maintains its own `page` state, requests 25 events per page via
`useEvents(id, {limit: 25, offset: page*25})`, and reads the total count
from the `X-Total-Count` response header (parsed by the API client's
`extractPageInfo` helper) to render "Showing X-Y of Z" and enable/disable
Previous/Next.

**106. Is the dashboard dark-mode only, or does it support light mode?**
The app defaults to dark mode (`class="dark"` on `<html>`), which is also
the primary aesthetic target, but the full Tailwind CSS variable theming
(`--background`, `--foreground`, etc. defined for both `:root` and `.dark`)
supports light mode too if the class is toggled.

**107. Is the UI responsive?**
Yes — grid layouts collapse from multi-column (dashboard video grid,
analytics stat cards) to single-column on narrow viewports via Tailwind's
responsive prefixes (`sm:`, `lg:`, `xl:`), and the video-detail page's
player/heatmap split stacks vertically below the `xl` breakpoint.

**108. How is upload progress shown?**
Axios's `onUploadProgress` callback drives a percentage shown both as text
and a `Progress` bar component during the upload; a separate, independently
polled `progress` field (0-100) from the backend drives a second progress
bar during the actual analysis phase — upload progress and analysis progress
are two different phases the UI represents distinctly.

**109. What loading states exist beyond a spinner?**
Skeleton placeholders (`Skeleton` component, matching the shape of the
eventual content) on the dashboard's video grid and the analytics panel
while their respective queries are in flight, rather than a generic
full-page spinner that discards layout context.

**110. Is the frontend covered by any automated tests?**
The upgrade prioritized backend test depth (143 tests) and verified the
frontend via `tsc --noEmit`-equivalent strict builds (`npm run build`, which
type-checks before bundling) plus a live browser smoke test (Playwright,
driving an actual running instance through upload → analyze → dashboard →
video detail → each tab) rather than a component-test suite — a reasonable
trade-off given the time budget, documented rather than silently skipped.

---

## Testing & Quality

**111. How many tests are there, and what do they cover?**
143 backend tests (up from 28 before this upgrade), spanning: motion
detection (adaptive thresholding, warm-up, resolution-scaled kernels, the
min_area regression), ROI detection (resolution-relative filtering,
contour-count cap), segmentation (smoothing, hysteresis, normalization),
object detection (label-mapping correctness, caching, batching, custom-model
hooks, GPU OOM recovery — all via a mocked model, no GPU/weights needed),
database constraints, config validation, rate limiting, SQL-aggregation
analytics correctness, and full API integration flows.

**112. How are YOLO/object-detection code paths tested without GPU or model weights?**
A lightweight fake model (`_FakeModel`/`_FakeResult`/`_FakeBox` classes
mimicking Ultralytics' `.predict()` return shape) is injected directly into
`ObjectDetector._model`, bypassing the real lazy-import entirely. This tests
all the detector's *logic* (label mapping, caching, batching, confidence
filtering, custom label maps, OOM recovery) deterministically and instantly,
independent of whether `ultralytics`/`torch` are even installed.

**113. Are there regression tests for the specific bugs found in this audit?**
Yes, explicitly, e.g.: `test_min_area_filters_score_not_just_boxes` (§8.1),
`test_book_is_not_relabelled_to_paper` (§8.2),
`test_object_counts_prohibited_flag_reflects_stored_data_not_static_set`
(§8.3), `test_double_analyze_returns_409` (§8.4),
`test_database_file_not_reachable_via_storage_mount` (§8.5).

**114. How is test isolation achieved (no shared state between test runs)?**
`conftest.py` provisions a fresh temp directory and SQLite database *before*
any application module is imported, sets every storage-path env var to point
into it, and disables rate limiting process-wide for the general suite
(rate limiting itself is tested separately against an independently
constructed middleware instance with injected — not env-derived — limits).

**115. What does CI actually run?**
Three parallel jobs (`.github/workflows/ci.yml`): backend lint (`ruff
check`) + full test suite with coverage; frontend `npm run build` (which
type-checks with strict TypeScript before bundling); and a Docker build of
both images — all three must pass on every push/PR.

**116. Is there a linter, and is the codebase clean?**
Ruff, configured in `pyproject.toml` (`E`, `F`, `I`, `UP`, `B`, `C4` rule
sets). `ruff check app tests` passes with zero warnings as of this upgrade.

**117. How would you verify the pipeline's segmentation output is actually correct, not just "doesn't crash"?**
The bundled synthetic sample video (`scripts/generate_sample_video.py`) has
three deliberately placed, precisely-timed motion windows; running the full
pipeline against it and asserting exactly three detected segments (with
timing that matches, within tolerance) is both a unit test
(`test_pipeline.py`) and a manual verification step documented in
`sample_data/README.md`.

**118. Is there load/stress testing for concurrent analysis or very long videos?**
Not automated in this pass — verified manually (a live end-to-end run
including a Playwright browser smoke test) but not via an automated
load-test suite. Documented as a reasonable scope trade-off, not silently
absent.

---

## Deployment & Operations

**119. How do I run this locally?**
`docker compose up --build` for the full stack (dashboard on `:8080`, API on
`:8000`), or `docker/none` — see `docs/INSTALLATION.md` for the manual
`uvicorn`/`npm run dev` path.

**120. How would I deploy this with GPU acceleration?**
Install the NVIDIA Container Toolkit, add a GPU device reservation to the
`backend`/`worker` Compose services, and set `YOLO_DEVICE=cuda`. Detailed in
`docs/DOCKER.md`.

**121. How do I scale analysis throughput horizontally?**
Set `TASK_BACKEND=celery`, run `docker compose --profile celery up`, and
scale the `worker` service (`--scale worker=N`); the API dispatches jobs to
Redis instead of a local thread, and multiple worker replicas consume from
the same queue.

**122. What's logged, and in what format?**
Structured logs throughout (timestamps, levels, logger names, and — for the
pipeline — per-stage timing/throughput via a `LogTimer` context manager).
Two output formats: human-readable text (default) or single-line JSON
(`LOG_FORMAT=json`) for log-aggregation systems (ELK/CloudWatch/Loki), where
custom fields (stage name, elapsed seconds, throughput) are queryable
structured JSON keys rather than needing to be grepped out of a text line.

**123. How would an operator notice the system is unhealthy?**
`GET /health` (liveness) and `GET /system` (capability report: FFmpeg
present, CUDA available, object detection loadable, free disk space) are
both cheap, dependency-free checks; both backend and frontend Docker images
also define container-level `HEALTHCHECK`s.

**124. What happens on a database outage mid-request?**
A global exception handler catches `SQLAlchemyError`, logs full detail
server-side, and returns a clean `503 Service Unavailable` with a
`database_error` error_type — rather than a raw driver traceback leaking to
the client.

**125. How is the SQLite database backed up / persisted across container restarts?**
The `storage` Docker named volume (which now also implicitly covers
`data_dir`, since Compose mounts the whole `/storage` parent in the current
setup — see next question for the nuance) persists across `docker compose
down`/`up` cycles; for production, back up the SQLite file directly or
migrate to Postgres with its own backup tooling.

**126. Wait — didn't you say the database must NOT be inside storage_dir?**
Correct, and it isn't served from there — `DATA_DIR` defaults to a sibling
directory (`<repo>/data` locally, `/data` in the container path convention)
distinct from `STORAGE_DIR`, and only `STORAGE_DIR`'s specific public
subdirectories are mounted by `StaticFiles`. The Docker volume persisting
both is purely about *durability across container restarts*, unrelated to
what's *served over HTTP* — those are two independent concerns and this
setup keeps them independent.

**127. What are the resource requirements for a typical deployment?**
Highly workload-dependent, but as a floor: the backend container needs
enough RAM to hold one frame-resolution heatmap accumulator plus the bounded
frame-reader queue (a handful of frames at a time) — not the whole video.
CPU-only object detection is the dominant cost when enabled; a GPU
dramatically improves that specific stage's throughput.

---

## Comparisons / "Why not X" / Trade-offs

**128. Why not use a pretrained video-understanding model (e.g. a temporal action detector) instead of classical CV motion detection?**
Classical background subtraction/frame differencing needs no training data,
no GPU for the motion stage, and is fully interpretable (a judge or operator
can see exactly why a frame was flagged — pixel-level foreground mask — not
a black-box embedding). A learned temporal model would likely generalize
better to complex scenes but is disproportionate engineering/data cost for
"detect motion in a mostly-static room."

**129. Why not run object detection on every frame for maximum recall?**
Enormous, mostly-wasted compute cost — the overwhelming majority of frames
in this use case have zero motion and thus zero chance of a relevant
detection. Running YOLO only on motion-segment representative frames cuts
inference volume by orders of magnitude on typical footage with minimal
recall loss (a real object present for a whole segment is very likely to
appear in at least one of its 1-3 representative frames).

**130. Why not a single combined "motion+object" deep model end-to-end?**
Would require either a custom-trained multi-task model (expensive,
needs domain-specific training data this project doesn't have) or an
off-the-shelf video model unlikely to be tunable to exam-hall-specific
notions of "prohibited item." The modular pipeline (classical CV for motion,
a swappable pretrained/fine-tunable detector for objects) is more
transparent, more debuggable stage-by-stage, and lets each stage use the
cheapest approach that actually works for its sub-problem.

**131. Why Recharts over D3 or a canvas-based charting library?**
Recharts is React-native (declarative components, not imperative DOM
manipulation), has a built-in `Brush` component that directly provided the
timeline-zoom feature with minimal custom code, and its bundle-size/feature
trade-off is appropriate for a handful of charts rather than needing D3's
full flexibility.

**132. Why Tailwind instead of a component library's own theming (e.g. MUI)?**
Full control over the exact visual design (the dark, data-dense dashboard
aesthetic) without fighting a pre-opinionated component library's defaults;
Radix primitives (unstyled, accessible) plus Tailwind gave shadcn-style
components tailored precisely to this app.

**133. Why not Next.js instead of Vite + React Router?**
No server-rendering or file-based-routing requirement here — this is a pure
client-side SPA talking to a separate FastAPI backend; Vite's dev server and
build are simpler and faster for that shape of app than bringing in a
full-stack meta-framework's SSR machinery for no SSR need.

**134. Why not store ROI/detection boxes as a JSON blob on the Event row instead of separate tables?**
Separate `ROI`/`Detection` tables allow indexing (`Detection.label`),
per-row CHECK constraints, and SQL-side aggregation (`GROUP BY label`) that
a JSON blob would require pulling out into Python to achieve — the
analytics endpoint's whole SQL-aggregation performance story (§ Performance
Q60) depends on `Detection` being real, queryable rows.

**135. Isn't hysteresis thresholding over-engineering for a hackathon project?**
It's a small, well-understood, cheap technique (a handful of lines) that
directly fixes a real, demonstrable failure mode (event fragmentation on
noisy real-world footage) — the opposite of over-engineering, which would be
adding complexity *without* a corresponding concrete problem it solves.

---

## Limitations & Honesty

**136. What's the single biggest capability gap in this system today?**
Reliable loose-paper/chit detection — the thing most directly relevant to
exam-hall cheating detection. COCO-pretrained YOLO simply has no class for
it; `book` is used as a clearly-labeled, imperfect heuristic proxy. Closing
this gap requires a fine-tuned custom model (the hook exists; the model
doesn't ship).

**137. If a judge asks "does this really work," what's the honest answer?**
Motion detection, ROI extraction, and event segmentation work well and are
validated against known-ground-truth synthetic footage (the 3-motion-window
sample video reliably produces exactly 3 events). Object detection for
`phone`/`person`/`bag`/`bottle`/`laptop` is as reliable as YOLOv11/COCO
generally is for those classes. `book`-as-prohibited-proxy is explicitly
weak and labeled as such. The system does not claim capabilities it doesn't
have — that honesty is itself a deliberate design choice, not an oversight.

**138. What would break this system in production that a demo wouldn't reveal?**
No authentication (anyone reachable can access/delete any video); the
in-process rate limiter not being multi-worker-safe; SQLite's single-writer
model under genuinely concurrent multi-user write load; and the `auto`
algorithm heuristic potentially mispicking on footage very different from
what it was designed around (e.g. a moving camera).

**139. Did you consider this a "rewrite" or an "upgrade," and how did you keep to the latter?**
Strictly an upgrade — every existing file, API contract, and database table
was preserved and extended, not replaced. New behavior is additive (new
optional query params, new response fields, new endpoints) rather than
changing existing response shapes; the one behavior change with real
external impact (motion scores now being normalized rather than raw) is a
values-only change to an already-opaque 0..1 field, not a schema or contract
break.

**140. What's the actual before/after on test coverage and code quality?**
28 → 143 backend tests. Multiple real, previously-undetected bugs fixed
(§ General Q9, and §8.1-8.4 in `SYSTEM_DESIGN.md`) with regression tests
added for each. Ruff lint clean throughout. Frontend strict-TypeScript build
clean throughout, verified against a live running instance (not just
`tsc`).
