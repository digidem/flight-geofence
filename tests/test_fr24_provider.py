import asyncio
import json
from datetime import UTC, datetime

import httpx
import pytest

from app.config import env_settings
from app.database import db
from app.providers.base import AircraftObservation
from app.providers.fr24 import (
    FR24Failure,
    fetch_count,
    fetch_light,
    fetch_summary_full,
    fetch_track,
    fetch_usage,
    normalize_light_observation,
    parse_fr24_timestamp,
)
from app.providers.providers import ProviderFailure, fetch_provider_region
from app.settings_store import set_setting


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _recent_timestamp():
    return int(datetime.now(UTC).timestamp())


def _valid_raw(**overrides):
    base = {
        "hex": "ABC123",
        "lat": -1.5,
        "lon": -55.5,
        "alt": 3000,
        "callsign": "  test123  ",
        "fr24_id": "fr24-abc",
        "timestamp": _recent_timestamp(),
    }
    base.update(overrides)
    return base


def _setup_key():
    set_setting("flightradar24_api_key", "test-token")


LIGHT_KWARGS = dict(
    north=-1,
    south=-3,
    west=-56,
    east=-54,
    categories=["T", "H", "N"],
    min_altitude_ft=-2000,
    max_altitude_ft=10000,
    limit=20,
    cluster_id="cluster-1",
    billing_cycle_id="2026-07",
)

COUNT_KWARGS = dict(
    north=-1,
    south=-3,
    west=-56,
    east=-54,
    categories=["T", "H", "N"],
    min_altitude_ft=-2000,
    max_altitude_ft=10000,
    cluster_id="cluster-1",
    billing_cycle_id="2026-07",
)


def _json_response(data, status=200):
    return httpx.Response(
        status,
        content=json.dumps(data).encode(),
        headers={"content-type": "application/json"},
    )


def _fr24_log_rows(endpoint=None, outcome=None):
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM fr24_request_log ORDER BY requested_at"
        ).fetchall()
    result = [dict(r) for r in rows]
    if endpoint:
        result = [r for r in result if r["endpoint"] == endpoint]
    if outcome:
        result = [r for r in result if r["http_outcome"] == outcome]
    return result


# --- parse_fr24_timestamp ---


def test_parse_fr24_timestamp_numeric_seconds():
    result = parse_fr24_timestamp(1_700_000_000)
    assert result is not None
    assert result.year == 2023


def test_parse_fr24_timestamp_numeric_milliseconds():
    seconds = parse_fr24_timestamp(1_700_000_000)
    milliseconds = parse_fr24_timestamp(1_700_000_000_000)
    assert seconds == milliseconds


def test_parse_fr24_timestamp_iso_z_suffix():
    result = parse_fr24_timestamp("2023-11-14T22:13:20Z")
    assert result is not None
    assert result.year == 2023
    assert result.tzinfo is not None


def test_parse_fr24_timestamp_none_returns_none():
    assert parse_fr24_timestamp(None) is None


def test_parse_fr24_timestamp_empty_string_returns_none():
    assert parse_fr24_timestamp("") is None


def test_parse_fr24_timestamp_invalid_string_returns_none():
    assert parse_fr24_timestamp("not-a-date") is None


# --- normalize_light_observation ---


def test_normalize_light_valid_record():
    obs = normalize_light_observation(_valid_raw(), "cluster-1")
    assert obs is not None
    assert isinstance(obs, AircraftObservation)
    assert obs.provider == "flightradar24"
    assert obs.hex == "abc123"
    assert obs.callsign == "TEST123"
    assert obs.fr24_id == "fr24-abc"


def test_normalize_light_missing_hex_returns_none():
    assert normalize_light_observation(_valid_raw(hex=""), "cluster-1") is None


def test_normalize_light_missing_callsign_still_valid():
    obs = normalize_light_observation(_valid_raw(callsign=""), "cluster-1")
    assert obs is not None
    assert obs.callsign is None


def test_normalize_light_invalid_coordinates_returns_none():
    assert normalize_light_observation(_valid_raw(lat=200), "cluster-1") is None


def test_normalize_light_nan_coordinates_returns_none():
    assert normalize_light_observation(_valid_raw(lat=float("nan")), "cluster-1") is None


def test_normalize_light_stale_timestamp_returns_none():
    cfg = env_settings()
    stale_ts = int(datetime.now(UTC).timestamp()) - cfg.position_max_age_seconds - 100
    assert normalize_light_observation(_valid_raw(timestamp=stale_ts), "cluster-1") is None


def test_normalize_light_future_timestamp_returns_none():
    future_ts = int(datetime.now(UTC).timestamp()) + 120
    assert normalize_light_observation(_valid_raw(timestamp=future_ts), "cluster-1") is None


# --- fetch_light ---


def test_fetch_light_empty_response():
    _setup_key()

    def handler(request):
        return _json_response({"data": []})

    result = asyncio.run(fetch_light(_client(handler), **LIGHT_KWARGS))
    assert result.possibly_truncated is False
    assert result.observations == []
    assert result.estimated_credits == 1


def test_fetch_light_one_aircraft():
    _setup_key()

    def handler(request):
        return _json_response({"data": [_valid_raw()]})

    result = asyncio.run(fetch_light(_client(handler), **LIGHT_KWARGS))
    assert len(result.observations) == 1
    assert result.estimated_credits == 6


def test_fetch_light_helicopter_record():
    _setup_key()

    def handler(request):
        return _json_response({"data": [_valid_raw(category="H")]})

    result = asyncio.run(fetch_light(_client(handler), **LIGHT_KWARGS))
    assert len(result.observations) == 1


def test_fetch_light_invalid_hex_dropped():
    _setup_key()

    def handler(request):
        return _json_response({"data": [_valid_raw(), _valid_raw(hex="")]})

    result = asyncio.run(fetch_light(_client(handler), **LIGHT_KWARGS))
    assert len(result.observations) == 1


def test_fetch_light_exactly_limit_truncated():
    _setup_key()
    items = [_valid_raw(hex=f"abc{i:03d}") for i in range(20)]

    def handler(request):
        return _json_response({"data": items})

    result = asyncio.run(fetch_light(_client(handler), **LIGHT_KWARGS))
    assert result.possibly_truncated is True


def test_fetch_light_fewer_than_limit_not_truncated():
    _setup_key()
    items = [_valid_raw(hex=f"abc{i:03d}") for i in range(5)]

    def handler(request):
        return _json_response({"data": items})

    result = asyncio.run(fetch_light(_client(handler), **LIGHT_KWARGS))
    assert result.possibly_truncated is False


def test_fetch_light_malformed_json_raises():
    _setup_key()

    def handler(request):
        return httpx.Response(
            200, content=b"not json", headers={"content-type": "application/json"}
        )

    with pytest.raises(FR24Failure):
        asyncio.run(fetch_light(_client(handler), **LIGHT_KWARGS))


def test_fetch_light_401_no_retry():
    _setup_key()
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(401, content=b"Unauthorized")

    with pytest.raises(FR24Failure):
        asyncio.run(fetch_light(_client(handler), **LIGHT_KWARGS))
    assert len(calls) == 1


def test_fetch_light_402_no_retry():
    _setup_key()
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(402, content=b"Payment Required")

    with pytest.raises(FR24Failure):
        asyncio.run(fetch_light(_client(handler), **LIGHT_KWARGS))
    assert len(calls) == 1


def test_fetch_light_429_retries():
    _setup_key()
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(
            429,
            content=b"rate limited",
            headers={"Retry-After": "0"},
        )

    with pytest.raises(FR24Failure):
        asyncio.run(fetch_light(_client(handler), **LIGHT_KWARGS))
    assert len(calls) > 1
    assert len(calls) <= 3


def test_fetch_light_500_retries():
    _setup_key()
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(500, content=b"Internal Server Error")

    with pytest.raises(FR24Failure):
        asyncio.run(fetch_light(_client(handler), **LIGHT_KWARGS))
    assert len(calls) > 1
    assert len(calls) <= 3


def test_fetch_light_timeout_raises():
    _setup_key()

    def handler(request):
        raise httpx.TimeoutException("timeout")

    with pytest.raises(FR24Failure):
        asyncio.run(fetch_light(_client(handler), **LIGHT_KWARGS))


def test_fetch_light_404_no_retry():
    _setup_key()
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(404, content=b"Not Found")

    with pytest.raises(FR24Failure):
        asyncio.run(fetch_light(_client(handler), **LIGHT_KWARGS))
    assert len(calls) == 1


def test_fetch_light_missing_data_key_raises_schema_mismatch():
    # A 2xx response with a missing/renamed 'data' key must never be treated
    # the same as a genuinely empty poll -- that would be exactly the
    # "provider failure counted as aircraft disappearance" case the
    # detection invariants forbid.
    _setup_key()

    def handler(request):
        return _json_response({"unexpected": "schema"})

    with pytest.raises(FR24Failure):
        asyncio.run(fetch_light(_client(handler), **LIGHT_KWARGS))
    rows = _fr24_log_rows(outcome="failed")
    assert len(rows) == 1


def test_fetch_light_non_dict_record_element_silently_dropped():
    # A malformed (non-dict) element inside 'data' must not crash the whole
    # poll -- it's filtered like any other invalid record (missing hex,
    # bad coordinates), while valid records in the same response still count.
    _setup_key()

    def handler(request):
        return _json_response({"data": [_valid_raw(), "not-a-dict"]})

    result = asyncio.run(fetch_light(_client(handler), **LIGHT_KWARGS))
    assert len(result.observations) == 1
    assert result.raw_count == 2


def test_retry_delay_applies_jitter():
    from app.providers.fr24 import _retry_delay

    delays = {_retry_delay(None, 0) for _ in range(20)}
    assert len(delays) > 1, "expected randomized jitter, got deterministic values"
    assert all(0.4 <= d <= 1.1 for d in delays)


def test_retry_does_not_reuse_stale_retry_after_across_attempts(monkeypatch):
    # Attempt 0 gets a 429 with a real Retry-After; attempt 1 then fails with
    # a transport error (no HTTP response at all). The delay before attempt 2
    # must not reuse attempt 0's stale Retry-After header.
    _setup_key()
    delays = []

    async def fake_sleep(seconds):
        delays.append(seconds)

    monkeypatch.setattr("app.providers.fr24.asyncio.sleep", fake_sleep)
    call_count = [0]

    def handler(request):
        call_count[0] += 1
        if call_count[0] == 1:
            return httpx.Response(429, headers={"Retry-After": "100"})
        raise httpx.TimeoutException("timeout")

    with pytest.raises(FR24Failure):
        asyncio.run(fetch_light(_client(handler), **LIGHT_KWARGS))
    assert len(delays) == 2
    assert delays[0] == 30  # 429's explicit Retry-After, capped at 30
    assert delays[1] < 10  # must fall back to jittered backoff, not reuse 30/100


def test_fetch_light_failure_logged():
    _setup_key()

    def handler(request):
        return httpx.Response(401, content=b"Unauthorized")

    with pytest.raises(FR24Failure):
        asyncio.run(fetch_light(_client(handler), **LIGHT_KWARGS))
    rows = _fr24_log_rows(outcome="failed")
    assert len(rows) == 1


def test_fetch_light_success_logged():
    _setup_key()

    def handler(request):
        return _json_response({"data": [_valid_raw()]})

    asyncio.run(fetch_light(_client(handler), **LIGHT_KWARGS))
    rows = _fr24_log_rows(outcome="ok")
    assert len(rows) == 1
    assert rows[0]["estimated_credits"] == 6


# --- fetch_count ---


def test_fetch_count_returns_count():
    _setup_key()

    def handler(request):
        # Real schema (live sandbox): {"data": [{"record_count": 123}]}
        return _json_response({"data": [{"record_count": 5}]})

    result = asyncio.run(fetch_count(_client(handler), **COUNT_KWARGS))
    assert result == 5
    rows = _fr24_log_rows(outcome="ok")
    assert len(rows) == 1
    assert rows[0]["estimated_credits"] == 0


def test_fetch_count_missing_count_key_raises_schema_mismatch():
    _setup_key()

    def handler(request):
        return _json_response({"unexpected": "schema"})

    with pytest.raises(FR24Failure):
        asyncio.run(fetch_count(_client(handler), **COUNT_KWARGS))
    rows = _fr24_log_rows(outcome="failed")
    assert len(rows) == 1


def test_fetch_count_boolean_count_raises_schema_mismatch():
    # bool is a subclass of int in Python -- must not be accepted as a count.
    _setup_key()

    def handler(request):
        return _json_response({"data": [{"record_count": True}]})

    with pytest.raises(FR24Failure):
        asyncio.run(fetch_count(_client(handler), **COUNT_KWARGS))


# --- fetch_summary_full ---


def test_fetch_summary_full_batches():
    _setup_key()
    calls = []
    fr24_ids = [f"fr24-{i}" for i in range(12)]

    def handler(request):
        calls.append(1)
        ids_param = request.url.params.get("flight_ids", "")
        ids_list = ids_param.split(",")
        return _json_response({"data": [{"id": fid} for fid in ids_list]})

    result = asyncio.run(
        fetch_summary_full(_client(handler), fr24_ids, billing_cycle_id="2026-07")
    )
    assert len(calls) == 2
    assert len(result) == 12
    rows = _fr24_log_rows(endpoint="flight-summary/full")
    assert len(rows) == 2


def test_fetch_summary_full_missing_data_key_raises_schema_mismatch():
    _setup_key()

    def handler(request):
        return _json_response({"unexpected": "schema"})

    with pytest.raises(FR24Failure):
        asyncio.run(fetch_summary_full(_client(handler), ["fr24-1"], billing_cycle_id="2026-07"))


# --- fetch_track ---


def test_fetch_track_returns_payload():
    _setup_key()

    def handler(request):
        # Real schema (live sandbox): top-level array of {fr24_id, tracks}.
        return _json_response([{"fr24_id": "fr24-abc", "tracks": [{"lat": -1.0, "lon": -55.0}]}])

    result = asyncio.run(
        fetch_track(_client(handler), "fr24-abc", billing_cycle_id="2026-07")
    )
    assert isinstance(result, list)
    assert result[0]["tracks"]
    rows = _fr24_log_rows(outcome="ok")
    assert len(rows) == 1
    assert rows[0]["estimated_credits"] == 40


def test_fetch_track_non_list_raises_schema_mismatch():
    _setup_key()

    def handler(request):
        return _json_response({"unexpected": "schema"})

    with pytest.raises(FR24Failure):
        asyncio.run(fetch_track(_client(handler), "fr24-abc", billing_cycle_id="2026-07"))


# --- fetch_usage ---


def test_fetch_usage_valid_period():
    _setup_key()

    def handler(request):
        return _json_response({"period": "24h", "total": 100})

    result = asyncio.run(fetch_usage(_client(handler), "24h"))
    assert result["period"] == "24h"


def test_fetch_usage_invalid_period_no_http_call():
    _setup_key()

    def handler(request):
        raise AssertionError("HTTP should not be called for invalid period")

    with pytest.raises(ValueError):
        asyncio.run(fetch_usage(_client(handler), "90d"))


# --- fetch_provider_region ---


def test_fetch_provider_region_flightradar24_raises():
    with pytest.raises(ProviderFailure):
        asyncio.run(fetch_provider_region("flightradar24", {"id": "r1"}))


# --- fetch_all: flightradar24 must not disable free-provider disappearance detection ---


def test_fetch_all_flightradar24_configured_does_not_block_free_provider_success(monkeypatch):
    # Regression: flightradar24 previously raised INSIDE fetch_all's
    # per-region loop, which meant no region could ever satisfy
    # "all enabled providers succeeded" once flightradar24 was configured --
    # silently disabling disappearance detection for every provider,
    # including the still-working free ones.
    import app.providers.providers as providers_mod
    from app.database import replace_query_regions

    set_setting("flight_providers", ["adsb_lol", "flightradar24"])
    replace_query_regions(
        [
            {
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
        ]
    )

    async def fake_readsb_region(client, provider, region):
        return []

    monkeypatch.setattr(providers_mod, "_readsb_region", fake_readsb_region)
    _observations, fully_successful_regions, _errors, requests_successful = asyncio.run(
        providers_mod.fetch_all()
    )
    assert "r1" in fully_successful_regions
    assert requests_successful == 1
