"""API/integration tests covering the full HTTP surface."""
from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

API = "/api"


def _upload(client: TestClient, sample_video_path: Path) -> dict:
    with sample_video_path.open("rb") as fh:
        resp = client.post(
            f"{API}/upload",
            files={"file": ("sample.mp4", fh, "video/mp4")},
        )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_health(client: TestClient) -> None:
    resp = client.get(f"{API}/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_upload_rejects_bad_extension(client: TestClient) -> None:
    resp = client.post(
        f"{API}/upload",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 400


def test_upload_and_metadata(client: TestClient, sample_video_path: Path) -> None:
    data = _upload(client, sample_video_path)
    assert data["width"] == 320
    assert data["height"] == 240
    assert data["duration"] > 0
    assert data["status"] == "uploaded"


def test_full_analysis_flow(client: TestClient, sample_video_path: Path) -> None:
    video = _upload(client, sample_video_path)
    video_id = video["id"]

    # Kick off analysis (runs in a background thread with the thread backend).
    resp = client.post(
        f"{API}/analyze/{video_id}",
        json={"motion_algorithm": "mog2", "enable_object_detection": False},
    )
    assert resp.status_code == 202

    # Poll until completion (bounded).
    status = ""
    for _ in range(120):
        detail = client.get(f"{API}/video/{video_id}").json()
        status = detail["status"]
        if status in ("completed", "failed"):
            break
        time.sleep(0.5)
    assert status == "completed", f"analysis did not complete: {status}"

    # Events.
    events = client.get(f"{API}/events/{video_id}").json()
    assert len(events) >= 1
    assert "rois" in events[0]

    # Timeline.
    timeline = client.get(f"{API}/timeline/{video_id}").json()
    assert timeline["duration"] > 0
    assert len(timeline["points"]) > 0

    # Analytics.
    analytics = client.get(f"{API}/analytics/{video_id}").json()
    assert analytics["total_events"] >= 1

    # Heatmap metadata + download.
    heatmap = client.get(f"{API}/heatmap/{video_id}").json()
    assert heatmap["generated"] is True
    dl = client.get(f"{API}/heatmap/{video_id}/download")
    assert dl.status_code == 200
    assert dl.headers["content-type"] == "image/png"

    # Clips.
    clips = client.get(f"{API}/clips/{video_id}").json()
    assert len(clips) >= 1

    # CSV export.
    csv = client.get(f"{API}/report/{video_id}/csv")
    assert csv.status_code == 200
    assert "event_id" in csv.text

    # Delete.
    deleted = client.delete(f"{API}/video/{video_id}")
    assert deleted.status_code == 200
    assert client.get(f"{API}/video/{video_id}").status_code == 404


def test_analyze_missing_video(client: TestClient) -> None:
    assert client.post(f"{API}/analyze/999999").status_code == 404


def test_events_missing_video(client: TestClient) -> None:
    assert client.get(f"{API}/events/999999").status_code == 404


def test_upload_rejects_content_extension_mismatch(client: TestClient) -> None:
    """A file with a video extension but non-video bytes must be rejected by
    the magic-byte signature check, not merely by the extension allow-list."""
    resp = client.post(
        f"{API}/upload",
        files={"file": ("fake.mp4", b"not actually a video, just some bytes", "video/mp4")},
    )
    assert resp.status_code == 400
    assert resp.json()["error_type"] == "validation_error"


def test_upload_rejects_path_traversal_filename(client: TestClient, sample_video_path: Path) -> None:
    """A malicious filename must be sanitised, never used to escape the
    upload directory (content still has to be a real video to pass)."""
    with sample_video_path.open("rb") as fh:
        resp = client.post(
            f"{API}/upload",
            files={"file": ("../../../etc/passwd.mp4", fh, "video/mp4")},
        )
    assert resp.status_code == 201
    stored_filename = resp.json()["filename"]
    assert ".." not in stored_filename
    assert "/" not in stored_filename


def test_list_videos_pagination_headers(client: TestClient, sample_video_path: Path) -> None:
    _upload(client, sample_video_path)
    resp = client.get(f"{API}/videos?limit=1&offset=0")
    assert resp.status_code == 200
    assert len(resp.json()) <= 1
    assert int(resp.headers["x-total-count"]) >= 1
    assert resp.headers["x-limit"] == "1"
    assert resp.headers["x-offset"] == "0"


def test_events_pagination_headers(client: TestClient, sample_video_path: Path) -> None:
    video = _upload(client, sample_video_path)
    resp = client.get(f"{API}/events/{video['id']}?limit=5&offset=0")
    assert resp.status_code == 200
    assert "x-total-count" in resp.headers


def test_global_stats_endpoint(client: TestClient, sample_video_path: Path) -> None:
    _upload(client, sample_video_path)
    resp = client.get(f"{API}/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_videos"] >= 1
    assert "free_disk_bytes" in data


def test_double_analyze_returns_409(client: TestClient, sample_video_path: Path) -> None:
    """The second of two immediate analyze calls for the same video must be
    rejected — regression test for the atomic try_mark_queued() fix (a plain
    read-then-write status check has a TOCTOU race that could double-enqueue)."""
    video = _upload(client, sample_video_path)
    video_id = video["id"]

    first = client.post(f"{API}/analyze/{video_id}", json={"enable_object_detection": False})
    assert first.status_code == 202
    second = client.post(f"{API}/analyze/{video_id}", json={"enable_object_detection": False})
    assert second.status_code == 409

    # Drain to completion so the background thread doesn't leak into other tests.
    for _ in range(120):
        if client.get(f"{API}/video/{video_id}").json()["status"] in ("completed", "failed"):
            break
        time.sleep(0.5)


def test_invalid_motion_algorithm_rejected(client: TestClient, sample_video_path: Path) -> None:
    video = _upload(client, sample_video_path)
    resp = client.post(
        f"{API}/analyze/{video['id']}", json={"motion_algorithm": "not_a_real_algorithm"}
    )
    assert resp.status_code == 400


def test_auto_algorithm_end_to_end(client: TestClient, sample_video_path: Path) -> None:
    video = _upload(client, sample_video_path)
    video_id = video["id"]
    resp = client.post(
        f"{API}/analyze/{video_id}",
        json={"motion_algorithm": "auto", "enable_object_detection": False},
    )
    assert resp.status_code == 202

    status = ""
    for _ in range(120):
        detail = client.get(f"{API}/video/{video_id}").json()
        status = detail["status"]
        if status in ("completed", "failed"):
            break
        time.sleep(0.5)
    assert status == "completed"
    # "auto" must have been resolved to one of the concrete algorithms.
    assert detail["motion_algorithm"] in ("mog2", "frame_diff", "optical_flow")
    # Processing stats must be populated and reflect the resolution.
    assert detail["processing_stats"] is not None
    assert detail["processing_stats"]["resolved_motion_algorithm"] == detail["motion_algorithm"]

    client.delete(f"{API}/video/{video_id}")


def test_cors_preflight_allows_authorization_header(client: TestClient) -> None:
    """Regression test: a browser's CORS preflight for a cross-origin,
    Bearer-authenticated request must succeed. This previously failed
    (silently, from the app's point of view — the request never even
    reached a route) because the CORS middleware's allow_headers list
    only had Content-Type/Accept, not Authorization."""
    resp = client.options(
        f"{API}/videos",
        headers={
            "Origin": "http://localhost:5173",  # default cors_origins entry
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert resp.status_code == 200
    allowed = resp.headers.get("access-control-allow-headers", "").lower()
    assert "authorization" in allowed


def test_database_file_not_reachable_via_storage_mount(client: TestClient) -> None:
    """Regression test for the critical security fix: the SQLite database
    must never be servable through the public /storage static mount, even via
    a path-traversal attempt against one of its subdirectories."""
    for path in (
        "/storage/app.db",
        "/storage/videos/../app.db",
        "/storage/videos/../../data/app.db",
        "/storage/clips/../../data/app.db",
    ):
        resp = client.get(path)
        assert resp.status_code in (404, 403), f"{path} returned {resp.status_code}"
