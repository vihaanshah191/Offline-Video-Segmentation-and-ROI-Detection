"""Tests for Demo Mode's one-click 'load the bundled sample and analyze' flow."""
from __future__ import annotations

import time

from app.core.config import settings
from fastapi.testclient import TestClient

API = "/api"


def test_load_demo_sample_queues_analysis_and_completes(client: TestClient) -> None:
    resp = client.post(f"{API}/demo/load-sample")
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["original_name"].startswith("[Demo]")
    assert body["status"] in ("queued", "processing")

    video_id = body["id"]
    status = ""
    for _ in range(120):
        detail = client.get(f"{API}/video/{video_id}").json()
        status = detail["status"]
        if status in ("completed", "failed"):
            break
        time.sleep(0.5)
    assert status == "completed", f"demo analysis did not complete: {status}"

    events = client.get(f"{API}/events/{video_id}").json()
    assert isinstance(events, list)


def test_load_demo_sample_disabled_returns_404(client: TestClient) -> None:
    original = settings.demo_mode_enabled
    settings.demo_mode_enabled = False
    try:
        resp = client.post(f"{API}/demo/load-sample")
        assert resp.status_code == 404
    finally:
        settings.demo_mode_enabled = original


def test_load_demo_sample_missing_file_returns_400(client: TestClient) -> None:
    original = settings.sample_video_path
    settings.sample_video_path = settings.sample_video_path.parent / "does-not-exist.mp4"
    try:
        resp = client.post(f"{API}/demo/load-sample")
        assert resp.status_code == 400
    finally:
        settings.sample_video_path = original
