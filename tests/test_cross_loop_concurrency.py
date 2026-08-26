"""Cross-loop concurrency tests for the aircraft_state CAS funnel.

Lane CROSS-LOOP-CAS (roadmap §6.5 / build/W4-CROSS-LOOP-CAS-plan.md): the true
lost-update window is ``process_missing()``'s ``active_states()`` snapshot
(app/detection.py:353) through its ``upsert_state()`` write
(app/detection.py:425). A free-grid ``process_observation()`` write landing
inside that window is silently overwritten by the stale FR24 snapshot while
the upsert stays unconditional. These tests pin that window with a
deterministic gated interleaving (threading events, no sleeps) and exercise
every ``cas_upsert_state`` branch. Fully offline and deterministic.
"""

import asyncio
import httpx
import json
import logging
import sqlite3
import threading
from datetime import UTC, datetime, timedelta

import pytest
from shapely.geometry import Polygon, mapping

import app.detection as detection_mod
from app.database import (
    get_state,
    replace_areas,
    upsert_state,
)
from app.detection import process_missing, process_observation
from app.geofences import GeofenceIndex
from app.providers.base import AircraftObservation


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


def _observation(**overrides):
    values = dict(
        hex="e49abc",
        callsign=None,
        registration=None,
        aircraft_type=None,
        latitude=-1.0,
        longitude=-55.0,
        altitude_ft=2000,
        on_ground=False,
        ground_speed_kt=100,
        track_deg=90,
        observed_at=datetime.now(UTC),
        seen_pos_seconds=1,
        region_id="region-test",
        provider="adsb_lol",
    )
    values.update(overrides)
    return AircraftObservation(**values)


def _fr24_owned_state(last_seen_at, aircraft_hex="e49abc", **overrides):
    """Active FR24-owned row inside the selected area, below the disappearance
    qualification threshold (inside_observations=1 < default minimum of 2) so
    the gated missing-cycle writer performs only the bookkeeping write."""
    base = {
        "aircraft_hex": aircraft_hex,
        "callsign": None,
        "registration": None,
        "aircraft_type": None,
        "airline_classification": "unknown_candidate",
        "classification_reason": "test",
        "last_seen_at": last_seen_at.isoformat(),
        "last_provider": "flightradar24",
        "last_region_id": "c1",
        "latitude": -1.0,
        "longitude": -55.0,
        "altitude_ft": 2000,
        "ground_speed_kt": 50,
        "area_ids_json": json.dumps(["funai:test"]),
        "area_names_json": json.dumps(["Test Area"]),
        "inside_since": last_seen_at.isoformat(),
        "inside_observations": 1,
        "outside_observations": 0,
        "stationary_since": None,
        "stationary_anchor_lat": None,
        "stationary_anchor_lon": None,
        "missing_cycles": 0,
        "episode_id": f"{aircraft_hex}-20260724T120000",
        "stop_alerted": 0,
        "disappeared_alerted": 0,
    }
    base.update(overrides)
    return base


def test_concurrent_writers_no_lost_update(monkeypatch):
    """The plan's pinned race: FR24's missing-cycle writer snapshots through
    active_states(), the free grid commits a newer observation inside that
    window, then the stale FR24 writer resumes and must NOT clobber it."""
    replace_areas([_selected_area_record()], True)
    t0 = datetime(2026, 7, 24, 12, 0, 0, tzinfo=UTC)
    upsert_state(_fr24_owned_state(t0))
    index = GeofenceIndex()

    real_active_states = detection_mod.active_states
    snapshot_taken = threading.Event()
    allow_missing_write = threading.Event()

    def gated_active_states():
        rows = real_active_states()
        snapshot_taken.set()
        assert allow_missing_write.wait(timeout=2), (
            "free-grid writer never released the missing-cycle gate"
        )
        return rows

    monkeypatch.setattr(detection_mod, "active_states", gated_active_states)

    outcome = {}

    def run_missing_cycle():
        outcome["missing_events"] = asyncio.run(
            process_missing({"c1"}, set(), "shadow")
        )

    worker = threading.Thread(target=run_missing_cycle, name="fr24-missing-writer")
    worker.start()
    try:
        assert snapshot_taken.wait(timeout=2), "FR24 snapshot was never taken"
        t2 = t0 + timedelta(minutes=5)
        free_events = asyncio.run(
            process_observation(
                _observation(
                    observed_at=t2,
                    provider="adsb_lol",
                    region_id="region-free-grid",
                ),
                index,
                "shadow",
            )
        )
        assert free_events == 0
        allow_missing_write.set()
    finally:
        worker.join(timeout=5)
    assert not worker.is_alive(), "stale FR24 writer deadlocked"
    assert outcome["missing_events"] == 0

    final = get_state("e49abc")
    assert final is not None
    # Serialized outcome: the fresher free-grid observation wins every field
    # the stale snapshot tried to restore -- asserted concretely on
    # last_provider/last_region_id/missing_cycles, not mere row existence.
    assert final["last_provider"] == "adsb_lol"
    assert final["last_region_id"] == "region-free-grid"
    assert final["missing_cycles"] == 0
    assert final["last_seen_at"] == t2.isoformat()
# --- Remaining §6.5 tests-to-write-first ------------------------------------


@pytest.fixture(autouse=True)
def _reset_fr24_scheduler_module_state():
    # Mirror tests/test_fr24_scheduler.py: throttle globals on the scheduler
    # module must never leak between tests in either direction.
    import app.fr24_scheduler as fr24_scheduler_mod

    fr24_scheduler_mod._last_usage_sync = None
    fr24_scheduler_mod._last_count_calibration = {}
    yield


@pytest.fixture
def mock_fr24_transport(monkeypatch):
    handlers = {}

    def set_handler(fn):
        handlers["fn"] = fn

    real_async_client = httpx.AsyncClient

    def fake_async_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handlers["fn"])
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", fake_async_client)
    return set_handler


def _json_response(data, status=200):
    return httpx.Response(
        status,
        content=json.dumps(data).encode(),
        headers={"content-type": "application/json"},
    )


def _enable_fr24():
    from app.settings_store import set_setting

    set_setting("fr24_enabled", True)
    set_setting("flightradar24_api_key", "test-token")
    set_setting("fr24_poll_interval_seconds", 300)
    set_setting("fr24_inter_cluster_delay_seconds", 0)


def _enabled_cluster(cluster_id="c1"):
    return {
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


def _valid_raw(**overrides):
    base = {
        "hex": "abc123",
        "lat": -1.0,
        "lon": -55.0,
        "alt": 3000,
        "callsign": "  test123  ",
        "fr24_id": "fr24-abc",
        "timestamp": int(datetime.now(UTC).timestamp()),
    }
    base.update(overrides)
    return base


_LEGACY_AIRCRAFT_STATE_DDL = """
CREATE TABLE aircraft_state (
    aircraft_hex TEXT PRIMARY KEY,
    callsign TEXT,
    registration TEXT,
    aircraft_type TEXT,
    airline_classification TEXT NOT NULL DEFAULT 'unknown_candidate',
    classification_reason TEXT,
    last_seen_at TEXT,
    last_provider TEXT,
    last_region_id TEXT,
    latitude REAL,
    longitude REAL,
    altitude_ft REAL,
    ground_speed_kt REAL,
    area_ids_json TEXT NOT NULL DEFAULT '[]',
    area_names_json TEXT NOT NULL DEFAULT '[]',
    inside_since TEXT,
    inside_observations INTEGER NOT NULL DEFAULT 0,
    outside_observations INTEGER NOT NULL DEFAULT 0,
    stationary_since TEXT,
    stationary_anchor_lat REAL,
    stationary_anchor_lon REAL,
    missing_cycles INTEGER NOT NULL DEFAULT 0,
    episode_id TEXT,
    stop_alerted INTEGER NOT NULL DEFAULT 0 CHECK(stop_alerted IN (0,1)),
    disappeared_alerted INTEGER NOT NULL DEFAULT 0 CHECK(disappeared_alerted IN (0,1)),
    updated_at TEXT NOT NULL
);
"""


def test_cas_conflict_applies_merge_rule():
    """Two writers leaving from ONE read revision are ordered by strict >
    observed_at (mirrors _merge_observation). Covers initial CAS success,
    conflict -> re-read -> retry-success, and conflict -> committed-wins."""
    from app.database import cas_upsert_state

    t0 = datetime(2026, 7, 24, 12, 0, 0, tzinfo=UTC)
    upsert_state(_fr24_owned_state(t0, aircraft_hex="cafe01"))
    snapshot = get_state("cafe01")
    assert snapshot["updated_seq"] == 1

    intermediate = dict(snapshot)
    intermediate["last_seen_at"] = (t0 + timedelta(minutes=2)).isoformat()
    intermediate["last_provider"] = "provider-mid"
    cas_upsert_state(intermediate)  # plain CAS success -> seq 2

    fresher = dict(snapshot)  # still carrying the stale revision 1
    fresher["last_seen_at"] = (t0 + timedelta(minutes=5)).isoformat()
    fresher["last_provider"] = "adsb_lol"
    fresher["last_region_id"] = "region-free-grid"
    cas_upsert_state(fresher)  # conflict -> re-read -> retry wins -> seq 3

    staler = dict(snapshot)  # stale revision 1, older timestamp
    staler["last_seen_at"] = (t0 + timedelta(minutes=1)).isoformat()
    staler["last_provider"] = "flightradar24"
    cas_upsert_state(staler)  # conflict -> committed strictly newer -> yields

    final = get_state("cafe01")
    assert final["last_provider"] == "adsb_lol"
    assert final["last_region_id"] == "region-free-grid"
    assert final["last_seen_at"] == (t0 + timedelta(minutes=5)).isoformat()
    assert final["updated_seq"] == 3


def test_updated_seq_migrates_legacy_rows_at_boot(tmp_path, monkeypatch):
    """A pre-lane volume (old aircraft_state DDL) boots through init_db(),
    gets updated_seq=0 backfilled, and its first CAS update succeeds."""
    from app.config import env_settings
    from app.database import cas_upsert_state, db, init_db

    legacy_path = tmp_path / "legacy.db"
    monkeypatch.setenv("DATABASE_PATH", str(legacy_path))
    env_settings.cache_clear()
    try:
        raw = sqlite3.connect(legacy_path)
        raw.executescript(_LEGACY_AIRCRAFT_STATE_DDL)
        stamp = datetime(2026, 7, 24, 12, 0, 0, tzinfo=UTC).isoformat()
        raw.execute(
            "INSERT INTO aircraft_state(aircraft_hex, last_seen_at, last_provider,"
            " last_region_id, episode_id, area_ids_json, updated_at)"
            " VALUES('deadbeef01', ?, 'flightradar24', 'c1', 'deadbeef01-ep', '[]', ?)",
            (stamp, stamp),
        )
        raw.commit()
        raw.close()

        init_db()  # additive migration backfills updated_seq=0

        with db() as conn:
            columns = {
                str(row[1]) for row in conn.execute("PRAGMA table_info(aircraft_state)")
            }
        assert "updated_seq" in columns
        migrated = get_state("deadbeef01")
        assert migrated is not None
        assert migrated["updated_seq"] == 0

        migrated["last_seen_at"] = (
            datetime(2026, 7, 24, 12, 5, 0, tzinfo=UTC).isoformat()
        )
        migrated["last_provider"] = "adsb_lol"
        cas_upsert_state(migrated)  # first CAS update rides legacy sequence 0

        after = get_state("deadbeef01")
        assert after["updated_seq"] == 1
        assert after["last_provider"] == "adsb_lol"
    finally:
        env_settings.cache_clear()


def test_cas_conflict_storm_logs_and_falls_back(monkeypatch, caplog):
    """Pathological contention (every conditional attempt loses): exactly one
    warning, then the bounded atomic last-writer-wins fallback persists."""
    import app.database as database_mod
    from app.database import cas_upsert_state

    t0 = datetime(2026, 7, 24, 12, 0, 0, tzinfo=UTC)
    upsert_state(_fr24_owned_state(t0, aircraft_hex="storm01"))
    snapshot = get_state("storm01")

    storm_write = dict(snapshot)
    storm_write["last_seen_at"] = (t0 + timedelta(minutes=1)).isoformat()
    storm_write["last_provider"] = "storm-winner"

    def never_matches(payload, expected_seq):
        return 0

    monkeypatch.setattr(database_mod, "_cas_update_aircraft_state", never_matches)

    with caplog.at_level(logging.WARNING):
        cas_upsert_state(storm_write)

    fallbacks = [
        record for record in caplog.records if "cas_conflict_fallback" in record.getMessage()
    ]
    assert len(fallbacks) == 1
    assert "storm01" in fallbacks[0].getMessage()

    final = get_state("storm01")
    assert final["last_provider"] == "storm-winner"
    assert final["last_seen_at"] == storm_write["last_seen_at"]
    assert final["updated_seq"] == 2


def test_free_grid_deferral_still_wins_when_fresh(mock_fr24_transport):
    """Deferral regression: a full mocked FR24 cycle over a freshly free-owned
    row keeps free ownership untouched (roadmap invariant)."""
    from app.database import save_fr24_cluster
    from app.fr24_scheduler import run_fr24_cycle

    _enable_fr24()
    replace_areas([_selected_area_record()], True)
    save_fr24_cluster(_enabled_cluster("c1"))
    upsert_state(
        _fr24_owned_state(
            datetime.now(UTC),
            aircraft_hex="abc123",
            last_provider="adsb_lol",
            last_region_id="region-free-grid",
        )
    )

    def handler(request):
        return _json_response({"data": [_valid_raw(hex="abc123", lat=-1.0, lon=-55.0)]})

    mock_fr24_transport(handler)
    result = asyncio.run(run_fr24_cycle())

    assert result.get("skipped") == 0
    assert result.get("clusters_successful") == 1  # the cycle really ran and fetched
    # Deferred observations are deliberately NOT fed into detection
    # (fr24_scheduler.py: _free_grid_actively_tracking gate precedes
    # _merge_observation), so the deferred hex never counts as returned.
    assert result.get("aircraft_returned") == 0
    state = get_state("abc123")
    assert state is not None
    assert state["last_provider"] == "adsb_lol"
    assert state["last_region_id"] == "region-free-grid"
    assert state["missing_cycles"] == 0


def test_loops_progress_independently_under_contention(monkeypatch):
    """poll_lock/fr24_lock (and coverage-poll/fr24-poll flock names) stay
    distinct: each loop holds its own lock while blocked and the other still
    makes progress -- no new cross-blocking enters either cycle."""
    import app.main as main_mod
    import app.fr24_scheduler as sched_mod

    coverage_entered = asyncio.Event()
    fr24_entered = asyncio.Event()
    release = asyncio.Event()

    async def gated_coverage_locked():
        coverage_entered.set()
        await asyncio.wait_for(release.wait(), timeout=2)
        return {"status": "ok", "lane": "coverage"}

    async def gated_fr24_locked():
        fr24_entered.set()
        await asyncio.wait_for(release.wait(), timeout=2)
        return {"status": "ok", "lane": "fr24"}

    monkeypatch.setattr(main_mod, "_run_coverage_cycle_locked", gated_coverage_locked)
    monkeypatch.setattr(sched_mod, "_run_fr24_cycle_locked", gated_fr24_locked)

    async def drive():
        coverage_task = asyncio.create_task(main_mod.run_coverage_cycle())
        fr24_task = asyncio.create_task(sched_mod.run_fr24_cycle())
        await asyncio.wait_for(
            asyncio.gather(coverage_entered.wait(), fr24_entered.wait()), timeout=2
        )
        # Both loops hold THEIR OWN locks simultaneously: neither blocked the other.
        assert main_mod.poll_lock.locked()
        assert sched_mod.fr24_lock.locked()
        release.set()
        return await asyncio.wait_for(
            asyncio.gather(coverage_task, fr24_task), timeout=5
        )

    coverage_result, fr24_result = asyncio.run(drive())
    assert coverage_result == {"status": "ok", "lane": "coverage"}
    assert fr24_result == {"status": "ok", "lane": "fr24"}


def test_cas_fallback_advances_live_sequence_past_racing_third_writer(monkeypatch):
    """G-review blocker regression: between the fallback's re-read and its
    unconditional upsert, a real third writer may advance the live sequence.
    The fallback must advance the row's CURRENT LIVE sequence inside the
    statement -- never reuse its stale re-read -- so no snapshot held by a
    losing writer can re-pass the CAS guard afterwards."""
    import app.database as database_mod
    from app.database import _cas_update_aircraft_state, cas_upsert_state

    t0 = datetime(2026, 7, 24, 12, 0, 0, tzinfo=UTC)
    upsert_state(_fr24_owned_state(t0, aircraft_hex="relay01"))

    # The storm writer's snapshot predates every later advance (seq 1).
    winner_snapshot = get_state("relay01")
    winner_write = dict(winner_snapshot)
    winner_write["last_seen_at"] = (t0 + timedelta(minutes=5)).isoformat()
    winner_write["last_provider"] = "storm-winner"

    # Early bird advances seq 1 -> 2 so the winner's first CAS attempt loses.
    early = dict(winner_snapshot)
    early["last_seen_at"] = (t0 + timedelta(minutes=1)).isoformat()
    early["last_provider"] = "early-bird"
    assert _cas_update_aircraft_state(early, 1) == 1

    seam_state = {"reads": 0, "loser_snapshot": None}

    real_get_state = database_mod.get_state

    def seamed_get_state(aircraft_hex):
        row = real_get_state(aircraft_hex)
        seam_state["reads"] += 1
        if aircraft_hex != "relay01" or seam_state["reads"] not in (1, 2):
            return row
        # A real third writer commits inside EACH resolution window and the
        # concurrent reader grabs what becomes the next stale-but-seq-matching
        # snapshot -- yet this fallback's re-read result is returned one
        # advance behind the live sequence, exactly the reviewer-reproduced
        # interleaving (re-read raced by writers it cannot see).
        racer = dict(row)
        racer["last_seen_at"] = (
            t0 + timedelta(minutes=1 + seam_state["reads"])
        ).isoformat()
        racer["last_provider"] = f"racer-{seam_state['reads']}"
        assert _cas_update_aircraft_state(racer, int(row["updated_seq"])) == 1
        post_advance = real_get_state("relay01")
        if seam_state["reads"] == 2:
            # Loser read the row after racer-2 but before the fallback wrote.
            seam_state["loser_snapshot"] = post_advance
        return row

    monkeypatch.setattr(database_mod, "get_state", seamed_get_state)
    cas_upsert_state(winner_write)

    assert seam_state["loser_snapshot"] is not None
    max_losing_seq = max(
        1,
        int(winner_snapshot["updated_seq"]),
        int(seam_state["loser_snapshot"]["updated_seq"]),
    )

    after_fallback = get_state("relay01")
    # The fallback must land STRICTLY past every sequence any writer observed,
    # including racer-two's in-window advance.
    assert after_fallback["updated_seq"] > max_losing_seq
    assert after_fallback["last_provider"] == "storm-winner"
    assert after_fallback["last_seen_at"] == (t0 + timedelta(minutes=5)).isoformat()

    # The stale loser can no longer re-pass the CAS guard: replaying its
    # snapshot must yield to the committed newer state, not restore it.
    cas_upsert_state(seam_state["loser_snapshot"])
    final = get_state("relay01")
    assert final["last_provider"] == "storm-winner"
    assert final["last_seen_at"] == (t0 + timedelta(minutes=5)).isoformat()
    assert final["missing_cycles"] == 0
