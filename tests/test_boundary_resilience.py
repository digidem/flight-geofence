"""Boundary-sync failure backoff and orphaned tmp cleanup."""

import os
import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest


def _sync_run(minutes_ago: int, success: int) -> dict:
    started = datetime(2026, 8, 30, 12, 0, tzinfo=UTC) - timedelta(
        minutes=minutes_ago
    )
    return {
        "id": str(uuid.uuid4()),
        "started_at": started.isoformat(),
        "completed_at": started.isoformat(),
        "success": success,
    }


def test_consecutive_sync_failures_counts_then_resets():
    from app.database import consecutive_sync_failures, save_sync_run

    # No syncs at all.
    assert consecutive_sync_failures() == 0

    # Two most-recent runs failed.
    save_sync_run(_sync_run(30, success=0))
    save_sync_run(_sync_run(20, success=0))
    assert consecutive_sync_failures() == 2

    # A newer success resets the count.
    save_sync_run(_sync_run(10, success=1))
    assert consecutive_sync_failures() == 0


@pytest.mark.parametrize(
    ("failures", "expected_hours"),
    [(0, 0), (1, 1), (2, 6), (3, 24), (9, 24)],
)
def test_sync_backoff_schedule(monkeypatch, failures, expected_hours):
    import app.main as main_module

    monkeypatch.setattr(
        main_module, "consecutive_sync_failures", lambda: failures
    )
    assert main_module._sync_backoff_hours() == expected_hours


def test_sync_due_respects_backoff(monkeypatch):
    import app.main as main_module

    now = datetime.now(UTC)

    def set_latest(started, success=0, completed=None):
        monkeypatch.setattr(
            main_module,
            "latest_sync",
            lambda: {
                "success": success,
                "completed_at": completed,
                "started_at": started,
            },
        )

    # Two failures, backoff window (2 -> 6h) still open.
    monkeypatch.setattr(main_module, "consecutive_sync_failures", lambda: 2)
    set_latest((now - timedelta(minutes=30)).isoformat())
    assert main_module._sync_due() is False

    # Same failures, 6h backoff window elapsed.
    set_latest((now - timedelta(hours=7)).isoformat())
    assert main_module._sync_due() is True

    # No failures: interval logic applies as before.
    monkeypatch.setattr(main_module, "consecutive_sync_failures", lambda: 0)
    set_latest(
        (now - timedelta(days=2000)).isoformat(),
        success=1,
        completed=(now - timedelta(days=2000)).isoformat(),
    )
    assert main_module._sync_due() is True


def test_cleanup_orphaned_tmp(tmp_path, monkeypatch):
    from app.boundary_sync import cleanup_orphaned_tmp
    from app.config import env_settings

    monkeypatch.setenv("DOWNLOAD_DIR", str(tmp_path))
    env_settings.cache_clear()

    old_dir = tmp_path / "tmpAAA"
    old_dir.mkdir()
    fresh_dir = tmp_path / "tmpBBB"
    fresh_dir.mkdir()
    other_dir = tmp_path / "otherCCC"
    other_dir.mkdir()
    old_time = time.time() - 2 * 24 * 3600
    os.utime(old_dir, (old_time, old_time))

    assert cleanup_orphaned_tmp() == 1
    assert not old_dir.exists()
    assert fresh_dir.exists()
    assert other_dir.exists()

    # Missing (non-dir) download_dir is a no-op.
    monkeypatch.setenv("DOWNLOAD_DIR", str(tmp_path / "missing"))
    env_settings.cache_clear()
    assert cleanup_orphaned_tmp() == 0
