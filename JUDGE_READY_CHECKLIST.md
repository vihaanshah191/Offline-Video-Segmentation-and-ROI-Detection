# Judge-Ready Checklist

A demo-day summary. For full detail, see `FEATURE_AUDIT.md` (feature-by-
feature status), `BUG_REPORT.md` (defects found/fixed), `PERFORMANCE_REPORT.md`,
`SECURITY_REPORT.md`, and `TEST_COVERAGE.md`.

## 60-second pitch

Fully offline video analytics for examination-hall (or similar
surveillance) recordings: motion detection → ROI extraction → event
segmentation → object detection → heatmaps → investigation-ready reports.
No cloud dependency at analysis time. Runs on CPU or GPU. Ships with a
one-click Demo Mode so a judge can see the whole pipeline run in under a
minute with zero setup.

## Before you demo

1. Start the backend and frontend (see `README.md` / `docker-compose.yml`).
2. Open the dashboard, click **Try demo** — this uploads the bundled
   sample video and starts analysis automatically. No file picker needed.
3. Once it completes (~seconds for the small bundled sample), you land on
   the results page with the video player, timeline, heatmap and analytics
   already populated.
4. Visit **/judge** for a presentation-ready overview (live counters,
   pipeline diagram, model info) if you want a slide-free walkthrough.

## What's genuinely done (✅ in `FEATURE_AUDIT.md`)

- Core CV pipeline: 3 motion algorithms + auto-select, adaptive
  thresholding, ROI merge, hysteresis segmentation, batched/cached YOLOv11
  object detection with an explicit heuristic-vs-confirmed distinction.
- Video player: independent overlay toggles, 0.25x–4x speed, prev/next
  event nav, skip-to-timestamp, custom fullscreen, PNG snapshot export.
- Timeline: zoom, severity-colored markers with hover thumbnail preview,
  time ruler, richer tooltips.
- Event log: thumbnails, severity, per-event clip download and JSON
  export, search/filter/sort/pagination.
- Analytics: 14 metrics including live CPU/memory/GPU usage, compression
  ratio, ROI area.
- Object detection: per-run confidence slider and class filter.
- Heatmap: whole-video and per-event, interactive opacity blend.
- PDF report: exec summary, system info, motion chart, heatmap, event
  snapshot, recommendations, appendix — genuinely multi-section, not a
  bare table.
- Dashboard: live queue view, system/model panel, recent analyses.
- Multi-video batch upload with per-file progress; explicit cancel and
  retry.
- Settings page, backed by a persisted, runtime-editable config.
- Auth: JWT + RBAC (admin/investigator/viewer) + audit log + session
  timeout — opt-in, zero impact on the default unauthenticated flow.
- Demo Mode (one-click) and Judge Mode (this page's sibling, `/judge`).
- 200 backend tests, all passing; every UI feature above was verified live
  in a real browser against a running backend (not just "the build
  succeeded").

## What's intentionally not done (❌ in `FEATURE_AUDIT.md`, with reasons)

- **Animated heatmap playback** — would require storing a time-sequence of
  frames, not one flattened image; a materially larger feature than an
  opacity slider.
- **Pause/resume for in-progress analysis** — genuinely infeasible with
  the thread-based worker (no way to suspend and resume an in-flight
  OpenCV decode loop mid-frame). Cancel (stop and discard) is implemented
  instead, honestly, rather than faking pause.
- **Bulk/multi-video export** — lower judge-value than the per-video PDF
  report; deferred.
- **Cross-video performance-history charts** on the dashboard — would need
  bulk-fetching every video's `processing_stats`; deferred as a separate
  feature.
- **Frontend unit-test harness** (Jest/RTL) — deliberately traded for more
  backend tests plus live browser verification this pass; see
  `TEST_COVERAGE.md` for the reasoning, including that live verification
  is what actually caught this session's two real bugs.

## Known limitations, said out loud

- Real multi-hour HD footage has not been benchmarked in this environment
  (no such source footage / GPU available) — see `PERFORMANCE_REPORT.md`.
- Rate limiting is single-process/in-memory — fine for one node, would
  need Redis behind multiple replicas.
- No dependency CVE scan or penetration test was run this pass.
- JWTs cannot be revoked early (no server-side session store); they expire
  on their own schedule instead.

## Honesty check

Every ✅ in `FEATURE_AUDIT.md` was either exercised by an automated test,
verified live in a browser, or both — cross-reference `TEST_COVERAGE.md`
if you want to know exactly which. Nothing above claims a feature exists
that isn't wired end-to-end: backend route → service → (frontend
component, if UI-facing) → verified working, not just "the code compiles."
