"""Live FR24 sandbox event-lifecycle simulation.

Drives the running sandbox compose stack through every event lifecycle the
production system can produce, asserting each stage in the real DB/API
surfaces:

  S0  reset + dynamic fixture discovery (FR24 rotates the static payload --
      nothing here may hardcode a hex or coordinate)
  S1  presence/entry: episodes open, enrichment fetched, no events,
      scheduled-aircraft classification filtering
  S2  DISAPPEARED via the real production path (free-grid deferral seed
      simulates the aircraft vanishing from FR24 coverage) + manual track
      fetch on the event
  S3  one clearly-labeled synthetic PROBABLE_STOP row (the live fixture
      flies at ~491 kt -- above stop_max_speed_kt's 150 kt ceiling -- so a
      real stop event can never fire from sandbox data; this row exists only
      so the UI shows both event types)
  S4  episode close-by-leaving: aircraft exits the selected area, episode
      closes with NO event
  S5  budget warning state: cycle runs, nonessential calls suppressed,
      dashboard reports the degraded budget state
  S6  budget exhausted + pause_fr24: cycle skipped, track fetch refused,
      blocker surfaced in status

Opt-in like the other sandbox suites: skipped unless
FR24_SANDBOX_BASE_URL and FR24_SANDBOX_ADMIN_PASSWORD are set.
scripts/fr24_sandbox_simulate.sh wires everything (and runs the
screenshot/restore steps around this file).

The final test normally restores every setting S0 touched. Run with
FR24_SANDBOX_SKIP_RESTORE=1 to leave the end state (budget exhausted,
both event types present) standing for UI screenshots -- the wrapper's
restore step then puts settings back.
"""

import json
import math
import os
import subprocess
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

pytestmark = [
    pytest.mark.fr24_sandbox,
    pytest.mark.skipif(
        not (os.environ.get("FR24_SANDBOX_BASE_URL") and os.environ.get("FR24_SANDBOX_ADMIN_PASSWORD")),
        reason="FR24_SANDBOX_BASE_URL and FR24_SANDBOX_ADMIN_PASSWORD not set (compose stack not wired)",
    ),
]

BASE_URL = os.environ.get("FR24_SANDBOX_BASE_URL", "http://127.0.0.1:8081").rstrip("/")
ADMIN_PASSWORD = os.environ["FR24_SANDBOX_ADMIN_PASSWORD"] if os.environ.get("FR24_SANDBOX_ADMIN_PASSWORD") else ""
SKIP_RESTORE = os.environ.get("FR24_SANDBOX_SKIP_RESTORE", "") == "1"

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPOSE = [
    "docker",
    "compose",
    "-f",
    "docker-compose.yml",
    "-f",
    "docker-compose.sandbox.yml",
    "-p",
    "flight-geofence-sandbox",
]
ARTIFACTS_DIR = REPO_ROOT / "sandbox-artifacts"
SETTINGS_BACKUP = ARTIFACTS_DIR / "settings-backup.json"
AREA_SOURCE = "sandbox-sim"

# Settings this session mutates; everything else is left untouched.
TOUCHED_SETTINGS = (
    "disappear_max_altitude_ft",
    "operating_phase",
    "fr24_monthly_operating_budget",
    "fr24_budget_policy",
)

# Shared session state -- tests run in file order and build on each other.
SESSION: dict = {}


# ---------------------------------------------------------------------------
# helpers: container DB access, manual cycle triggering, API client
# ---------------------------------------------------------------------------


def _container(code: str, timeout: float = 120) -> tuple[str, str]:
    """Run python inside the sandbox container (same env, same sqlite file as
    the app process); returns (stdout, stderr)."""
    result = subprocess.run(
        COMPOSE + ["exec", "-T", "flight-monitor", "python", "-c", code],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise AssertionError(f"container exec failed: {result.stderr[-600:]}")
    return result.stdout, result.stderr


def db_rows(sql: str, params: tuple = ()) -> list[dict]:
    code = (
        "import json\n"
        "from app.database import db\n"
        f"with db() as conn:\n"
        f"    rows = [dict(r) for r in conn.execute({sql!r}, {params!r}).fetchall()]\n"
        "print(json.dumps(rows, default=str))\n"
    )
    return json.loads(_container(code)[0].strip().splitlines()[-1])


def db_write(sql: str, params: tuple = ()) -> None:
    code = (
        "from app.database import db\n"
        f"with db() as conn:\n"
        f"    conn.execute({sql!r}, {params!r})\n"
    )
    _container(code)


def db_write_many(statements: list[tuple[str, tuple]]) -> None:
    """All statements in one transaction (the db() context commits once)."""
    body = "".join(
        f"    conn.execute({sql!r}, {params!r})\n" for sql, params in statements
    )
    _container("from app.database import db\nwith db() as conn:\n" + body)


def run_cycle() -> dict:
    """Trigger one FR24 poll cycle in a separate container process. The
    background loop (FR24_POLL_INTERVAL_SECONDS=300, env-locked in the
    sandbox) may collide; the cross-process flock makes that a clean
    'skipped' result which we simply retry."""
    code = (
        "import asyncio, json\n"
        "from app.fr24_scheduler import run_fr24_cycle\n"
        "print(json.dumps(asyncio.run(run_fr24_cycle()), default=str))\n"
    )
    for _ in range(6):
        stdout, stderr = _container(code)
        result = json.loads(stdout.strip().splitlines()[-1])
        if result.get("status") != "skipped":
            # Manual exec cycles log to this process's stderr, NOT the
            # container's log stream (that only carries the background loop).
            # Keep the tail for log-line assertions.
            SESSION["cycle_logs"] = stderr[-4000:]
            return result
        time.sleep(4)
    pytest.fail("manual cycle kept reporting skipped (background loop contention)")


def container_logs() -> str:
    result = subprocess.run(
        COMPOSE + ["logs", "--no-color", "flight-monitor"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=60,
    )
    return result.stdout + result.stderr


def wait_for(predicate, timeout: float = 45, interval: float = 3, message: str = "condition"):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = predicate()
        if last:
            return last
        time.sleep(interval)
    pytest.fail(f"timed out waiting for {message}: last={last!r}")


@pytest.fixture
def api():
    client = httpx.Client(base_url=BASE_URL, timeout=30, follow_redirects=True)
    login = client.post("/api/auth/login", json={"password": ADMIN_PASSWORD})
    assert login.status_code == 200, f"login failed: {login.status_code} {login.text[:200]}"
    client.headers.update({"X-CSRF-Token": login.json()["csrf_token"]})
    yield client
    client.close()


def set_settings(api, values: dict) -> dict:
    response = api.post("/api/settings", json={"values": values, "clear": []})
    assert response.status_code == 200, f"settings update failed: {response.text[:300]}"
    body = response.json()
    assert not body["errors"], f"settings update errored: {body['errors']}"
    return body


def cluster_payload(name: str, *, north: float, south: float, west: float, east: float) -> dict:
    return {
        "name": name,
        "enabled": True,
        "buffer_km": 15.0,
        "min_altitude_ft": -2000.0,
        "max_altitude_ft": 45000.0,
        "categories": ["T", "H", "N"],
        "area_ids": [],
        "use_manual_bounds": True,
        "manual_north": north,
        "manual_south": south,
        "manual_west": west,
        "manual_east": east,
    }


def insert_sim_area(area_id: str, name: str, lat: float, lon: float, half_size: float = 0.3) -> None:
    """One square selected geofence around a point, inserted directly -- the
    areas API only selects rows brought in by dataset sync, which the sandbox
    stack deliberately runs without."""
    polygon = {
        "type": "Polygon",
        "coordinates": [
            [
                [lon - half_size, lat - half_size],
                [lon + half_size, lat - half_size],
                [lon + half_size, lat + half_size],
                [lon - half_size, lat + half_size],
                [lon - half_size, lat - half_size],
            ]
        ],
    }
    db_write_many(
        [
            ("DELETE FROM areas WHERE id=?", (area_id,)),
            (
                "INSERT INTO areas(id, source, external_id, name, category, state, phase,"
                " selected, geometry_json, min_lon, min_lat, max_lon, max_lat, source_date, updated_at)"
                " VALUES (?,?,?,?,?,?,?,1,?,?,?,?,?,?,datetime('now'))",
                (
                    area_id,
                    AREA_SOURCE,
                    area_id,
                    name,
                    "conservation",
                    None,
                    None,
                    json.dumps(polygon),
                    lon - half_size,
                    lat - half_size,
                    lon + half_size,
                    lat + half_size,
                    None,  # source_date
                ),
            ),
        ]
    )


# ---------------------------------------------------------------------------
# S0 -- reset + discover
# ---------------------------------------------------------------------------


def test_s0_reset_and_discover(api):
    # Refuse to run anywhere but a sandbox stack. This suite's first act is
    # DELETE FROM events + dropping every FR24 cluster, so a misaimed
    # FR24_SANDBOX_BASE_URL must fail here rather than halfway through.
    # STATE_RETENTION_DAYS=36500 is a sandbox-only accommodation
    # (.env.sandbox.example); no production stack carries it.
    guard = api.get("/api/fr24/status").json()
    assert guard.get("retention_state_days", 0) >= 36500, (
        "refusing to run destructive scenarios: "
        f"{BASE_URL} does not look like the sandbox stack ({guard.get('retention_state_days')!r})"
    )

    # Wipe detection-shaped state so repeated runs start clean. Request log
    # and poll-run history stay: accumulated credits are the fuel the budget
    # scenarios (S5/S6) spend against.
    db_write_many(
        [
            ("DELETE FROM events", ()),
            ("DELETE FROM aircraft_state", ()),
            ("DELETE FROM fr24_enrichment", ()),
            (f"DELETE FROM areas WHERE source='{AREA_SOURCE}'", ()),
        ]
    )
    for cluster in api.get("/api/fr24/clusters").json()["clusters"]:
        response = api.delete(f"/api/fr24/clusters/{cluster['id']}")
        assert response.status_code in (200, 204), response.text[:200]

    # Back up every setting this session will touch, for the restore step.
    settings = api.get("/api/settings").json()["settings"]
    ARTIFACTS_DIR.mkdir(exist_ok=True)
    # Each settings item arrives as {value, source, locked, ...}; store the
    # plain values so the restore POST (here and in fr24_sandbox_restore.py)
    # round-trips directly.
    backup = {key: (settings.get(key) or {}).get("value") for key in TOUCHED_SETTINGS}
    # A poisoned budget left over from an interrupted prior run (S6 sets
    # budget=used and only restores it on a clean finish) must not be
    # captured as "the baseline" here -- S6 would then faithfully restore
    # the poison and the stack would stay broken forever. Substitute the
    # SettingDef default (app/settings_store.py) instead; every other
    # touched setting still snapshots its live value.
    if guard.get("budget_state") != "normal":
        # Ask the server for its own default rather than hardcoding one: clear
        # the override, then read back whatever the SettingDef supplies. Keeps
        # this suite black-box and immune to the default drifting.
        cleared = api.post(
            "/api/settings", json={"values": {}, "clear": ["fr24_monthly_operating_budget"]}
        )
        assert cleared.status_code == 200, f"budget heal failed: {cleared.text[:300]}"
        healed_value = (
            api.get("/api/settings").json()["settings"]["fr24_monthly_operating_budget"]["value"]
        )
        print(
            f"S0: healing poisoned baseline (budget_state={guard.get('budget_state')!r}) -- "
            f"backing up the server default {healed_value} instead of the live value"
        )
        backup["fr24_monthly_operating_budget"] = healed_value
    SETTINGS_BACKUP.write_text(json.dumps(backup))

    # Baseline settings for the run: altitude gate must admit the fixture's
    # cruise altitude (default 6000 ft); phase "review" creates events with
    # review_only email status (live is refused while email_provider=console
    # -- _live_readiness_errors rejects it and would roll the phase back); the
    # budget is parked high so a previously interrupted session's exhausted
    # end-state (S6 sets budget=used) can't skip this run's discovery cycle.
    set_settings(
        api,
        {
            "disappear_max_altitude_ft": 60000,
            "operating_phase": "review",
            "fr24_monthly_operating_budget": 100000,
        },
    )

    # World-bounds cluster + one cycle discovers whatever fixture FR24 is
    # currently serving. Sandbox ignores query params, so bounds shape
    # nothing -- they exist only so the cluster is pollable. A temporary
    # world-covering selected area is required too: process_observation only
    # writes aircraft_state for aircraft inside a selected area, so without
    # it a successful cycle would leave no discoverable rows.
    insert_sim_area(
        "sandbox-sim-world", "Sandbox simulation world (discovery)", 0, 0, half_size=179.9
    )
    created = api.post(
        "/api/fr24/clusters",
        json=cluster_payload("sandbox-sim-discovery", north=89, south=-89, west=-179, east=179),
    )
    assert created.status_code == 200, created.text[:300]
    discovery_cluster_id = created.json()["id"]
    try:
        run = run_cycle()
        assert run["success"] == 1, f"discovery cycle failed: {run}"
        assert run["aircraft_returned"] >= 1, f"no aircraft returned: {run}"
    finally:
        api.delete(f"/api/fr24/clusters/{discovery_cluster_id}")
        db_write("DELETE FROM areas WHERE id='sandbox-sim-world'")

    rows = db_rows("SELECT * FROM aircraft_state")
    assert rows, "discovery cycle created no aircraft_state rows"
    for row in rows:
        print(f"discovered: {row['callsign']} hex={row['aircraft_hex']} "
              f"class={row['airline_classification']} "
              f"lat={row['latitude']} lon={row['longitude']} alt={row['altitude_ft']}")

    target = next((r for r in rows if r["airline_classification"] != "scheduled_airline"), None)
    control = next((r for r in rows if r["airline_classification"] == "scheduled_airline"), None)
    if target is None:
        pytest.skip(
            "fixture returned only scheduled-airline aircraft -- classification-dependent "
            "scenarios (DISAPPEARED) cannot run; rerun after FR24 rotates the fixture"
        )

    # Tight cluster + one selected area per aircraft.
    all_rows = [target] + ([control] if control else [])
    north = max(r["latitude"] for r in all_rows) + 0.5
    south = min(r["latitude"] for r in all_rows) - 0.5
    east = max(r["longitude"] for r in all_rows) + 0.5
    west = min(r["longitude"] for r in all_rows) - 0.5
    created = api.post(
        "/api/fr24/clusters", json=cluster_payload("sandbox-sim", north=north, south=south, west=west, east=east)
    )
    assert created.status_code == 200, created.text[:300]

    insert_sim_area("sandbox-sim-target", "Sandbox Sim Target Area", target["latitude"], target["longitude"])
    if control:
        insert_sim_area("sandbox-sim-control", "Sandbox Sim Control Area", control["latitude"], control["longitude"])

    SESSION.update(
        {
            "target_hex": target["aircraft_hex"],
            "control_hex": control["aircraft_hex"] if control else None,
        }
    )


# ---------------------------------------------------------------------------
# S1 -- presence / entry / enrichment (no event)
# ---------------------------------------------------------------------------


def test_s1_presence_enrichment_no_event(api):
    for _ in range(2):
        run = run_cycle()
        assert run["success"] == 1, f"cycle failed: {run}"

    states = {r["aircraft_hex"]: r for r in db_rows("SELECT * FROM aircraft_state")}
    target = states[SESSION["target_hex"]]
    assert target["episode_id"], "target episode should be open after entry"
    assert target["inside_observations"] >= 2
    assert target["missing_cycles"] == 0
    assert target["disappeared_alerted"] == 0

    if SESSION["control_hex"]:
        control = states[SESSION["control_hex"]]
        assert control["episode_id"], "control episode should be open too"
        assert control["airline_classification"] == "scheduled_airline"

    assert db_rows("SELECT * FROM events") == [], "no event may fire from mere presence"

    enrichment = db_rows("SELECT * FROM fr24_enrichment WHERE aircraft_hex=?", (SESSION["target_hex"],))
    assert enrichment, "entry enrichment row missing"
    assert enrichment[0]["status"] in ("ok", "empty")
    assert enrichment[0]["fr24_id"], "enrichment must persist the FR24 id for later track fetches"
    summary_rows = db_rows(
        "SELECT * FROM fr24_request_log WHERE endpoint='flight-summary/full' AND http_outcome='ok'"
    )
    assert summary_rows, "summary-full request not logged"

    SESSION["target_episode"] = target["episode_id"]
    SESSION["target_fr24_id"] = enrichment[0]["fr24_id"]
    if SESSION["control_hex"]:
        control_enrichment = db_rows(
            "SELECT * FROM fr24_enrichment WHERE aircraft_hex=?", (SESSION["control_hex"],)
        )
        SESSION["control_fr24_id"] = control_enrichment[0]["fr24_id"] if control_enrichment else None
        SESSION["control_episode"] = states[SESSION["control_hex"]]["episode_id"]


# ---------------------------------------------------------------------------
# S2 -- DISAPPEARED through the real production path + track fetch
# ---------------------------------------------------------------------------


def test_s2_disappeared_and_track(api):
    # Absence lever: claim the target for a non-FR24 provider with a fresh
    # last_seen. _free_grid_actively_tracking() then defers its FR24
    # observation every cycle (fr24_scheduler.py), the cluster stays
    # successful, and process_missing() advances missing_cycles on the real
    # detection path until the DISAPPEARED gate trips.
    db_write(
        "UPDATE aircraft_state SET last_provider='adsb_lol', last_seen_at=? WHERE aircraft_hex=?",
        (datetime.now(UTC).isoformat(), SESSION["target_hex"]),
    )

    for _ in range(3):
        run = run_cycle()
        assert run["success"] == 1, f"cycle failed: {run}"

    events = db_rows(
        "SELECT * FROM events WHERE event_type='DISAPPEARED' AND aircraft_hex=?",
        (SESSION["target_hex"],),
    )
    assert len(events) == 1, f"expected exactly one DISAPPEARED event, got {len(events)}"
    event = events[0]
    assert event["email_status"] == "review_only", "review phase must mark events review_only"
    assert json.loads(event["details_json"])["episode_id"] == SESSION["target_episode"]

    state = db_rows("SELECT * FROM aircraft_state WHERE aircraft_hex=?", (SESSION["target_hex"],))[0]
    assert state["disappeared_alerted"] == 1
    assert state["missing_cycles"] >= 3

    # Manual track fetch on the event (authenticated, confirmed, audited).
    status = api.get(f"/api/fr24/events/{event['id']}/track")
    assert status.status_code == 200
    assert status.json()["available"] is True, status.json()
    fetched = api.post(f"/api/fr24/events/{event['id']}/track", json={"confirm": True})
    assert fetched.status_code == 200, fetched.text[:300]
    body = fetched.json()
    assert body["fetched"] is True

    track_rows = db_rows("SELECT * FROM fr24_tracks WHERE event_id=?", (event["id"],))
    assert track_rows, "track row not persisted"
    assert track_rows[0]["fr24_id"] == SESSION["target_fr24_id"]
    log_rows = db_rows(
        "SELECT * FROM fr24_request_log WHERE endpoint='flight-tracks' AND http_outcome='ok'"
    )
    assert log_rows, "flight-tracks request not logged"
    assert log_rows[-1]["estimated_credits"] >= 40

    SESSION["disappeared_event_id"] = event["id"]


# ---------------------------------------------------------------------------
# S3 -- synthetic PROBABLE_STOP demo row (not from the live pipeline)
# ---------------------------------------------------------------------------


def test_s3_synthetic_probable_stop(api):
    """The live fixture's groundspeed (~491 kt) exceeds stop_max_speed_kt's
    hard 150 kt ceiling, so no real PROBABLE_STOP can ever fire from sandbox
    data. This row is a clearly-labeled DB insert so the UI demonstrates the
    second event type -- no detection-pipeline claim is made for it."""
    assert SESSION.get("disappeared_event_id"), "S2 must run first"
    state = db_rows("SELECT * FROM aircraft_state WHERE aircraft_hex=?", (SESSION["target_hex"],))[0]
    now_iso = _container(
        "from app.database import utc_now_iso\nprint(utc_now_iso())"
    )[0].strip()
    synthetic = {
        "id": str(uuid.uuid4()),
        "deduplication_key": f"sim-{uuid.uuid4()}:PROBABLE_STOP",
        "event_type": "PROBABLE_STOP",
        "occurred_at": now_iso,
        "aircraft_hex": SESSION["target_hex"],
        "callsign": state["callsign"],
        "registration": state["registration"],
        "aircraft_type": state["aircraft_type"],
        "airline_classification": state["airline_classification"],
        "area_ids_json": json.dumps(["sandbox-sim-target"]),
        "area_names_json": json.dumps(["Sandbox Sim Target Area"]),
        "latitude": state["latitude"],
        "longitude": state["longitude"],
        "altitude_ft": state["altitude_ft"],
        "ground_speed_kt": 0,
        "reason": (
            "SANDBOX SIMULATION -- synthetic row for UI demonstration only; not produced "
            "by the detection pipeline (the live fixture flies above the stop-speed gate)."
        ),
        "confidence": "medium",
        "provider": "sandbox-simulation",
        "phase": "review",
        "email_status": "not_applicable",
        "details_json": json.dumps(
            {
                "episode_id": SESSION["target_episode"],
                # Present so the S6 budget-block check resolves an fr24_id.
                # Deliberately NOT the target's: S2 already stored a track for
                # it, and "already_fetched" outranks the budget block in the
                # track endpoints. The control aircraft was never tracked.
                "fr24_id": SESSION.get("control_fr24_id") or f"sim{uuid.uuid4().hex[:10]}",
                "synthetic": True,
            }
        ),
    }
    code = (
        "import json\n"
        "from app.database import insert_event\n"
        f"print(insert_event({synthetic!r}))\n"
    )
    assert _container(code)[0].strip() == "True", "synthetic event insert rejected"

    listed = api.get("/api/events", params={"limit": 50}).json()["events"]
    matches = [e for e in listed if e["event_type"] == "PROBABLE_STOP" and e["provider"] == "sandbox-simulation"]
    assert matches, "synthetic event not listed by /api/events"
    SESSION["synthetic_event_id"] = matches[0]["id"]

    # Email rendering demo (works in any phase with the console provider):
    # the same template path real events use, logged as EMAIL PREVIEW.
    # Compare against the pre-request log tail so a preview line left by an
    # earlier session in the same container can't satisfy the assert.
    log_before = len(container_logs())
    tested = api.post("/api/email/test")
    assert tested.status_code == 200, tested.text[:200]
    assert tested.json()["status"] == "previewed"
    assert "EMAIL PREVIEW" in container_logs()[log_before:]


# ---------------------------------------------------------------------------
# S4 -- episode close-by-leaving (no event)
# ---------------------------------------------------------------------------


def test_s4_episode_close_by_leaving(api):
    control_hex = SESSION.get("control_hex")
    if not control_hex:
        pytest.skip("no scheduled-aircraft fixture available for the clean-exit scenario")

    # Deselect the control's area directly (the selection API regenerates
    # free-grid query regions -- irrelevant here and lock-prone); the FR24
    # cycle rebuilds GeofenceIndex from the DB every run.
    db_write("UPDATE areas SET selected=0 WHERE id='sandbox-sim-control'")

    for _ in range(2):
        run = run_cycle()
        assert run["success"] == 1, f"cycle failed: {run}"

    state = db_rows("SELECT * FROM aircraft_state WHERE aircraft_hex=?", (control_hex,))[0]
    assert state["episode_id"] is None, "episode must close after outside confirmation"
    control_events = db_rows("SELECT * FROM events WHERE aircraft_hex=?", (control_hex,))
    assert control_events == [], "leaving an area cleanly must produce no event"


# ---------------------------------------------------------------------------
# S5 -- budget warning
# ---------------------------------------------------------------------------


def test_s5_budget_warning(api):
    status = api.get("/api/fr24/status").json()
    used = status["credits_used_this_cycle"]
    assert used > 0, "no credits accumulated -- earlier scenarios did not spend"

    # used/budget = 0.75 lands in "warning" (>= 0.70 per fr24_credits).
    warning_budget = max(1, math.ceil(used / 0.75))
    set_settings(api, {"fr24_monthly_operating_budget": warning_budget})

    run = run_cycle()
    assert run["success"] == 1, "warning state must still poll (only pause_fr24+exhausted skips)"

    status = api.get("/api/fr24/status").json()
    assert status["budget_state"] in ("warning", "critical", "hard_limit"), status["budget_state"]
    # Manual exec cycles log to their own stderr (captured by run_cycle), not
    # the container log stream -- see run_cycle().
    assert "fr24.budget.warning" in SESSION["cycle_logs"], SESSION["cycle_logs"][-500:]
    # Nonessential spend (summary enrichment / usage sync) is suppressed in
    # non-normal states; with no new episodes this cycle there is nothing to
    # enrich anyway -- the log line above is the observable contract.


# ---------------------------------------------------------------------------
# S6 -- budget exhausted + pause_fr24 + restore
# ---------------------------------------------------------------------------


def test_s6_budget_exhausted_pause_and_restore(api):
    status = api.get("/api/fr24/status").json()
    used = status["credits_used_this_cycle"]
    set_settings(api, {"fr24_monthly_operating_budget": used, "fr24_budget_policy": "pause_fr24"})

    light_before = len(db_rows("SELECT * FROM fr24_request_log WHERE endpoint='live/flight-positions/light'"))

    run = run_cycle()
    assert run.get("skipped") == 1, f"exhausted+pause_fr24 must skip the cycle: {run}"
    assert "budget exhausted" in (run.get("error_message") or "")

    light_after = len(db_rows("SELECT * FROM fr24_request_log WHERE endpoint='live/flight-positions/light'"))
    assert light_after == light_before, "a skipped cycle must not spend on light polls"

    status = api.get("/api/fr24/status").json()
    assert status["budget_state"] == "exhausted"
    assert "budget_exhausted_paused" in status["blockers"]

    # Manual track fetch is refused in the paused state: the synthetic event
    # resolves an fr24_id (details.fr24_id) and has no stored track, so the
    # ONLY thing blocking it is the budget.
    synthetic_id = SESSION["synthetic_event_id"]
    preview = api.get(f"/api/fr24/events/{synthetic_id}/track")
    assert preview.status_code == 200
    assert preview.json()["blocked_reason"] == "budget_exhausted_pause_fr24", preview.json()
    refused = api.post(f"/api/fr24/events/{synthetic_id}/track", json={"confirm": True})
    assert refused.status_code == 409
    assert "budget exhausted" in refused.json()["detail"].lower()

    # End state now stands for screenshots (both event types present,
    # exhausted budget visible). Restore unless the wrapper asked us to wait.
    if SKIP_RESTORE:
        print("FR24_SANDBOX_SKIP_RESTORE=1 -- settings left for screenshots; wrapper restores")
        return

    backup = json.loads(SETTINGS_BACKUP.read_text())
    restore = {key: value for key, value in backup.items() if value is not None}
    set_settings(api, restore)
    # Assert the settings round-tripped, not the derived budget state: this
    # billing cycle's cumulative spend can legitimately exceed the restored
    # budget after several runs, which leaves budget_state non-normal without
    # anything having failed (scripts/fr24_sandbox_restore.py says the same).
    settings_now = api.get("/api/settings").json()["settings"]
    for key, value in restore.items():
        assert settings_now[key]["value"] == value, f"{key} not restored: {settings_now[key]}"
