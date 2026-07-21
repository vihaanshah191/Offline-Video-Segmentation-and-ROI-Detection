# API Reference

Base URL: `http://localhost:8000/api`. Interactive OpenAPI docs: `/docs`
(Swagger) and `/redoc`.

All artefacts (heatmaps, clips, thumbnails) are served statically under
`/storage/<subdir>/...` where `<subdir>` is one of `videos`, `clips`,
`heatmaps`, `thumbnails` — these are the only publicly mounted directories;
the database and reports are never reachable this way.

## Error format

Every error response uses a consistent envelope:

```json
{ "detail": "human-readable message", "error_type": "validation_error" }
```

| `error_type` | Status | Meaning |
|---|---|---|
| `validation_error` | 400 | Bad input (unsupported file type, bad content signature, invalid parameter). |
| — | 404 | Resource not found. |
| — | 409 | Conflict (e.g. analysis already queued/processing for this video). |
| `rate_limited` | 429 | Too many requests to this endpoint group; see `Retry-After` header. |
| `database_error` | 503 | Database temporarily unavailable. |
| `internal_error` | 500 | Unexpected server error (full detail logged server-side, never leaked). |

## Rate limiting

Best-effort, single-process, sliding-window (per client IP). `/upload` and
`/analyze/*` have their own (stricter) budgets; everything else shares a
higher default. Configure via `UPLOAD_RATE_LIMIT_PER_MINUTE`,
`ANALYZE_RATE_LIMIT_PER_MINUTE`, `DEFAULT_RATE_LIMIT_PER_MINUTE`, or disable
with `RATE_LIMIT_ENABLED=false`. **Not** shared across multiple
worker processes/replicas — see `SYSTEM_DESIGN.md` → Known Limitations.

## Pagination

`GET /videos` and `GET /events/{id}` are paginated via `limit`/`offset` query
parameters. This is **additive and non-breaking**: the JSON response body is
still a plain array (unchanged shape); paging metadata rides in response
headers instead:

| Header | Meaning |
|---|---|
| `X-Total-Count` | Total matching rows across all pages. |
| `X-Limit` | The `limit` actually applied. |
| `X-Offset` | The `offset` actually applied. |

---

## System

### `GET /health`
Liveness probe. → `{ "status": "ok", "app": "...", "version": "1.1.0" }`

### `GET /system`
Backend capabilities.
```json
{
  "version": "1.1.0",
  "ffmpeg": true,
  "cuda": false,
  "object_detection": true,
  "default_motion_algorithm": "mog2",
  "free_disk_bytes": 123456789,
  "allowed_extensions": ["avi", "mkv", "mov", "mp4"]
}
```

### `GET /stats`
Aggregate counts across every uploaded video (dashboard overview).
```json
{
  "total_videos": 5, "completed_videos": 3, "processing_videos": 1,
  "failed_videos": 0, "total_events": 47, "total_video_duration_seconds": 7230.0,
  "free_disk_bytes": 31292059648
}
```

---

## Videos

### `POST /upload`
`multipart/form-data` with field `file`. → **201** `VideoDetail`.

```bash
curl -F "file=@sample.mp4" http://localhost:8000/api/upload
```

Validation, in order: extension allow-list → `Content-Length` pre-check →
streamed size enforcement → **magic-byte content-signature check** (the
file's actual bytes must match a real video container for its extension —
an `.mp4` renamed from a non-video file is rejected here, not just on
extension). Errors: **400** on any of the above; **429** if rate-limited.

### `GET /videos`
List videos, newest first, paginated.

| Query param | Default | Notes |
|---|---|---|
| `limit` | 100 | 1-500 |
| `offset` | 0 | ≥0 |

→ `VideoRead[]`, with `X-Total-Count`/`X-Limit`/`X-Offset` headers.

### `GET /video/{id}`
Video detail incl. `progress`, `status`, `event_count`, `processing_stats`.
→ `VideoDetail` / **404**.

```json
{
  "id": 1, "status": "completed", "progress": 100.0,
  "motion_algorithm": "frame_diff",
  "processing_stats": {
    "events": 3, "samples": 150, "frames_processed": 150,
    "frames_with_errors": 0, "object_detection": false,
    "resolved_motion_algorithm": "frame_diff",
    "motion_detection_seconds": 0.21, "motion_detection_throughput_fps": 713.3,
    "total_pipeline_seconds": 0.94,
    "object_detection_cache_hits": 0, "object_detection_cache_misses": 0
  },
  "...": "..."
}
```

### `DELETE /video/{id}`
Delete a video and every artefact + DB row (cascade). →
`{ "message": "Video 1 deleted" }`.

---

## Analysis

### `POST /analyze/{id}`
Queue an offline analysis run. → **202** `VideoDetail` (status `queued`).

```json
{
  "motion_algorithm": "auto",          // mog2 | frame_diff | optical_flow | auto
  "enable_object_detection": true,
  "frame_sample_step": 2,               // optional, 1..60
  "min_motion_area": 800                // optional, px^2
}
```

`"auto"` pre-scans the video and resolves to whichever concrete algorithm
best fits its lighting/noise characteristics; the resolved choice (never the
literal string `"auto"`) is what gets recorded on `video.motion_algorithm`
and returned in `processing_stats.resolved_motion_algorithm`.

Errors: **400** bad algorithm, **404** missing, **409** already
queued/processing for this video (an atomic DB-level check prevents a
double-enqueue race even under near-simultaneous requests), **429**
rate-limited.

---

## Results

### `GET /events/{id}`
Searchable, filterable, sortable, **paginated** event log.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `search` | string | — | Filter by object label substring. |
| `prohibited_only` | bool | false | Only events with a prohibited detection (applied after pagination — see note below). |
| `min_score` | float | 0 | Minimum normalized motion score (0..1). |
| `sort_by` | enum | `start_time` | `start_time`\|`duration`\|`motion_score`\|`confidence`. |
| `order` | enum | `asc` | `asc`\|`desc`. |
| `limit` | int | 200 | 1-1000. |
| `offset` | int | 0 | ≥0. |

→ `EventRead[]` (each includes `rois[]` and `detections[]`, each detection
including a `heuristic: bool` field — see below), with pagination headers.

> **Note:** `prohibited_only` is applied in Python after the paginated SQL
> query (it depends on the related `detections` collection, not a directly
> filterable/paginated column), so a page may return fewer than `limit` items
> when combined with pagination on a video with sparse prohibited-object
> hits. This is documented, not a bug.

**Detection fields:**
```json
{
  "id": 1, "label": "book", "confidence": 0.61, "timestamp": 12.4,
  "prohibited": true, "heuristic": true, "x": 10, "y": 20, "w": 80, "h": 100
}
```
`heuristic: true` means this label is a proxy for a concept the model has no
direct class for (e.g. "book" standing in for "possible notes"), not a
confident, direct detection — see `SYSTEM_DESIGN.md` § Object Detection.

### `GET /clips/{id}`
Generated clips with URLs (not paginated). → array of
`{ event_id, start_time, end_time, duration, motion_score, objects[], clip_url, thumbnail_url }`.

### `GET /clips/{id}/{event_id}/download`
Download an event clip (`video/mp4`).

### `GET /heatmap/{id}`
```json
{ "video_id": 1, "heatmap_url": "/storage/heatmaps/video_1.png",
  "width": 640, "height": 360, "generated": true }
```

### `GET /heatmap/{id}/download`
Download the heatmap PNG.

### `GET /timeline/{id}`
Down-sampled motion timeline + event markers. `motion_score` values are
video-relative normalized (0..1, where 1.0 = the most active moment in this
recording).
```json
{
  "video_id": 1, "duration": 20.0, "fps": 15.0, "sample_interval": 0.5,
  "points": [{ "time": 0.0, "motion_score": 0.0, "active": false, "objects": [] }],
  "event_markers": [{ "id": 1, "start": 2.0, "end": 6.4, "objects": [] }]
}
```

### `GET /analytics/{id}`
Computed via SQL-side aggregation (not loaded-then-reduced in Python — see
`SYSTEM_DESIGN.md` § Performance).
```json
{
  "video_id": 1, "total_events": 3, "total_motion_duration": 14.27,
  "motion_coverage": 0.71, "average_motion_score": 0.566,
  "peak_motion_score": 1.0, "peak_activity_time": 14.0,
  "longest_event_duration": 5.47, "longest_event_id": 3,
  "total_detections": 0, "prohibited_detections": 0, "object_counts": []
}
```
`object_counts[].prohibited` reflects what was actually stored on the
underlying `Detection` rows for that label (`MAX(prohibited)` grouped by
label), not a hardcoded label set — correct even when a video was analyzed
with a custom model that has its own prohibited-label configuration.

---

## Reports

### `GET /report/{id}/csv`
Event log as CSV (`text/csv`, attachment).

### `GET /report/{id}/pdf`
Full PDF investigation report (`application/pdf`). **501** if ReportLab is not
installed.

---

## Status codes

| Code | Meaning |
|------|---------|
| 200 | OK |
| 201 | Created (upload) |
| 202 | Accepted (analysis queued) |
| 400 | Validation error |
| 404 | Resource not found |
| 409 | Analysis already queued/processing |
| 429 | Rate limited |
| 500 | Unexpected internal error |
| 501 | Feature unavailable (e.g. PDF without ReportLab) |
| 503 | Database temporarily unavailable |
