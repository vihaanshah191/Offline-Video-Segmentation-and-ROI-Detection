# API Reference

Base URL: `http://localhost:8000/api`. Interactive OpenAPI docs: `/docs`
(Swagger) and `/redoc`.

All artefacts (heatmaps, clips, thumbnails) are served statically under
`/storage/...`.

---

## System

### `GET /health`
Liveness probe. → `{ "status": "ok", "app": "...", "version": "1.0.0" }`

### `GET /system`
Backend capabilities.
```json
{
  "version": "1.0.0",
  "ffmpeg": true,
  "cuda": false,
  "object_detection": true,
  "default_motion_algorithm": "mog2",
  "free_disk_bytes": 123456789,
  "allowed_extensions": ["avi", "mkv", "mov", "mp4"]
}
```

---

## Videos

### `POST /upload`
`multipart/form-data` with field `file`. → **201** `VideoDetail`.

```bash
curl -F "file=@sample.mp4" http://localhost:8000/api/upload
```

Errors: **400** unsupported extension / empty / unreadable / too large.

### `GET /videos`
List all videos (newest first). → `VideoRead[]`.

### `GET /video/{id}`
Video detail incl. `progress`, `status`, `event_count`. → `VideoDetail` / **404**.

### `DELETE /video/{id}`
Delete a video and every artefact + DB row. → `{ "message": "Video 1 deleted" }`.

---

## Analysis

### `POST /analyze/{id}`
Queue an offline analysis run. → **202** `VideoDetail` (status `queued`).

```json
{
  "motion_algorithm": "mog2",           // mog2 | frame_diff | optical_flow
  "enable_object_detection": true,
  "frame_sample_step": 2,                // optional, 1..30
  "min_motion_area": 800                 // optional, px^2
}
```

Poll `GET /video/{id}` for `progress` (0–100) and `status`
(`processing` → `completed` / `failed`). Errors: **400** bad algorithm, **404**
missing, **409** already processing.

---

## Results

### `GET /events/{id}`
Searchable event log. Query params:

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `search` | string | — | Filter by object label substring. |
| `prohibited_only` | bool | false | Only events with prohibited objects. |
| `min_score` | float | 0 | Minimum motion score. |
| `sort_by` | enum | `start_time` | `start_time`\|`duration`\|`motion_score`\|`confidence`. |
| `order` | enum | `asc` | `asc`\|`desc`. |

→ `EventRead[]` (each includes `rois[]` and `detections[]`).

### `GET /clips/{id}`
Generated clips with URLs. → array of `{ event_id, start_time, end_time, duration, motion_score, objects[], clip_url, thumbnail_url }`.

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
Down-sampled motion timeline + event markers.
```json
{
  "video_id": 1, "duration": 20.0, "fps": 15.0, "sample_interval": 0.5,
  "points": [{ "time": 0.0, "motion_score": 0.0, "active": false, "objects": [] }],
  "event_markers": [{ "id": 1, "start": 2.0, "end": 6.4, "objects": [] }]
}
```

### `GET /analytics/{id}`
```json
{
  "video_id": 1, "total_events": 3, "total_motion_duration": 14.27,
  "motion_coverage": 0.71, "average_motion_score": 0.023,
  "peak_motion_score": 0.034, "peak_activity_time": 14.0,
  "longest_event_duration": 5.47, "longest_event_id": 3,
  "total_detections": 0, "prohibited_detections": 0, "object_counts": []
}
```

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
| 409 | Analysis already in progress |
| 501 | Feature unavailable (e.g. PDF without ReportLab) |
