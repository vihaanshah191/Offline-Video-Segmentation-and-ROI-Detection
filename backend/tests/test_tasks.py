"""Tests for the background task runner's concurrency cap.

Batch-uploading N videos (VideoUpload's multi-file support) and analyzing
all of them must not spawn N unbounded concurrent analysis threads —
settings.max_concurrent_analyses caps how many actually run at once via a
module-level semaphore in app.workers.tasks.
"""
from __future__ import annotations

import threading
import time

from app.workers import tasks


def test_run_analysis_respects_concurrency_cap(monkeypatch) -> None:
    monkeypatch.setattr(tasks, "_analysis_semaphore", threading.Semaphore(1))

    active = 0
    max_active = 0
    lock = threading.Lock()

    def fake_locked(video_id: int, config: object) -> None:
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.2)
        with lock:
            active -= 1

    monkeypatch.setattr(tasks, "_run_analysis_locked", fake_locked)

    threads = [threading.Thread(target=tasks.run_analysis, args=(i, None)) for i in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert max_active == 1, "concurrency cap of 1 was violated"


def test_run_analysis_allows_up_to_the_configured_cap(monkeypatch) -> None:
    monkeypatch.setattr(tasks, "_analysis_semaphore", threading.Semaphore(2))

    active = 0
    max_active = 0
    lock = threading.Lock()

    def fake_locked(video_id: int, config: object) -> None:
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.2)
        with lock:
            active -= 1

    monkeypatch.setattr(tasks, "_run_analysis_locked", fake_locked)

    threads = [threading.Thread(target=tasks.run_analysis, args=(i, None)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert max_active == 2, f"expected exactly 2 concurrent slots to be used, got {max_active}"
