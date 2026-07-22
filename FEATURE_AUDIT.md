# Feature Audit

Legend: ✅ Fully implemented & tested · ⚠ Partially implemented · ❌ Missing

This audit compares README/SYSTEM_DESIGN claims against actual backend
(`backend/app/`), frontend (`frontend/src/`) and test (`backend/tests/`)
code, as of the start of this work pass. It is the working checklist for
everything implemented below; the final state is re-audited in
`JUDGE_READY_CHECKLIST.md`.

## Core pipeline

| Feature | Status | Notes |
|---|---|---|
| MOG2 / frame-diff / optical-flow / auto motion detection | ✅ | `motion_detection.py`, tested |
| Adaptive (Otsu) thresholding, resolution-scaled morphology | ✅ | tested |
| ROI extraction + merge + resolution-relative filtering | ✅ | `roi_detection.py`, tested |
| Segmentation: smoothing + hysteresis + normalization | ✅ | `segmentation.py`, tested |
| YOLOv11 object detection, batched, cached, custom-model hook | ✅ | `object_detection.py`, tested |
| Heatmap (whole-video) | ✅ | `heatmap.py` |
| Per-event heatmap | ❌ | only a single whole-video heatmap is generated |
| Clip generation (FFmpeg + OpenCV fallback) | ✅ | tested |
| CSV / PDF report | ⚠ | CSV complete; PDF has only summary + event table, missing exec summary/system info/graphs/heatmap image/ROI snapshots/recommendations/appendix per README's own claim |

## Video player

| Feature | Status |
|---|---|
| ROI overlay | ✅ |
| Bounding box (detection) overlay | ✅ |
| Toggle overlays on/off | ✅ (single toggle for both; not independent) |
| Heatmap overlay on player | ❌ (heatmap is a separate panel, not overlaid on video) |
| Frame-by-frame controls | ✅ |
| Playback speed control | ❌ |
| Previous/next detected event navigation | ❌ |
| Skip to timestamp (manual entry) | ❌ |
| Fullscreen | ⚠ (native browser `<video controls>` fullscreen only, no custom button/overlay-aware fullscreen) |
| Snapshot export | ❌ |

## Timeline

| Feature | Status |
|---|---|
| Zoom | ✅ (Recharts Brush) |
| Pan | ⚠ (achievable by re-dragging the brush; no dedicated pan/drag-to-scroll) |
| Click to seek | ✅ |
| Hover tooltips | ⚠ (shows motion % only, not objects/severity) |
| Event markers | ✅ |
| Object icons on markers | ❌ |
| Severity colors | ❌ |
| ROI preview on hover | ❌ |
| Time ruler | ⚠ (X-axis ticks only, no dedicated ruler strip) |

## Event log

| Feature | Status |
|---|---|
| Thumbnail | ⚠ (available via clips endpoint, not shown in the event table itself) |
| Timestamp / duration / motion score / confidence | ✅ |
| Detected objects (with heuristic flag) | ✅ |
| ROI image | ❌ |
| Severity | ❌ (no severity concept exists yet) |
| Jump to video | ✅ |
| Download clip | ✅ (from Clips tab, not from the event row itself) |
| Export single event | ❌ (only whole-video CSV export exists) |
| Search / filter / sort / pagination | ✅ |

## Analytics

| Feature | Status |
|---|---|
| Total events, motion duration, peak activity, avg motion, longest event | ✅ |
| Average event duration | ❌ |
| Maximum motion (peak) | ✅ (`peak_motion_score`) |
| Total ROI area | ❌ |
| Object counts / top object | ⚠ (counts yes via chart; "top" not explicitly surfaced) |
| Processing FPS | ✅ (`processing_stats.motion_detection_throughput_fps`) |
| CPU / GPU / memory usage | ❌ |
| Video compression ratio | ❌ |
| Analysis time | ✅ (`processing_stats.total_pipeline_seconds`) |
| Storage usage | ✅ (`/api/stats.free_disk_bytes`, global only, not per-video) |

## Object detection

| Feature | Status |
|---|---|
| Batch inference | ✅ |
| Confidence slider (UI) | ❌ (backend supports per-run confidence only via settings, not exposed as a request param or UI control) |
| Object/class filtering (UI) | ❌ |
| Custom models / future fine-tuned weights | ✅ |
| Multiple YOLO versions | ⚠ (any Ultralytics-compatible weights work via `yolo_model`/`custom_yolo_model_path`, but not selectable per-run from the UI) |
| Detection statistics | ⚠ (counts via analytics; no dedicated stats view) |
| Bounding box customization (color/style) | ❌ |

## Heatmap

| Feature | Status |
|---|---|
| Whole-video heatmap | ✅ |
| Per-event heatmap | ❌ |
| Animated playback | ❌ |
| Interactive heatmap | ❌ |
| Heat intensity legend | ✅ |
| Opacity slider | ❌ |
| Download PNG | ✅ |

## Dashboard

| Feature | Status |
|---|---|
| Video grid + stats cards | ✅ |
| Recent analyses | ⚠ (video grid is sorted newest-first, but not a distinct "recent activity" feed) |
| Processing queue view | ❌ |
| Model information | ❌ |
| GPU status | ⚠ (`/api/system` returns `cuda: bool`; not surfaced in UI) |
| Storage statistics | ✅ |
| Performance charts | ❌ |
| Processing history | ❌ |

## Multi-video / batch

| Feature | Status |
|---|---|
| Batch uploads | ❌ (upload UI accepts one file at a time) |
| Queue processing | ⚠ (backend can run multiple thread-workers concurrently; no explicit queue/concurrency cap or visibility) |
| Progress tracking | ✅ (per-video) |
| Pause / resume | ❌ |
| Cancel | ❌ |
| Retry failed jobs | ⚠ (re-clicking Analyze on a failed video works; no dedicated "Retry" affordance) |

## Settings

| Feature | Status |
|---|---|
| Settings page (UI) | ❌ |
| Persisted, runtime-editable settings | ❌ (all configuration is env-var/`.env`, requires restart) |

## Security

| Feature | Status |
|---|---|
| Upload validation (extension + magic bytes) | ✅ |
| Rate limiting | ✅ |
| CORS hardening | ✅ |
| DB isolation from public storage mount | ✅ |
| Authentication | ❌ |
| JWT | ❌ |
| Role-based access (admin/investigator/viewer) | ❌ |
| Audit log | ❌ |
| Session timeout | ❌ |

## API completeness

| Endpoint | Status |
|---|---|
| Health | ✅ `/api/health` |
| System capabilities | ✅ `/api/system` |
| Global stats | ✅ `/api/stats` |
| Settings (get/update) | ❌ |
| Job/queue status (list in-flight jobs) | ❌ (per-video status exists; no aggregate queue view) |
| Export (CSV/PDF) | ✅ per-video; ❌ no bulk/multi-video export |
| Auth (login/token) | ❌ |

## Demo Mode / Judge Mode

| Feature | Status |
|---|---|
| Bundled sample video | ✅ (`sample_data/`) |
| One-click "load sample + analyze" | ❌ |
| Guided tour | ❌ |
| Judge/presentation mode (pipeline animation, live counters, architecture diagram) | ❌ |

## Tests

| Area | Status |
|---|---|
| Motion/ROI/segmentation/object-detection unit tests | ✅ (extensive) |
| API integration tests | ✅ |
| Database constraint tests | ✅ |
| Config/security/rate-limit tests | ✅ |
| Frontend component tests | ❌ (verified via strict build + manual/Playwright smoke only) |
| Auth/settings/queue tests | ❌ (features don't exist yet) |

---

**Summary at audit time:** the core AI pipeline, security hardening, and base
dashboard are genuinely production-quality (✅ throughout). The gaps are
concentrated in presentation/UX polish (player controls, timeline richness,
event-log severity/ROI-image, heatmap interactivity), operational features
(settings page, queue visibility, batch upload), and two subsystems that
don't exist at all yet (authentication/RBAC, demo/judge presentation modes).
The rest of this pass closes as many of these as are honestly achievable in
one session, in priority order, and documents what's intentionally deferred.
