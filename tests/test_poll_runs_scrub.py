"""poll_runs.error_message must never store protected-area geometry.

Provider failure strings (httpx 429/5xx text, exceptions) quote the failing
URL, and these providers put the region centre/radius in the URL path --
e.g. https://api.adsb.lol/v2/point/0.280901/-52.592973/200.0. The same bug
class was fixed for provider_call_log in 0.6.1 (_scrub_log_message); these
tests pin the same guarantee for poll_runs, plus the one-time backfill
script for the 695 pre-fix production rows.
"""

import asyncio
import importlib.util
import sqlite3
from pathlib import Path

from app.database import latest_poll, replace_query_regions
from app.main import _run_coverage_cycle_locked
from app.settings_store import set_setting

_RAW_LEAK = (
    "Client error '429 Too Many Requests' for url "
    "'https://api.adsb.lol/v2/point/0.280901/-52.592973/200.0'"
)


def _region() -> dict:
    return {
        "id": "r1",
        "name": "r1",
        "latitude": -1,
        "longitude": -55,
        "radius_nm": 10,
        "north": 0,
        "south": -2,
        "west": -56,
        "east": -54,
    }


def _setup_regions() -> None:
    set_setting("flight_providers", ["adsb_lol"])
    replace_query_regions([_region()])


def _assert_scrubbed(message: str | None) -> None:
    assert message is not None, "expected a non-empty error_message"
    assert "0.280901" not in message
    assert "-52.592973" not in message
    assert "api.adsb.lol" not in message
    assert "<url>" in message
    assert "429 Too Many Requests" in message, "human-readable part must survive"


def test_cycle_exception_message_never_stores_geometry(monkeypatch):
    _setup_regions()

    async def leaky_fetch_all():
        raise RuntimeError(_RAW_LEAK)

    monkeypatch.setattr("app.main.fetch_all", leaky_fetch_all)
    run = asyncio.run(_run_coverage_cycle_locked())
    _assert_scrubbed(run["error_message"])

    stored = latest_poll()
    assert stored is not None
    _assert_scrubbed(stored["error_message"])


def test_cycle_joined_provider_errors_never_store_geometry(monkeypatch):
    _setup_regions()

    async def leaky_fetch_all():
        return ([], set(), [f"adsb_lol r1: {_RAW_LEAK}"], 0)

    monkeypatch.setattr("app.main.fetch_all", leaky_fetch_all)
    run = asyncio.run(_run_coverage_cycle_locked())
    _assert_scrubbed(run["error_message"])

    stored = latest_poll()
    assert stored is not None
    _assert_scrubbed(stored["error_message"])


def test_cycle_no_errors_leaves_error_message_none(monkeypatch):
    _setup_regions()

    async def clean_fetch_all():
        return ([], {"r1"}, [], 1)

    monkeypatch.setattr("app.main.fetch_all", clean_fetch_all)
    run = asyncio.run(_run_coverage_cycle_locked())
    assert run["error_message"] is None
    assert latest_poll()["error_message"] is None


# ---------------------------------------------------------------------------
# Backfill script: scripts/scrub_poll_runs.py
# ---------------------------------------------------------------------------

def _load_script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "scrub_poll_runs.py"
    spec = importlib.util.spec_from_file_location("scrub_poll_runs", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_LEAKY_ROWS = [
    ("leaky-adsb", f"ProviderFailure: {_RAW_LEAK}"),
    (
        "leaky-airplanes",
        "ProviderFailure: Client error '429' for url "
        "'https://api.airplanes.live/v2/point/0.280901/-52.592973/200.0'",
    ),
    # Matches the LIKE filters but contains no URL -- must be left untouched.
    ("clean-no-url", "failed to reach http endpoint without scheme"),
    # No match at all -- not even scanned.
    ("clean-plain", "budget exhausted"),
]


def _seed(tmp_path: Path) -> Path:
    db_path = tmp_path / "poll_runs.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE poll_runs (id TEXT PRIMARY KEY, error_message TEXT)")
    conn.executemany(
        "INSERT INTO poll_runs (id, error_message) VALUES (?, ?)",
        _LEAKY_ROWS,
    )
    conn.commit()
    conn.close()
    return db_path


def _rows(db_path: Path) -> dict[str, str | None]:
    conn = sqlite3.connect(db_path)
    try:
        return {
            row[0]: row[1]
            for row in conn.execute("SELECT id, error_message FROM poll_runs")
        }
    finally:
        conn.close()


def test_backfill_script_dry_run_then_real_then_idempotent(tmp_path, monkeypatch):
    script = _load_script()
    db_path = _seed(tmp_path)
    monkeypatch.setenv("DATABASE_PATH", str(db_path))

    before = _rows(db_path)

    # Dry run: reports, writes nothing.
    assert script.main(["--dry-run"]) == 0
    assert _rows(db_path) == before

    # Real run: leaky rows scrubbed, clean rows byte-identical.
    assert script.main([]) == 0
    after = _rows(db_path)
    for row_id, _original in _LEAKY_ROWS:
        if row_id.startswith("leaky"):
            message = after[row_id]
            assert message is not None
            assert "0.280901" not in message
            assert "api." not in message
            assert "<url>" in message
            assert "ProviderFailure" in message, "readable part must survive"
        else:
            assert after[row_id] == before[row_id]

    # Second run: already-scrubbed text has no URLs, so nothing is rewritten.
    assert script.main([]) == 0
    assert _rows(db_path) == after
