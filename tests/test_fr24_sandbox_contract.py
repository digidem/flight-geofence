"""Live Flightradar24 sandbox contract tests.

These hit the real FR24 sandbox (static responses, zero credits) and verify
every client function in app/providers/fr24.py against the production schema:
auth headers accepted, response shape parsed, request-log rows written, and
the sandbox key never leaking into logs or exceptions.

Opt-in by design: skipped unless FR24_SANDBOX_API_KEY is set, so the default
suite (and CI) is untouched. Run via scripts/fr24_sandbox_smoke.sh or:

    FR24_SANDBOX_API_KEY=<key> pytest -m fr24_sandbox

Sandbox caveats (see FLIGHTRADAR_API.md "Sandbox testing"): query params are
ignored, every call returns the same static payload, and the documented
fixture (flight SK7679, hex 4CAD41, timestamp 2024-10-10T08:08:12Z) may drift
-- assertions are schema-level, never exact-value.
"""

import asyncio
import os
from datetime import UTC, datetime

import httpx
import pytest

from app.config import env_settings
from app.database import db
from app.fr24_credits import billing_cycle_id
from app.providers.fr24 import (
    FR24Failure,
    fetch_count,
    fetch_light,
    fetch_summary_full,
    fetch_track,
    fetch_usage,
)

pytestmark = [
    pytest.mark.fr24_sandbox,
    pytest.mark.skipif(
        not os.environ.get("FR24_SANDBOX_API_KEY"),
        reason="FR24_SANDBOX_API_KEY not set (opt-in live sandbox tests)",
    ),
]

# Documented sandbox fixture (docs/sandbox-environment). Used only as a
# soft expectation -- FR24 may rotate the static payload without notice.
DOCS_HEX = "4cad41"
DOCS_FR24_ID = "333ca4a2"
DOCS_LAT = 35.34722
DOCS_LON = -7.90277

BOUNDS = {"north": 36.0, "south": 35.0, "west": -9.0, "east": -7.0}


@pytest.fixture
def sandbox_env(monkeypatch):
    """Wire the sandbox key through the normal env->setting path.

    FLIGHTRADAR24_API_KEY is deliberately never read from the ambient
    environment here -- only FR24_SANDBOX_API_KEY -- so a shell-exported
    production key can never silently ride along.
    """
    key = os.environ["FR24_SANDBOX_API_KEY"]
    monkeypatch.setenv("FLIGHTRADAR24_API_KEY", key)
    # Accept the sandbox's 2024-dated static timestamps through the same
    # freshness gate production uses (default 150s).
    monkeypatch.setenv("POSITION_MAX_AGE_SECONDS", "70000000")
    env_settings.cache_clear()
    yield key
    env_settings.cache_clear()


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=40, follow_redirects=True)


def _bcid() -> str:
    return billing_cycle_id(datetime.now(UTC))


def _request_rows(endpoint: str) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM fr24_request_log WHERE endpoint=? ORDER BY requested_at DESC",
            (endpoint,),
        ).fetchall()
    return [dict(r) for r in rows]


def test_sandbox_light_contract(sandbox_env):
    result = asyncio.run(
        fetch_light(
            _client(),
            north=BOUNDS["north"],
            south=BOUNDS["south"],
            west=BOUNDS["west"],
            east=BOUNDS["east"],
            categories=["T", "H", "N"],
            min_altitude_ft=-2000,
            max_altitude_ft=10000,
            limit=20,
            cluster_id="sandbox-contract",
            billing_cycle_id=_bcid(),
        )
    )
    assert result.raw_count >= 1, "sandbox light response should contain the static row"
    row = _request_rows("live/flight-positions/light")[0]
    assert row["http_outcome"] == "ok"
    assert row["records_returned"] >= 1
    assert row["retry_count"] == 0


def test_sandbox_light_normalizes_with_raised_max_age(sandbox_env):
    """The full normalize path must accept the real sandbox payload once the
    freshness window is widened -- this is exactly what the sandbox compose
    stack does via POSITION_MAX_AGE_SECONDS."""
    result = asyncio.run(
        fetch_light(
            _client(),
            north=BOUNDS["north"],
            south=BOUNDS["south"],
            west=BOUNDS["west"],
            east=BOUNDS["east"],
            categories=["T", "H", "N"],
            min_altitude_ft=-2000,
            max_altitude_ft=10000,
            limit=20,
            cluster_id="sandbox-contract",
            billing_cycle_id=_bcid(),
        )
    )
    assert result.observations, "raised POSITION_MAX_AGE should keep the static observation"
    obs = result.observations[0]
    assert obs.provider == "flightradar24"
    assert -90 <= obs.latitude <= 90
    assert -180 <= obs.longitude <= 180
    assert obs.callsign  # static row always carries a callsign


def test_sandbox_count_contract(sandbox_env):
    count = asyncio.run(
        fetch_count(
            _client(),
            north=BOUNDS["north"],
            south=BOUNDS["south"],
            west=BOUNDS["west"],
            east=BOUNDS["east"],
            categories=["T", "H", "N"],
            min_altitude_ft=-2000,
            max_altitude_ft=10000,
            cluster_id="sandbox-contract",
            billing_cycle_id=_bcid(),
        )
    )
    assert isinstance(count, int)
    assert count >= 0


def test_sandbox_summary_contract(sandbox_env):
    rows = asyncio.run(fetch_summary_full(_client(), [DOCS_FR24_ID], billing_cycle_id=_bcid()))
    assert isinstance(rows, list)
    row = _request_rows("flight-summary/full")[0]
    assert row["http_outcome"] == "ok"


def test_sandbox_track_contract(sandbox_env):
    track = asyncio.run(fetch_track(_client(), DOCS_FR24_ID, billing_cycle_id=_bcid()))
    # Real schema: top-level array of {fr24_id, tracks} flight objects.
    assert isinstance(track, list)
    row = _request_rows("flight-tracks")[0]
    assert row["http_outcome"] == "ok"
    assert row["records_returned"] >= 1


def test_sandbox_usage_contract(sandbox_env):
    usage = asyncio.run(fetch_usage(_client(), "24h"))
    assert isinstance(usage, dict)
    # /api/usage is deliberately not written to fr24_request_log (its own
    # credit cost is undocumented) -- nothing to assert there.


def test_sandbox_rejects_bad_key_without_leaking_it(monkeypatch, caplog):
    """An invalid key must surface as FR24Failure (401 is a no-retry status)
    with neither the key nor the full query string in the message or logs."""
    bad_key = "sandbox-invalid-key-do-not-use"
    monkeypatch.setenv("FLIGHTRADAR24_API_KEY", bad_key)
    env_settings.cache_clear()
    with caplog.at_level("ERROR"), pytest.raises(FR24Failure) as excinfo:
        asyncio.run(
            fetch_light(
                _client(),
                north=BOUNDS["north"],
                south=BOUNDS["south"],
                west=BOUNDS["west"],
                east=BOUNDS["east"],
                categories=["T"],
                min_altitude_ft=-2000,
                max_altitude_ft=10000,
                limit=5,
                cluster_id="sandbox-contract",
                billing_cycle_id=_bcid(),
            )
        )
    assert bad_key not in str(excinfo.value)
    assert bad_key not in caplog.text
    failed = _request_rows("live/flight-positions/light")[0]
    assert failed["http_outcome"] == "failed"
    # Rebuild lazily after monkeypatch restores the environment, so the
    # bad-key settings never leak into later tests through the lru_cache.
    env_settings.cache_clear()
