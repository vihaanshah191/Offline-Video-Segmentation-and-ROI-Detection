# Performance Report

Architectural performance design (streaming pipeline, bounded queues,
two-pass strategy) is documented in detail in `SYSTEM_DESIGN.md`. This
report covers what changed and was measured during this pass, and states
plainly what has and hasn't been benchmarked at real scale.

## What changed this pass

1. **Enforced the concurrency cap.** `settings.max_concurrent_analyses`
   (default 2) was declared but never wired up — every queued analysis ran
   in its own unbounded thread. Fixed via a module-level semaphore in
   `workers/tasks.py` (see `BUG_REPORT.md` / commit `ea7d29f`). This
   matters specifically because this pass also added multi-file batch
   upload: without the cap, batch-uploading and analyzing N videos at once
   would spawn N concurrent full-video decode + CV threads with no bound,
   which is a straightforward way to exhaust CPU/memory on a single host.
2. **New per-run configurability.** `object_detection_confidence` and
   `object_detection_classes` are now per-request overrides (Analyze
   dialog), not just deploy-time settings — no measurable perf cost, since
   they're passed straight to the existing `ObjectDetector` constructor.
3. **Per-event heatmaps add negligible overhead.** Generated from
   already-computed ROI boxes (pass-one output), not a second video decode
   — see `_generate_event_heatmap` in `pipeline.py`. Cost is proportional
   to (samples in the event × ROI boxes per sample), which is small
   relative to the motion-detection pass itself.
4. **New `/api/system` resource sampling** (`psutil.cpu_percent`,
   `virtual_memory()`) uses a 0.05s blocking sample per call. The dashboard
   polls this every 10s — negligible load, but worth knowing it's a
   real (if tiny) blocking call on the request thread, not free telemetry.

## Measured (small-scale, this session)

Using the bundled synthetic sample (`sample_data/sample_exam_hall.mp4`:
320×240 or 640×360, 15 fps, 12–20s, MOG2/frame_diff, object detection
disabled):

| Metric | Observed |
|---|---|
| Motion-detection throughput | ~560–570 fps (180 frames in ~0.32s) |
| Full pipeline (motion + segmentation + event materialisation) | ~0.4–0.6s total |
| Per-event heatmap generation | included in the above; not separately measurable at this scale (sub-millisecond) |

**These numbers are from a tiny synthetic 320×240–640×360 clip, not a real
multi-hour 1080p/4K exam-hall recording, and are not representative of
production throughput.** They confirm the pipeline runs correctly and the
new features (per-event heatmap, concurrency cap, object-detection
overrides) don't introduce an obvious regression at this scale — they are
not a substitute for a real load test against multi-hour HD footage, which
this pass did not have the time or source footage to run. `SYSTEM_DESIGN.md`
documents the architectural reasoning (bounded frame queue, two-pass design,
fixed-size float32 heatmap accumulator) that this small-scale run is
consistent with, but that reasoning has not been re-validated at real scale
in this pass.

## Known scaling considerations (unchanged from prior pass, still accurate)

- **Frame buffer bound** (`frame_buffer_size`, default 64) caps memory
  growth if CV processing falls behind decode — a fixed-size safeguard
  independent of video length.
- **Heatmap accumulator** is a single `float32` array sized to frame
  resolution, independent of video duration — a 3-hour recording costs the
  same heatmap memory as a 3-minute one.
- **Object detection is two-pass**: the full video is decoded once for
  motion detection; object detection only re-seeks to a handful of
  representative frames per *event* (not per frame), which is what makes
  YOLO inference tractable on multi-hour footage.
- **Rate limiting is single-process, in-memory** (documented as a known
  limitation in `SYSTEM_DESIGN.md`) — still true, unchanged.
- **SQLite is single-writer.** The new concurrency cap indirectly helps
  here too: fewer simultaneous analysis threads means fewer simultaneous
  writers contending for SQLite's write lock during progress updates.

## Not benchmarked / explicitly out of scope for this pass

- Real multi-hour (2–4h) 1080p/4K footage end-to-end timing.
- GPU vs CPU YOLO inference throughput comparison (this environment has no
  GPU available to test against).
- Concurrent multi-user load (the auth/RBAC system supports multiple
  accounts, but no multi-user concurrent-load test was run).
- Celery-backend throughput under real Redis-backed distributed workers
  (verified functionally correct — see `BUG_REPORT.md` item 3 — but not
  load-tested).
