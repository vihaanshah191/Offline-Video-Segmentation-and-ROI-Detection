"""Pytest fixtures.

A throwaway temp directory is wired up as the storage root and SQLite database
*before* the application modules are imported, so the whole test run is fully
isolated from any real data. Object detection is disabled by default (no model
weights required in CI).
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

# ---- Configure an isolated environment BEFORE importing the app -----------
_TMP = Path(tempfile.mkdtemp(prefix="video-analytics-test-"))
for name in ("storage", "videos", "clips", "heatmaps", "thumbnails", "reports"):
    (_TMP / name).mkdir(parents=True, exist_ok=True)

os.environ.update(
    {
        "DATABASE_URL": f"sqlite:///{_TMP / 'test.db'}",
        "STORAGE_DIR": str(_TMP / "storage"),
        "VIDEOS_DIR": str(_TMP / "videos"),
        "CLIPS_DIR": str(_TMP / "clips"),
        "HEATMAPS_DIR": str(_TMP / "heatmaps"),
        "THUMBNAILS_DIR": str(_TMP / "thumbnails"),
        "REPORTS_DIR": str(_TMP / "reports"),
        "ENABLE_OBJECT_DETECTION": "false",
        "FRAME_SAMPLE_STEP": "1",
    }
)

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database.session import SessionLocal, engine, init_db  # noqa: E402
from app.database.base import Base  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _init_database() -> None:
    """Create all tables once for the test session."""
    init_db()
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session():
    """Provide a database session, rolling back nothing (real commits used)."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client() -> TestClient:
    """FastAPI test client."""
    return TestClient(app)


@pytest.fixture(scope="session")
def sample_video_path() -> Path:
    """Render a small synthetic video with distinct motion windows."""
    path = _TMP / "sample.mp4"
    fps, seconds, w, h = 15, 12, 320, 240
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    background = np.full((h, w, 3), 30, dtype=np.uint8)
    windows = [(2, 4), (7, 10)]
    for i in range(seconds * fps):
        t = i / fps
        frame = background.copy()
        frame = cv2.add(frame, np.random.randint(0, 5, frame.shape, dtype=np.uint8))
        if any(a <= t <= b for a, b in windows):
            cx = int(w * 0.5 + np.sin(t * 3) * w * 0.3)
            cv2.rectangle(frame, (cx - 25, 90), (cx + 25, 170), (0, 150, 255), -1)
        writer.write(frame)
    writer.release()
    return path
