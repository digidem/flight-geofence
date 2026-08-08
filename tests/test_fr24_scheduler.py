import asyncio
import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from shapely.geometry import Polygon, mapping

import app.fr24_scheduler as fr24_scheduler_mod
from app.database import (
    get_fr24_enrichment,
    get_state,
    record_fr24_request,
    replace_areas,
    save_fr24_cluster,
    upsert_state,
)
from app.fr24_credits import billing_cycle_id
from app.fr24_scheduler import fr24_lock, run_fr24_cycle
from app.settings_store import set_setting


@pytest.fixture(autouse=True)
def _reset_fr24_scheduler_module_state():
    # fr24_scheduler.py has two in-memory, process-wide throttle globals
    # (_last_usage_sync, _last_count_calibration) that would otherwise leak
    # state between tests -- e.g. a usage-sync test setting a recent
    # timestamp would make a LATER test's "not synced in 24h" check pass
    # trivially, silently making that test vacuous regardless of the
    # setting/logic it's actually meant to exercise.
    fr24_scheduler_mod._last_usage_sync = None
    fr24_scheduler_mod._last_count_calibration = {}
    yield


def _selected_area_record(area_id="funai:test", name="Test Area"):
    geometry = Polygon(
        [(-55.1, -1.1), (-54.9, -1.1), (-54.9, -0.9), (-55.1, -0.9), (-55.1, -1.1)]
    )
    return {
        "id": area_id,
        "source": "FUNAI",
        "external_id": area_id.split(":")[-1],
        "name": name,
        "category": "indigenous_territory",
        "state": "PA",
        "phase": "Regularizada",
        "geometry_json": json.dumps(mapping(geometry)),
        "min_lon": -55.1,
        "min_lat": -1.1,
        "max_lon": -54.9,
        "max_lat": -0.9,
        "source_date": "2026-07-23",
    }


def _enabled_cluster(cluster_id="cluster-1", **overrides):
    base = {
        "id": cluster_id,
        "name": "Test Cluster",
        "enabled": 1,
        "buffer_km": 10.0,
        "min_altitude_ft": -2000.0,
        "max_altitude_ft": 10000.0,
        "categories_json": '["T", "H", "N"]',
        "calc_north": -1.0,
        "calc_south": -3.0,
        "calc_west": -56.0,
        "calc_east": -54.0,
        "use_manual_bounds": 0,
    }
    base.update(overrides)
    return base


def _enable_fr24():
    set_setting("fr24_enabled", True)
    set_setting("flightradar24_api_key", "test-token")
    set_setting("fr24_poll_interval_seconds", 300)
    set_setting("fr24_inter_cluster_delay_seconds", 0)


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


def _json_response(data, status=200):
    return httpx.Response(
        status,
        content=json.dumps(data).encode(),
        headers={"content-type": "application/json"},
    )


@pytest.fixture
def mock_fr24_transport(monkeypatch):
    handlers = {}

    def set_handler(fn):
        handlers["fn"] = fn

    real_async_client = httpx.AsyncClient

    def fake_async_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handlers["fn"])
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr("app.fr24_scheduler.httpx.AsyncClient", fake_async_client)
    return set_handler


# --- Two-cluster success ---


def test_two_cluster_success(mock_fr24_transport):
    _enable_fr24()
    save_fr24_cluster(_enabled_cluster("c1"))
    save_fr24_cluster(_enabled_cluster("c2", calc_west=-53, calc_east=-51))

    def handler(request):
        return _json_response({"data": []})

    mock_fr24_transport(handler)
    result = asyncio.run(run_fr24_cycle())
    assert result["success"] == 1
    assert result["skipped"] == 0
    assert result["clusters_successful"] == 2


# --- Lock prevents overlapping cycles ---


def test_run_fr24_cycle_skips_when_locked():
    async def scenario():
        async with fr24_lock:
            return await run_fr24_cycle()

    result = asyncio.run(scenario())
    assert result["status"] == "skipped"


# --- Cluster A succeeds, cluster B fails ---


def test_cluster_a_succeeds_cluster_b_fails(mock_fr24_transport):
    _enable_fr24()
    save_fr24_cluster(_enabled_cluster("c1"))
    save_fr24_cluster(_enabled_cluster("c2", calc_west=-53, calc_east=-51))

    def handler(request):
        bounds = request.url.params.get("bounds", "")
        if "-53" in bounds or "-51" in bounds:
            return httpx.Response(500, content=b"Internal Server Error")
        return _json_response({"data": []})

    mock_fr24_transport(handler)
    result = asyncio.run(run_fr24_cycle())
    assert result["clusters_successful"] == 1
    assert "c2" in result["error_message"]


# --- Both clusters empty ---


def test_both_clusters_empty(mock_fr24_transport):
    _enable_fr24()
    save_fr24_cluster(_enabled_cluster("c1"))
    save_fr24_cluster(_enabled_cluster("c2", calc_west=-53, calc_east=-51))

    def handler(request):
        return _json_response({"data": []})

    mock_fr24_transport(handler)
    result = asyncio.run(run_fr24_cycle())
    assert result["events_created"] == 0
    assert result["success"] == 1


# --- Duplicate aircraft in overlapping clusters merged ---


def test_duplicate_aircraft_merged(mock_fr24_transport):
    # fetch_light never sends a cluster identifier over HTTP (by design --
    # it's an internal correlation id, not part of the FR24 API contract),
    # so the two clusters' requests can't be told apart by request content.
    # Clusters are polled sequentially in a fixed order (c1 then c2, per
    # list_fr24_clusters()'s created_at ordering and c1 being saved first),
    # so call order distinguishes them instead: first call returns an older
    # observation, second returns a newer one for the SAME aircraft,
    # simulating it appearing in both clusters' overlapping rectangles.
    _enable_fr24()
    # Isolated to merge behavior -- candidate enrichment has its own
    # dedicated tests below and would add a third (Summary Full) call here,
    # since this aircraft has an fr24_id and lands inside the selected area.
    set_setting("fr24_fetch_summary_on_entry", False)
    # Usage sync defaults to enabled and would add a third (Usage) call on
    # this, its first cycle in the test (fresh module state per-test via
    # the autouse reset fixture) -- disable it here since it isn't what
    # this test is exercising.
    set_setting("fr24_usage_sync_enabled", False)
    replace_areas([_selected_area_record()], auto_select_all=True)
    save_fr24_cluster(_enabled_cluster("c1"))
    save_fr24_cluster(_enabled_cluster("c2"))

    older_ts = _recent_timestamp() - 100
    newer_ts = _recent_timestamp()
    call_count = [0]

    def handler(request):
        call_count[0] += 1
        ts = older_ts if call_count[0] == 1 else newer_ts
        return _json_response({"data": [_valid_raw(timestamp=ts, lat=-1.0, lon=-55.0)]})

    mock_fr24_transport(handler)
    asyncio.run(run_fr24_cycle())
    assert call_count[0] == 2
    state = get_state("abc123")
    assert state is not None
    assert state["last_seen_at"] == datetime.fromtimestamp(newer_ts, tz=UTC).isoformat()


# --- Truncation not advancing disappearance ---


def test_truncation_not_advancing_disappearance(mock_fr24_transport):
    _enable_fr24()
    replace_areas([_selected_area_record()], auto_select_all=True)
    save_fr24_cluster(_enabled_cluster("c1"))

    base_time = datetime(2026, 7, 24, 12, 0, 0, tzinfo=UTC)
    upsert_state(
        {
            "aircraft_hex": "e49abc",
            "callsign": None,
            "registration": None,
            "aircraft_type": None,
            "airline_classification": "unknown_candidate",
            "classification_reason": "test",
            "last_seen_at": base_time.isoformat(),
            "last_provider": "flightradar24",
            "last_region_id": "c1",
            "latitude": -1.0,
            "longitude": -55.0,
            "altitude_ft": 2000,
            "ground_speed_kt": 50,
            "area_ids_json": json.dumps(["funai:test"]),
            "area_names_json": json.dumps(["Test Area"]),
            "inside_since": base_time.isoformat(),
            "inside_observations": 5,
            "outside_observations": 0,
            "stationary_since": base_time.isoformat(),
            "stationary_anchor_lat": -1.0,
            "stationary_anchor_lon": -55.0,
            "missing_cycles": 0,
            "episode_id": "e49abc-20260724T120000",
            "stop_alerted": 0,
            "disappeared_alerted": 0,
        }
    )

    items = [_valid_raw(hex=f"abc{i:03d}") for i in range(20)]

    def handler(request):
        return _json_response({"data": items})

    mock_fr24_transport(handler)
    asyncio.run(run_fr24_cycle())
    state = get_state("e49abc")
    assert state is not None
    assert state["missing_cycles"] == 0


# --- Failed FR24 poll not advancing disappearance ---


def test_failed_poll_not_advancing_disappearance(mock_fr24_transport):
    _enable_fr24()
    replace_areas([_selected_area_record()], auto_select_all=True)
    save_fr24_cluster(_enabled_cluster("c1"))

    base_time = datetime(2026, 7, 24, 12, 0, 0, tzinfo=UTC)
    upsert_state(
        {
            "aircraft_hex": "e49abc",
            "callsign": None,
            "registration": None,
            "aircraft_type": None,
            "airline_classification": "unknown_candidate",
            "classification_reason": "test",
            "last_seen_at": base_time.isoformat(),
            "last_provider": "flightradar24",
            "last_region_id": "c1",
            "latitude": -1.0,
            "longitude": -55.0,
            "altitude_ft": 2000,
            "ground_speed_kt": 50,
            "area_ids_json": json.dumps(["funai:test"]),
            "area_names_json": json.dumps(["Test Area"]),
            "inside_since": base_time.isoformat(),
            "inside_observations": 5,
            "outside_observations": 0,
            "stationary_since": base_time.isoformat(),
            "stationary_anchor_lat": -1.0,
            "stationary_anchor_lon": -55.0,
            "missing_cycles": 0,
            "episode_id": "e49abc-20260724T120000",
            "stop_alerted": 0,
            "disappeared_alerted": 0,
        }
    )

    def handler(request):
        return httpx.Response(500, content=b"Internal Server Error")

    mock_fr24_transport(handler)
    asyncio.run(run_fr24_cycle())
    state = get_state("e49abc")
    assert state is not None
    assert state["missing_cycles"] == 0


# --- Candidate enrichment once per episode ---


def test_candidate_enrichment_once_per_episode(mock_fr24_transport):
    _enable_fr24()
    set_setting("fr24_fetch_summary_on_entry", True)
    replace_areas([_selected_area_record()], auto_select_all=True)
    save_fr24_cluster(_enabled_cluster("c1"))

    summary_calls = []

    def handler(request):
        if "/flight-summary/full" in str(request.url):
            summary_calls.append(1)
            ids_param = request.url.params.get("flight_ids", "")
            ids_list = ids_param.split(",")
            return _json_response({"data": [{"fr24_id": fid} for fid in ids_list]})
        return _json_response({"data": [_valid_raw(lat=-1.0, lon=-55.0)]})

    mock_fr24_transport(handler)
    asyncio.run(run_fr24_cycle())
    state = get_state("abc123")
    assert state is not None
    assert state.get("episode_id")
    enrichment = get_fr24_enrichment("abc123", state["episode_id"])
    assert enrichment is not None

    asyncio.run(run_fr24_cycle())
    assert len(summary_calls) == 1


# --- Enrichment failure does not block detection ---


def test_enrichment_failure_does_not_block_detection(mock_fr24_transport):
    _enable_fr24()
    set_setting("fr24_fetch_summary_on_entry", True)
    replace_areas([_selected_area_record()], auto_select_all=True)
    save_fr24_cluster(_enabled_cluster("c1"))

    def handler(request):
        if "/flight-summary/full" in str(request.url):
            return httpx.Response(500, content=b"Internal Server Error")
        return _json_response({"data": [_valid_raw(lat=-1.0, lon=-55.0)]})

    mock_fr24_transport(handler)
    result = asyncio.run(run_fr24_cycle())
    assert result["success"] == 1
    assert result["events_created"] >= 0


# --- FR24 disabled ---


def test_fr24_disabled(mock_fr24_transport):
    set_setting("fr24_enabled", False)

    def handler(request):
        raise AssertionError("HTTP should not be called when FR24 is disabled")

    mock_fr24_transport(handler)
    result = asyncio.run(run_fr24_cycle())
    assert result["error_message"] == "FR24 disabled"
    # Benign skip, not a failure -- the dashboard relies on this flag to
    # avoid rendering a kill-switched cycle as a red "failed" run.
    assert result["skipped"] == 1


# --- No enabled clusters ---


def test_no_enabled_clusters(mock_fr24_transport):
    _enable_fr24()

    def handler(request):
        raise AssertionError("HTTP should not be called when no clusters are enabled")

    mock_fr24_transport(handler)
    result = asyncio.run(run_fr24_cycle())
    assert result["error_message"] == "no enabled clusters"
    assert result["skipped"] == 1


# --- Budget exhausted with pause_fr24 policy skips the cycle ---


def test_budget_exhausted_skips_cycle(mock_fr24_transport):
    _enable_fr24()
    set_setting("fr24_budget_policy", "pause_fr24")
    set_setting("fr24_monthly_operating_budget", 100)
    save_fr24_cluster(_enabled_cluster("c1"))

    bcid = billing_cycle_id(datetime.now(UTC))
    record_fr24_request(bcid, "live/flight-positions/light", "prior", "ok", 100, 200, 100, 0, False)

    def handler(request):
        raise AssertionError("HTTP should not be called when budget is exhausted")

    mock_fr24_transport(handler)
    result = asyncio.run(run_fr24_cycle())
    assert "budget exhausted" in result["error_message"]
    assert result["skipped"] == 1


# --- Positive control: a normal, non-truncated, non-failed cycle DOES advance disappearance ---


def _free_grid_tracked_state(aircraft_hex, last_seen_at, **overrides):
    base = {
        "aircraft_hex": aircraft_hex,
        "callsign": None,
        "registration": None,
        "aircraft_type": None,
        "airline_classification": "unknown_candidate",
        "classification_reason": "test",
        "last_seen_at": last_seen_at.isoformat(),
        "last_provider": "adsb_lol",
        "last_region_id": "region-free-grid",
        "latitude": -1.0,
        "longitude": -55.0,
        "altitude_ft": 2000,
        "ground_speed_kt": 50,
        "area_ids_json": json.dumps(["funai:test"]),
        "area_names_json": json.dumps(["Test Area"]),
        "inside_since": last_seen_at.isoformat(),
        "inside_observations": 3,
        "outside_observations": 0,
        "stationary_since": None,
        "stationary_anchor_lat": None,
        "stationary_anchor_lon": None,
        "missing_cycles": 0,
        "episode_id": f"{aircraft_hex}-episode",
        "stop_alerted": 0,
        "disappeared_alerted": 0,
    }
    base.update(overrides)
    return base


def test_successful_poll_advances_disappearance(mock_fr24_transport):
    # Proves the truncation/failure tests aren't vacuously true: under a
    # clean, non-truncated, non-failed cycle where the tracked aircraft
    # genuinely isn't observed, missing_cycles DOES increment.
    _enable_fr24()
    replace_areas([_selected_area_record()], auto_select_all=True)
    save_fr24_cluster(_enabled_cluster("c1"))
    base_time = datetime(2026, 7, 24, 12, 0, 0, tzinfo=UTC)
    upsert_state(_free_grid_tracked_state("e49abc", base_time, last_provider="flightradar24", last_region_id="c1"))

    def handler(request):
        return _json_response({"data": []})

    mock_fr24_transport(handler)
    asyncio.run(run_fr24_cycle())
    state = get_state("e49abc")
    assert state is not None
    assert state["missing_cycles"] == 1


# --- FR24 must not hijack an aircraft the free-provider grid is actively, freshly tracking ---


def test_fr24_does_not_hijack_freshly_tracked_free_grid_aircraft(mock_fr24_transport):
    _enable_fr24()
    replace_areas([_selected_area_record()], auto_select_all=True)
    save_fr24_cluster(_enabled_cluster("c1"))
    upsert_state(_free_grid_tracked_state("abc123", datetime.now(UTC)))

    def handler(request):
        return _json_response({"data": [_valid_raw(hex="abc123", lat=-1.0, lon=-55.0)]})

    mock_fr24_transport(handler)
    asyncio.run(run_fr24_cycle())
    state = get_state("abc123")
    assert state is not None
    assert state["last_provider"] == "adsb_lol"
    assert state["last_region_id"] == "region-free-grid"


def test_fr24_takes_over_when_free_grid_tracking_is_stale(mock_fr24_transport):
    _enable_fr24()
    replace_areas([_selected_area_record()], auto_select_all=True)
    save_fr24_cluster(_enabled_cluster("c1"))
    stale_time = datetime.now(UTC) - timedelta(hours=1)
    upsert_state(_free_grid_tracked_state("abc123", stale_time))

    def handler(request):
        return _json_response({"data": [_valid_raw(hex="abc123", lat=-1.0, lon=-55.0)]})

    mock_fr24_transport(handler)
    asyncio.run(run_fr24_cycle())
    state = get_state("abc123")
    assert state is not None
    assert state["last_provider"] == "flightradar24"


# --- Budget warning suppresses nonessential enrichment but keeps core monitoring ---


def test_budget_warning_suppresses_enrichment(mock_fr24_transport):
    _enable_fr24()
    set_setting("fr24_fetch_summary_on_entry", True)
    set_setting("fr24_budget_policy", "warn_only")
    set_setting("fr24_monthly_operating_budget", 1000)
    replace_areas([_selected_area_record()], auto_select_all=True)
    save_fr24_cluster(_enabled_cluster("c1"))

    bcid = billing_cycle_id(datetime.now(UTC))
    # 750/1000 = 75% -> "warning" (>=70%, <85%).
    record_fr24_request(bcid, "live/flight-positions/light", "prior", "ok", 100, 750, 100, 0, False)

    summary_calls = []

    def handler(request):
        if "/flight-summary/full" in str(request.url):
            summary_calls.append(1)
            return _json_response({"data": []})
        return _json_response({"data": [_valid_raw(lat=-1.0, lon=-55.0)]})

    mock_fr24_transport(handler)
    result = asyncio.run(run_fr24_cycle())
    assert result["success"] == 1
    assert len(summary_calls) == 0


# --- Truncation triggers an exceptional Count calibration call ---


def test_truncation_triggers_count_calibration(mock_fr24_transport):
    _enable_fr24()
    set_setting("fr24_response_limit", 20)
    save_fr24_cluster(_enabled_cluster("c1"))
    items = [_valid_raw(hex=f"abc{i:03d}") for i in range(20)]
    count_calls = []

    def handler(request):
        if "/flight-positions/count" in str(request.url):
            count_calls.append(1)
            return _json_response({"count": 42})
        return _json_response({"data": items})

    mock_fr24_transport(handler)
    result = asyncio.run(run_fr24_cycle())
    assert len(count_calls) == 1
    # Successful calibration is diagnostic, not an error -- it's logged via
    # fr24.count.calibrated, not surfaced in error_message (which is
    # reserved for actual failures/truncation warnings).
    assert result["error_message"] == "c1: possibly truncated (20 records)"


def test_non_truncated_response_does_not_call_count(mock_fr24_transport):
    _enable_fr24()
    save_fr24_cluster(_enabled_cluster("c1"))
    count_calls = []

    def handler(request):
        if "/flight-positions/count" in str(request.url):
            count_calls.append(1)
            return _json_response({"count": 0})
        return _json_response({"data": []})

    mock_fr24_transport(handler)
    asyncio.run(run_fr24_cycle())
    assert len(count_calls) == 0


# --- Daily usage sync ---


def test_usage_sync_called_once_per_cycle_when_enabled(mock_fr24_transport):
    _enable_fr24()
    set_setting("fr24_usage_sync_enabled", True)
    save_fr24_cluster(_enabled_cluster("c1"))
    usage_calls = []

    def handler(request):
        if "/usage" in str(request.url):
            usage_calls.append(1)
            return _json_response({"period": "24h"})
        return _json_response({"data": []})

    mock_fr24_transport(handler)
    asyncio.run(run_fr24_cycle())
    assert len(usage_calls) == 1
    # A second cycle within the same 24h window must not sync again.
    asyncio.run(run_fr24_cycle())
    assert len(usage_calls) == 1


def test_usage_sync_disabled_by_setting(mock_fr24_transport):
    _enable_fr24()
    set_setting("fr24_usage_sync_enabled", False)
    save_fr24_cluster(_enabled_cluster("c1"))
    usage_calls = []

    def handler(request):
        if "/usage" in str(request.url):
            usage_calls.append(1)
            return _json_response({"period": "24h"})
        return _json_response({"data": []})

    mock_fr24_transport(handler)
    asyncio.run(run_fr24_cycle())
    assert len(usage_calls) == 0
