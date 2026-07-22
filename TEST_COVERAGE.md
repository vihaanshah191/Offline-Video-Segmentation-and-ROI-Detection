# Test Coverage

200 backend tests pass (`cd backend && python -m pytest tests/ -q`), across
19 files. Below is what each covers, followed by what's *not* covered by
automated tests and how those gaps were actually verified instead.

## Backend test inventory (200 tests)

| File | Tests | Covers |
|---|---|---|
| `test_config.py` | 22 | Settings validation, fail-fast on bad env values |
| `test_motion_detection.py` | 21 | MOG2/frame-diff/optical-flow, adaptive thresholding, auto-select |
| `test_validation.py` | 20 | Upload validation: extension, magic bytes, size limits |
| `test_auth.py` | 18 | JWT roundtrip, password hashing, RBAC per role, audit log, seed-admin idempotency, session/deactivation |
| `test_api.py` | 17 | Full upload→analyze→events→timeline→report flow, pagination, CORS regressions, path-traversal guard |
| `test_object_detection.py` | 16 | YOLO detection, caching, class filtering, custom-model hooks |
| `test_database_constraints.py` | 14 | CHECK constraints, indexes, cascade delete |
| `test_segmentation.py` | 13 | Hysteresis thresholding, temporal smoothing, event merging |
| `test_analytics.py` | 11 | Aggregate stats (incl. this pass's new fields), timeline construction, severity on markers |
| `test_cancellation.py` | 11 | Cooperative cancellation: service layer, pipeline check, full API round-trip |
| `test_geometry.py` | 7 | Box IoU/merge/union utilities |
| `test_schemas.py` | 7 | Severity classification, clip/thumbnail/heatmap URL derivation |
| `test_settings_api.py` | 6 | Runtime settings get/update/reset, RBAC gating |
| `test_rate_limit.py` | 5 | Rate-limit middleware |
| `test_report.py` | 4 | CSV export, PDF generation (against a real pipeline-processed video, empty-video edge case, API endpoint) |
| `test_demo.py` | 3 | Demo Mode: full flow, disabled-mode 404, missing-file 400 |
| `test_pipeline.py` | 3 | End-to-end pipeline run, PipelineConfig serialization regression |
| `test_tasks.py` | 2 | Concurrency-cap enforcement (deterministic, event/counter-based) |

## Coverage added this pass (new this session, not present before)

- Auth/RBAC/audit log — previously didn't exist at all.
- Runtime settings API — previously didn't exist.
- Cooperative cancellation — previously didn't exist.
- Analytics extensions (avg event duration, ROI area, top object,
  compression ratio) and the shared severity classifier.
- URL-derivation for clip/thumbnail/heatmap paths (`EventRead`/`VideoDetail`).
- PDF/CSV report generation — **previously had zero tests** despite being
  a claimed feature since the prior pass; now covered against a real
  pipeline-generated video (not just a mock), plus an edge case (zero
  events) and the actual HTTP endpoint.
- Demo Mode.
- The two CORS regressions (`BUG_REPORT.md` #1, #2) — each has a
  regression test that was confirmed to fail without its corresponding fix.
- The Celery-serialization bug (`BUG_REPORT.md` #3) — regression test
  round-trips `PipelineConfig` through `dataclasses.asdict()`.
- The concurrency-cap fix — two deterministic tests (not sleep/timing
  dependent beyond a fixed synchronization window) verifying 1-slot and
  2-slot caps are actually respected.

## What's not covered by automated tests, and how it was verified instead

**Frontend: no Jest/React Testing Library unit-test harness.** This is a
real, honest gap — not a euphemism. It was not set up this pass because
the marginal value of introducing a whole new test toolchain
(configuration, mocking React Query/router, snapshot maintenance) for a
UI that was being actively, rapidly iterated on was judged lower than
spending that time on: (a) more backend test coverage for genuinely new
business logic, and (b) *live* verification, which catches a different
and arguably more relevant class of bug for this project — see
`BUG_REPORT.md`, where both real cross-origin CORS bugs were only
catchable by an actual browser enforcing actual CORS semantics, something
no unit test (React Testing Library included, since it doesn't run in a
real browser with real preflight behavior) would have caught.

Instead, every UI-facing feature added this pass was verified by:
1. `tsc --noEmit` in strict mode (`noUnusedLocals`, `noUnusedParameters`)
   after every change — catches type errors and dead code immediately.
2. A production `vite build` after every batch of changes.
3. A live Playwright session against a real running backend: upload a
   video, run analysis, and click through the actual feature (not a
   mock) — done for the video player controls, timeline hover/markers,
   event log actions, Settings page save, multi-file batch upload, Demo
   Mode's one-click flow, and the heatmap opacity blend — with the
   browser's console checked for zero errors each time, and screenshots
   taken and visually inspected (not just "did it crash").

This live-verification discipline is also what caught the two CORS bugs
and the heatmap-directory-layout false alarm documented in `BUG_REPORT.md`
— none of which a mocked unit test would have surfaced.

**Not benchmarked/load-tested**: see `PERFORMANCE_REPORT.md`'s "Not
benchmarked" section — real multi-hour footage, GPU inference, concurrent
multi-user load, and Celery-backend throughput under real distributed
workers.

**Not security-audited this pass**: dependency CVE scanning and
penetration testing — see `SECURITY_REPORT.md`'s closing section.
