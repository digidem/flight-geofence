"""Live FR24 sandbox system test: black-box pass over the real compose stack.

Exercises the full production path -- scheduler (there is deliberately no
HTTP endpoint that triggers a poll cycle), admin auth + CSRF, cluster
management, the sandbox key injected via environment, request accounting,
retention reporting, and the dashboard -- against the isolated sandbox stack
from docker-compose.sandbox.yml.

Opt-in: skipped unless BOTH FR24_SANDBOX_BASE_URL and FR24_SANDBOX_ADMIN_PASSWORD
are set. scripts/fr24_sandbox_smoke.sh brings the stack up and wires these.
"""

import json
import os
import time

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

# Manual bounds around the documented sandbox fixture coordinates
# (lat 35.34722, lon -7.90277) -- see tests/test_fr24_sandbox_contract.py.
CLUSTER_BOUNDS = {
    "manual_north": 36.0,
    "manual_south": 35.0,
    "manual_west": -9.0,
    "manual_east": -7.0,
}

# FR24_POLL_INTERVAL_SECONDS is clamped to a 300s minimum, so a poll that
# sees the just-created cluster can land up to ~305s after container start.
# Contract tests run first and eat some of that, but budget a full interval.
POLL_TIMEOUT_SECONDS = 360
POLL_POLL_SECONDS = 5


@pytest.fixture
def api():
    client = httpx.Client(base_url=BASE_URL, timeout=30, follow_redirects=True)
    login = client.post("/api/auth/login", json={"password": ADMIN_PASSWORD})
    assert login.status_code == 200, f"login failed: {login.status_code} {login.text[:200]}"
    client.headers.update({"X-CSRF-Token": login.json()["csrf_token"]})
    yield client
    client.close()


def test_sandbox_stack_end_to_end(api):
    # 1. Health.
    ready = httpx.get(f"{BASE_URL}/readyz", timeout=10)
    assert ready.status_code == 200

    # 2. Status: key present, locked to environment, retention widened.
    status = api.get("/api/fr24/status")
    assert status.status_code == 200
    body = status.json()
    assert body["enabled"] is True, f"FR24_ENABLED not effective: {body}"
    assert body["api_key_configured"] is True
    assert body["api_key_source"] == "environment", "sandbox key must be env-injected and locked"
    assert body["blockers"] == [] or "flag_disabled" not in body["blockers"]
    assert body["retention_state_days"] >= 36500, "STATE_RETENTION_DAYS override not effective"

    # 3. Create a manual-bounds cluster over the static sandbox coordinates.
    cluster_payload = {
        "name": "sandbox-smoke",
        "enabled": True,
        "buffer_km": 15.0,
        "min_altitude_ft": -2000.0,
        "max_altitude_ft": 10000.0,
        "categories": ["T", "H", "N"],
        "area_ids": [],
        "use_manual_bounds": True,
        **CLUSTER_BOUNDS,
    }
    created = api.post("/api/fr24/clusters", json=cluster_payload)
    assert created.status_code == 200, f"cluster save failed: {created.text[:300]}"
    cluster_id = created.json()["id"]
    try:
        # 3.5. A prior, interrupted scenarios run can leave the operating
        # budget exhausted (S6 parks it there deliberately and only restores
        # it on a clean finish), which would fail this suite on leftover
        # state it never created. Clear the override so the server falls back
        # to its own default, and deliberately do NOT put the exhausted value
        # back afterwards: restoring it would just re-break the stack for the
        # next run and for anyone using the leftover UI.
        pre_probe = api.get("/api/fr24/status").json()
        if pre_probe.get("budget_state") != "normal":
            healed = api.post(
                "/api/settings",
                json={"values": {}, "clear": ["fr24_monthly_operating_budget"]},
            )
            assert healed.status_code == 200, f"budget heal failed: {healed.text[:300]}"
            after = api.get("/api/fr24/status").json()
            print(
                f"healed leftover budget: {pre_probe.get('budget_state')!r} -> "
                f"{after.get('budget_state')!r} (budget now {after.get('operating_budget')})"
            )
            assert after.get("budget_state") == "normal", (
                "clearing the budget override did not restore a spendable budget: "
                f"used={after.get('credits_used_this_cycle')} "
                f"budget={after.get('operating_budget')}"
            )

        # 4. Manual probe endpoint (same fetch_light path, limit=1).
        probe = api.post("/api/fr24/test")
        assert probe.status_code == 200, f"fr24/test failed: {probe.text[:300]}"

        # 5. Ride the real scheduler: wait for a completed, successful poll.
        deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
        latest = None
        while time.monotonic() < deadline:
            latest = api.get("/api/fr24/status").json().get("latest_poll")
            if latest and latest.get("completed_at") and latest.get("started_at"):
                # A row left over from before the cluster existed also has
                # completed_at set; require it to have seen this cluster.
                clusters_json = latest.get("clusters_json") or "[]"
                if cluster_id in json.dumps(json.loads(clusters_json)):
                    break
            time.sleep(POLL_POLL_SECONDS)
        assert latest, "no fr24_poll_runs row appeared before timeout"
        assert latest["success"] == 1, f"poll not successful: {latest}"
        assert latest["clusters_successful"] >= 1
        assert latest["aircraft_returned"] >= 1, f"static row not returned: {latest}"
        assert not latest.get("error_message")

        # 6. Dashboard renders for an authenticated session.
        dash = api.get("/")
        assert dash.status_code == 200
    finally:
        # 7. Cleanup so repeated smoke runs start from a known state.
        api.delete(f"/api/fr24/clusters/{cluster_id}")
