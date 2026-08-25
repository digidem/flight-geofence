"""TRACKS-MANUAL lane (roadmap §6.2): manual authenticated FR24 track fetch.

Every provider interaction is served by httpx.MockTransport injected into
app.main's AsyncClient -- no live network is ever touched (AGENTS.md policy).
New database accessors (save_fr24_track / get_fr24_track_by_event), the
exposed conftest wipe callable, and the routes themselves are imported or
exercised lazily so this file reads red-first against the unimplemented tree.
"""

import json
import threading
import uuid
from datetime import UTC, datetime

import conftest
import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import EnvSettings
from app.database import (
    db,
    insert_event,
    record_fr24_request,
    save_fr24_enrichment,
)
from app.fr24_credits import billing_cycle_id, estimate_track_credits
from app.settings_store import SETTING_DEFS, public_settings, set_setting

ADMIN_PASSWORD = "correct-horse-battery-staple"


def _track_url(event_id: str) -> str:
    return f"/api/fr24/events/{event_id}/track"


def _authed_client():
    from app.main import app

    client = TestClient(app)
    login = client.post("/api/auth/login", json={"password": ADMIN_PASSWORD})
    assert login.status_code == 200
    client.headers.update({"X-CSRF-Token": login.json()["csrf_token"]})
    return client


def _unauthed_client():
    from app.main import app

    return TestClient(app)


_seed_counter = {"n": 0}


def _seed_event(
    *,
    event_id: str | None = None,
    aircraft_hex: str = "ABC123",
    details: dict | None = None,
) -> str:
    _seed_counter["n"] += 1
    event_id = event_id or f"ev-{uuid.uuid4().hex[:12]}"
    event = {
        "id": event_id,
        "deduplication_key": f"dedup-{_seed_counter['n']}-{uuid.uuid4().hex[:8]}",
        "event_type": "PROBABLE_STOP",
        "occurred_at": "2026-08-25T12:00:00+00:00",
        "aircraft_hex": aircraft_hex,
        "area_ids_json": "[]",
        "area_names_json": "[]",
        "reason": "unit-test",
        "confidence": "high",
        "provider": "flightradar24",
        "phase": "shadow",
        "details_json": json.dumps(details if details is not None else {"episode_id": "ep-1"}),
    }
    assert insert_event(event)
    return event_id


def _seed_fr24_id(
    aircraft_hex: str = "ABC123",
    episode_id: str = "ep-1",
    fr24_id: str = "fr24-test-1",
) -> str:
    save_fr24_enrichment(aircraft_hex, episode_id, fr24_id, "ok", {"summary": {}})
    return fr24_id


def _track_payload(rows: int = 2) -> dict:
    return {
        "data": [
            {
                "lat": -1.5 - i * 0.01,
                "lon": -55.5 - i * 0.01,
                "ts": 1756000000 + i,
                "fr24_id": "fr24-test-1",
            }
            for i in range(rows)
        ]
    }


def _install_transport(monkeypatch, handler) -> dict:
    # Provider traffic needs a staged credential (fetch_track -> _headers()).
    set_setting("flightradar24_api_key", "test-token")
    calls = {"count": 0}
    real_async_client = httpx.AsyncClient

    def counting_handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return handler(request)

    def fake_async_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(counting_handler)
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr("app.main.httpx.AsyncClient", fake_async_client)
    # Retry backoff sleeps real seconds -- collapse them; retry COUNTS are
    # asserted via fr24_request_log.retry_count instead.
    monkeypatch.setattr("app.providers.fr24._retry_delay", lambda *a, **k: 0.0)
    return calls


def _ok_track_handler(request: httpx.Request) -> httpx.Response:
    assert request.method == "GET"
    assert request.url.path == "/api/flight-tracks"
    assert request.url.params["flight_id"] == "fr24-test-1"
    body = json.dumps(_track_payload()).encode()
    return httpx.Response(200, content=body, headers={"content-type": "application/json"})


def _exhaust_budget(credits: int = 100000) -> None:
    bcid = billing_cycle_id(datetime.now(UTC))
    record_fr24_request(bcid, "flight-summary/full", None, "ok", 10, credits, None, 0, False)


def _stage_budget(exhausted: bool, policy: str | None = None) -> None:
    if policy is not None:
        set_setting("fr24_budget_policy", policy)
    set_setting("fr24_monthly_operating_budget", 50000)
    if exhausted:
        _exhaust_budget()


def _forbid_detection(monkeypatch) -> None:
    def _boom(*args, **kwargs):
        raise AssertionError("detection machinery invoked during track flow")

    monkeypatch.setattr("app.main.process_observation", _boom)
    monkeypatch.setattr("app.main.process_missing", _boom)


def _track_rows() -> list[dict]:
    with db() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM fr24_tracks").fetchall()]


def _audit_rows(event_id: str) -> list[dict]:
    with db() as conn:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM config_audit_log WHERE key=?", (f"fr24_track:{event_id}",)
            ).fetchall()
        ]


def _log_rows(endpoint: str = "flight-tracks", outcome: str | None = None) -> list[dict]:
    with db() as conn:
        rows = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM fr24_request_log WHERE endpoint=?", (endpoint,)
            ).fetchall()
        ]
    if outcome is not None:
        rows = [r for r in rows if r["http_outcome"] == outcome]
    return rows


# --- 1. auth -----------------------------------------------------------------


def test_post_requires_auth(monkeypatch):
    _install_transport(monkeypatch, _ok_track_handler)
    event_id = _seed_event()
    _seed_fr24_id()

    anon = _unauthed_client()
    assert anon.get(_track_url(event_id)).status_code == 401
    # Accepted-deviation-4: CsrfMiddleware runs BEFORE require_auth for every
    # state-changing /api method (middleware stack order in app/main.py), so an
    # anonymous POST without a session token is 403 "Invalid CSRF token" and
    # never reaches the route's require_auth. Restructuring that ordering is
    # out of lane scope (it would change security layering app-wide); the
    # endpoint stays unreachable anonymously either way, and the GET line
    # above pins the 401 require_auth contract.
    assert anon.post(_track_url(event_id), json={"confirm": True}).status_code == 403

    # Session cookie alone is not enough: CSRF middleware must 403.
    from app.main import app

    no_csrf = TestClient(app)
    login = no_csrf.post("/api/auth/login", json={"password": ADMIN_PASSWORD})
    assert login.status_code == 200
    response = no_csrf.post(_track_url(event_id), json={"confirm": True})
    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid CSRF token"


# --- 2. confirmation ---------------------------------------------------------


def test_post_requires_confirmation(monkeypatch):
    calls = _install_transport(monkeypatch, _ok_track_handler)
    event_id = _seed_event()
    _seed_fr24_id()
    client = _authed_client()

    missing = client.post(_track_url(event_id), json={})
    assert missing.status_code == 400
    assert missing.json()["detail"] == "Track fetch requires confirm=true"

    false_confirm = client.post(_track_url(event_id), json={"confirm": False})
    assert false_confirm.status_code == 400
    assert false_confirm.json()["detail"] == "Track fetch requires confirm=true"

    # B1: strict boolean only -- truthy strings/ints must NOT coerce to confirm.
    string_confirm = client.post(_track_url(event_id), json={"confirm": "true"})
    assert string_confirm.status_code == 422

    int_confirm = client.post(_track_url(event_id), json={"confirm": 1})
    assert int_confirm.status_code == 422

    malformed = client.post(_track_url(event_id), json="not-an-object")
    assert malformed.status_code == 422

    assert calls["count"] == 0


# --- 3. missing fr24 id ------------------------------------------------------


def test_event_without_fr24_id_refused_409(monkeypatch):
    calls = _install_transport(monkeypatch, _ok_track_handler)
    event_id = _seed_event(details={"episode_id": "ep-orphan"})  # no enrichment row
    client = _authed_client()

    response = client.post(_track_url(event_id), json={"confirm": True})
    assert response.status_code == 409
    assert response.json()["detail"] == "missing_fr24_id"
    assert calls["count"] == 0

    status = client.get(_track_url(event_id))
    assert status.status_code == 200
    body = status.json()
    assert body["available"] is False
    assert body["fr24_id"] is None
    assert body["already_fetched"] is False
    assert body["blocked_reason"] == "missing_fr24_id"


def test_unknown_event_404_no_provider_call(monkeypatch):
    calls = _install_transport(monkeypatch, _ok_track_handler)
    client = _authed_client()

    assert client.get(_track_url("ev-missing")).status_code == 404
    response = client.post(_track_url("ev-missing"), json={"confirm": True})
    assert response.status_code == 404
    assert response.json()["detail"] == "Event not found"
    assert calls["count"] == 0
    assert _track_rows() == []


# --- 4. happy path -----------------------------------------------------------


def test_successful_fetch_persists_and_audits(monkeypatch):
    calls = _install_transport(monkeypatch, _ok_track_handler)
    _forbid_detection(monkeypatch)
    _stage_budget(exhausted=True, policy="warn_only")  # warn_only allows manual spend
    event_id = _seed_event()
    fr24_id = _seed_fr24_id()
    client = _authed_client()

    response = client.post(_track_url(event_id), json={"confirm": True})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["fetched"] is True
    assert body["event_id"] == event_id
    assert body["fr24_id"] == fr24_id
    assert body["records_returned"] == 2
    assert body["estimated_credits"] == estimate_track_credits(2) == 80
    assert body["created_at"]

    rows = _track_rows()
    assert len(rows) == 1
    row = rows[0]
    assert row["event_id"] == event_id
    assert row["fr24_id"] == fr24_id
    assert row["aircraft_hex"] == "ABC123"
    assert row["requested_by"] == "authenticated_admin"
    assert row["estimated_credits"] == 80
    assert json.loads(row["payload_json"]) == _track_payload()

    audit = _audit_rows(event_id)
    assert len(audit) == 1
    assert audit[0]["old_value"] is None
    assert audit[0]["new_value"] == fr24_id
    assert audit[0]["changed_by"] == "authenticated_admin"

    ok_log = _log_rows(outcome="ok")
    assert len(ok_log) == 1
    assert ok_log[0]["estimated_credits"] == 80
    assert ok_log[0]["records_returned"] == 2

    assert calls["count"] == 1

    status = client.get(_track_url(event_id))
    assert status.status_code == 200
    status_body = status.json()
    assert status_body["already_fetched"] is True
    assert status_body["blocked_reason"] == "already_fetched"


# --- 5. duplicates -----------------------------------------------------------


def test_duplicate_fetch_blocked_single_spend(monkeypatch):
    calls = _install_transport(monkeypatch, _ok_track_handler)
    event_id = _seed_event()
    _seed_fr24_id()
    client = _authed_client()

    first = client.post(_track_url(event_id), json={"confirm": True})
    assert first.status_code == 200
    second = client.post(_track_url(event_id), json={"confirm": True})
    assert second.status_code == 409
    assert second.json()["detail"] == "already_fetched"
    assert calls["count"] == 1
    assert len(_log_rows()) == 1

    # Cross-event duplicate spend on the same fr24_id must also be refused.
    other_event = _seed_event(details={"episode_id": "ep-1"})  # same enrichment id
    cross = client.post(_track_url(other_event), json={"confirm": True})
    assert cross.status_code == 409
    assert cross.json()["detail"] == "already_fetched"
    assert calls["count"] == 1


def test_concurrent_fetch_single_spend(monkeypatch):
    calls = _install_transport(monkeypatch, _ok_track_handler)
    event_id = _seed_event()
    _seed_fr24_id()

    barrier = threading.Barrier(2)
    results: dict[int, httpx.Response] = {}

    def worker(index: int):
        client = _authed_client()
        barrier.wait()
        results[index] = client.post(_track_url(event_id), json={"confirm": True})

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    statuses = sorted(results[i].status_code for i in results)
    assert statuses == [200, 409]
    assert len(_track_rows()) == 1
    assert calls["count"] == 1
    assert len(_log_rows()) == 1


def test_active_same_id_request_maps_409(monkeypatch):
    import hashlib

    from app.locks import exclusive_job_lock

    _install_transport(monkeypatch, _ok_track_handler)
    event_id = _seed_event()
    fr24_id = _seed_fr24_id()
    lock_name = f"fr24-track-{hashlib.sha256(fr24_id.encode('utf-8')).hexdigest()}"
    client = _authed_client()

    with exclusive_job_lock(lock_name) as acquired:
        assert acquired
        response = client.post(_track_url(event_id), json={"confirm": True})
    assert response.status_code == 409
    assert response.json()["detail"] == "request_in_progress"
    assert _track_rows() == []
    assert _log_rows() == []


# --- 6. provider failures ----------------------------------------------------


@pytest.mark.parametrize(
    ("case", "handler"),
    [
        (
            "timeout",
            lambda request: (_ for _ in ()).throw(httpx.ConnectTimeout("peer closed")),
        ),
        (
            "server-error-exhausted-retries",
            lambda request: httpx.Response(503, content=b"over quota"),
        ),
        (
            "malformed-payload",
            lambda request: httpx.Response(
                200,
                content=json.dumps({"data": "not-a-list"}).encode(),
                headers={"content-type": "application/json"},
            ),
        ),
    ],
    ids=["timeout", "5xx-exhausted", "malformed"],
)
def test_provider_failure_maps_502_no_partial_row(monkeypatch, case, handler):
    calls = _install_transport(monkeypatch, handler)
    event_id = _seed_event()
    _seed_fr24_id()
    client = _authed_client()

    response = client.post(_track_url(event_id), json={"confirm": True})
    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail
    # Query strings (bearing the requested flight id) never leak into errors.
    assert "flight_id=" not in detail

    assert _track_rows() == []  # no partial row
    assert _audit_rows(event_id) == []  # no audit on failure
    failed = _log_rows(outcome="failed")
    assert len(failed) == 1  # exactly one logical failed log row
    if case == "server-error-exhausted-retries":
        assert failed[0]["retry_count"] == 2
    assert calls["count"] > 0


# --- 7. budget pause ---------------------------------------------------------


def test_paused_budget_refuses_manual_track(monkeypatch):
    calls = _install_transport(monkeypatch, _ok_track_handler)
    _stage_budget(exhausted=True, policy=None)  # default policy is pause_fr24
    event_id = _seed_event()
    _seed_fr24_id()
    client = _authed_client()

    response = client.post(_track_url(event_id), json={"confirm": True})
    assert response.status_code == 409
    assert "pause_fr24" in response.json()["detail"]
    assert calls["count"] == 0  # refused before any provider traffic

    status = client.get(_track_url(event_id)).json()
    assert status["available"] is False
    assert status["blocked_reason"] == "budget_exhausted_pause_fr24"
    assert _track_rows() == []


# --- 8. GET status truthfulness ----------------------------------------------


def test_get_status_endpoint_states(monkeypatch):
    _install_transport(monkeypatch, _ok_track_handler)
    client = _authed_client()

    # State 1: available.
    available_id = _seed_event()
    _seed_fr24_id()
    body = client.get(_track_url(available_id)).json()
    assert body == {
        "available": True,
        "event_id": available_id,
        "fr24_id": "fr24-test-1",
        "already_fetched": False,
        "estimated_credits": estimate_track_credits(1),
        "blocked_reason": None,
    }

    # State 2: fetched.
    assert client.post(_track_url(available_id), json={"confirm": True}).status_code == 200
    fetched = client.get(_track_url(available_id)).json()
    assert fetched["already_fetched"] is True
    assert fetched["blocked_reason"] == "already_fetched"

    # State 3: missing fr24 id (detailed assertions live in the 409 test).
    missing_id = _seed_event(details={"episode_id": "ep-none"})
    missing = client.get(_track_url(missing_id)).json()
    assert missing["blocked_reason"] == "missing_fr24_id"

    # State 4: budget paused.
    _stage_budget(exhausted=True, policy=None)
    paused_id = _seed_event()
    _seed_fr24_id(fr24_id="fr24-test-2")
    paused = client.get(_track_url(paused_id)).json()
    assert paused["blocked_reason"] == "budget_exhausted_pause_fr24"


def test_deleted_event_after_status_404_no_orphan(monkeypatch):
    _install_transport(monkeypatch, _ok_track_handler)
    event_id = _seed_event()
    _seed_fr24_id()
    client = _authed_client()

    status = client.get(_track_url(event_id))
    assert status.status_code == 200

    with db() as conn:
        conn.execute("DELETE FROM events WHERE id=?", (event_id,))

    assert client.get(_track_url(event_id)).status_code == 404
    response = client.post(_track_url(event_id), json={"confirm": True})
    assert response.status_code == 404
    assert _track_rows() == []  # FK cascade left no orphan


# --- 9. conftest cleanup coverage --------------------------------------------


def test_clean_database_wipes_fr24_tracks():
    from app.database import save_fr24_track

    event_id = _seed_event()
    assert save_fr24_track(
        event_id=event_id,
        aircraft_hex="ABC123",
        fr24_id="fr24-wipe-1",
        payload={"data": [{"lat": -1.0}]},
        requested_by="authenticated_admin",
        estimated_credits=40,
    )
    assert len(_track_rows()) == 1

    conftest.wipe_database()

    assert _track_rows() == []
    with db() as conn:
        parent = conn.execute("SELECT COUNT(*) FROM events WHERE id=?", (event_id,)).fetchone()[0]
    assert parent == 0  # seeded parent proves the wipe actually ran


# --- 10. legacy setting disposition ------------------------------------------


def test_legacy_auto_track_env_blank_accepted_silently(monkeypatch):
    monkeypatch.setenv("FR24_FETCH_TRACK_ON_EVENT", "")
    EnvSettings()  # must not raise

    monkeypatch.delenv("FR24_FETCH_TRACK_ON_EVENT", raising=False)
    EnvSettings()  # unset is equally silent


def test_legacy_auto_track_env_setting_is_rejected(monkeypatch):
    for value in ("false", "true"):
        monkeypatch.setenv("FR24_FETCH_TRACK_ON_EVENT", value)
        with pytest.raises(ValidationError) as excinfo:
            EnvSettings()
        message = str(excinfo.value)
        assert "FR24_FETCH_TRACK_ON_EVENT" in message
        # Migration guidance must tell the operator what to do instead.
        assert "manual" in message.lower()
        assert ".env" in message.lower()

    # Both declarations are gone: no SETTING_DEFS entry, nothing exposed to
    # the settings API, so the interface cannot resurrect the dead knob.
    assert "fr24_fetch_track_on_event" not in SETTING_DEFS
    assert "fr24_fetch_track_on_event" not in public_settings()


# --- branch coverage: direct details ID, post-lock recheck, integrity loser ---


def test_direct_details_fr24_id_used_before_enrichment(monkeypatch):
    _install_transport(monkeypatch, _ok_track_handler)
    # Event carries the FR24 ID directly in details (no enrichment row) --
    # the first lookup-order branch must resolve and fetch from it alone.
    event_id = _seed_event(details={"episode_id": "ep-direct", "fr24_id": "fr24-test-1"})
    client = _authed_client()

    response = client.post(_track_url(event_id), json={"confirm": True})
    assert response.status_code == 200
    assert response.json()["fr24_id"] == "fr24-test-1"
    assert len(_track_rows()) == 1


def test_post_lock_duplicate_recheck_maps_409(monkeypatch):
    _install_transport(monkeypatch, _ok_track_handler)
    event_id = _seed_event()
    fr24_id = _seed_fr24_id()

    # Simulate a winner inserting between our pre-check and our lock grant:
    # first lookup (pre-check) sees nothing, second (post-lock) sees the row.
    from app import main as app_main

    real_lookup = app_main.get_fr24_track_by_event
    lookups = {"n": 0}

    def racing_lookup(*args, **kwargs):
        lookups["n"] += 1
        if lookups["n"] == 1:
            return None
        return real_lookup(*args, **kwargs)

    winner_event = _seed_event(aircraft_hex="DEF456", details={"episode_id": "ep-winner"})
    with db() as conn:  # stage the "winner" row directly
        conn.execute(
            "INSERT INTO fr24_tracks(id,event_id,aircraft_hex,fr24_id,payload_json,"
            "requested_by,estimated_credits,created_at) VALUES(?,?,?,?,?,?,?,?)",
            ("winner-row", winner_event, "DEF456", fr24_id, "{}", "other", 40, "2026-08-25"),
        )
    monkeypatch.setattr("app.main.get_fr24_track_by_event", racing_lookup)

    client = _authed_client()
    response = client.post(_track_url(event_id), json={"confirm": True})
    assert response.status_code == 409
    assert response.json()["detail"] == "already_fetched"
    assert lookups["n"] >= 2  # pre-check AND post-lock recheck both ran


def test_save_integrity_loser_mapping(monkeypatch):
    _install_transport(monkeypatch, _ok_track_handler)
    event_id = _seed_event()
    _seed_fr24_id()
    monkeypatch.setattr("app.main.save_fr24_track", lambda **kwargs: False)
    client = _authed_client()

    # Integrity loser while the parent event still exists -> duplicate conflict.
    response = client.post(_track_url(event_id), json={"confirm": True})
    assert response.status_code == 409
    assert response.json()["detail"] == "already_fetched"

    # Parent event deleted before the request enters -> plain 404.
    with db() as conn:
        conn.execute("DELETE FROM events WHERE id=?", (event_id,))
    response = client.post(_track_url(event_id), json={"confirm": True})
    assert response.status_code == 404
    assert response.json()["detail"] == "Event not found"
    assert _audit_rows(event_id) == []


def test_save_fr24_track_unique_constraints_enforced():
    from app.database import save_fr24_track

    event_a = _seed_event(details={"episode_id": "ep-a"})
    event_b = _seed_event(aircraft_hex="DEF456", details={"episode_id": "ep-b"})

    assert save_fr24_track(
        event_id=event_a,
        aircraft_hex="ABC123",
        fr24_id="fr24-dup-1",
        payload={"data": []},
        requested_by="authenticated_admin",
        estimated_credits=0,
    )
    # Same flight, second event -> UNIQUE(fr24_id) refuses.
    assert not save_fr24_track(
        event_id=event_b,
        aircraft_hex="DEF456",
        fr24_id="fr24-dup-1",
        payload={"data": []},
        requested_by="authenticated_admin",
        estimated_credits=0,
    )
    # Same event, different flight -> UNIQUE(event_id) refuses.
    assert not save_fr24_track(
        event_id=event_a,
        aircraft_hex="ABC123",
        fr24_id="fr24-dup-2",
        payload={"data": []},
        requested_by="authenticated_admin",
        estimated_credits=0,
    )


def test_save_loser_midflight_deletion_maps_404(monkeypatch):
    # Loser whose parent is deleted WHILE its own fetch is in flight: the
    # post-save recheck must map to 404, leaving no orphan and no audit.
    _install_transport(monkeypatch, _ok_track_handler)
    from app import main as app_main

    real_get_event = app_main.get_event
    lookups = {"n": 0}

    def vanishing_event(lookup_event_id):
        lookups["n"] += 1
        if lookups["n"] == 1:  # route entry: event still present
            return real_get_event(lookup_event_id)
        return None  # gone by the post-save recheck

    midflight_id = _seed_event()
    _seed_fr24_id()
    monkeypatch.setattr("app.main.save_fr24_track", lambda **kwargs: False)
    monkeypatch.setattr("app.main.get_event", vanishing_event)
    client = _authed_client()
    response = client.post(_track_url(midflight_id), json={"confirm": True})
    assert response.status_code == 404
    assert response.json()["detail"] == "Event not found"
    assert lookups["n"] == 2
    assert _track_rows() == []
    assert _audit_rows(midflight_id) == []
