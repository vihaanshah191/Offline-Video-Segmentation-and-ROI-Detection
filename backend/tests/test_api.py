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
