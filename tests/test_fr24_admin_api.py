import json
from datetime import UTC, datetime, timezone

from fastapi.testclient import TestClient
from shapely.geometry import Polygon, mapping

from app.database import record_fr24_request, replace_areas
from app.fr24_credits import billing_cycle_id
from app.settings_store import set_setting


def _authed_client():
    from app.main import app

    client = TestClient(app)
    login = client.post("/api/auth/login", json={"password": "correct-horse-battery-staple"})
    assert login.status_code == 200
    csrf = login.json()["csrf_token"]
    client.headers.update({"X-CSRF-Token": csrf})
    return client


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


def _cluster_payload(**overrides):
    # Defaults include valid manual bounds so an enabled cluster with no
    # member areas still satisfies the "needs areas or manual bounds" rule
    # -- tests that specifically want to exercise the areas-only path
    # override use_manual_bounds=False (and enabled=False, where relevant).
    base = {
        "name": "Test Cluster",
        "enabled": True,
        "buffer_km": 15.0,
        "min_altitude_ft": -2000.0,
        "max_altitude_ft": 10000.0,
        "categories": ["T", "H", "N"],
        "area_ids": [],
        "use_manual_bounds": True,
        "manual_north": -1.0,
        "manual_south": -3.0,
        "manual_west": -56.0,
        "manual_east": -54.0,
    }
    base.update(overrides)
    return base


def test_fr24_clusters_requires_auth():
    from app.main import app

    with TestClient(app) as client:
        response = client.get("/api/fr24/clusters")
        assert response.status_code == 401


def test_fr24_clusters_post_requires_csrf():
    from app.main import app

    with TestClient(app) as client:
        login = client.post("/api/auth/login", json={"password": "correct-horse-battery-staple"})
        assert login.status_code == 200
        # No X-CSRF-Token header set -- session cookie alone must not be enough.
        response = client.post("/api/fr24/clusters", json=_cluster_payload())
        assert response.status_code == 403


def test_fr24_clusters_empty_on_fresh_db():
    client = _authed_client()
    response = client.get("/api/fr24/clusters")
    assert response.status_code == 200
    body = response.json()
    assert body["clusters"] == []
    assert body["overlap_warnings"] == []
    assert body["max_active_clusters"] == 2


def test_fr24_clusters_unknown_category_rejected():
    client = _authed_client()
    response = client.post("/api/fr24/clusters", json=_cluster_payload(categories=["X"]))
    assert response.status_code == 400


def test_fr24_clusters_create_with_manual_bounds_no_areas_succeeds():
    client = _authed_client()
    response = client.post("/api/fr24/clusters", json=_cluster_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["calc_bounds"] is None
    listing = client.get("/api/fr24/clusters").json()
    assert len(listing["clusters"]) == 1
    assert listing["clusters"][0]["name"] == "Test Cluster"


def test_fr24_clusters_listing_includes_coverage_geojson():
    replace_areas([_selected_area_record()], auto_select_all=True)
    client = _authed_client()
    created = client.post("/api/fr24/clusters", json=_cluster_payload(area_ids=["funai:test"]))
    assert created.status_code == 200
    listing = client.get("/api/fr24/clusters").json()
    cluster = listing["clusters"][0]
    fc = cluster["coverage_geojson"]
    assert fc["type"] == "FeatureCollection"
    roles = [f["properties"]["role"] for f in fc["features"]]
    assert "area" in roles
    assert "bounds" in roles


def test_fr24_clusters_coverage_geojson_null_without_bounds():
    client = _authed_client()
    payload = _cluster_payload(enabled=False, use_manual_bounds=False)
    assert client.post("/api/fr24/clusters", json=payload).status_code == 200
    listing = client.get("/api/fr24/clusters").json()
    assert listing["clusters"][0]["coverage_geojson"] is None


def test_fr24_clusters_disabled_without_areas_or_bounds_succeeds():
    # A disabled cluster with neither areas nor manual bounds is fine -- it
    # just isn't polled. Only an ENABLED cluster with neither is rejected.
    client = _authed_client()
    payload = _cluster_payload(enabled=False, use_manual_bounds=False)
    response = client.post("/api/fr24/clusters", json=payload)
    assert response.status_code == 200
    assert response.json()["calc_bounds"] is None


def test_fr24_clusters_enabled_without_areas_or_bounds_rejected():
    client = _authed_client()
    payload = _cluster_payload(enabled=True, use_manual_bounds=False)
    response = client.post("/api/fr24/clusters", json=payload)
    assert response.status_code == 400


def test_fr24_clusters_inverted_altitude_rejected():
    client = _authed_client()
    payload = _cluster_payload(min_altitude_ft=10000.0, max_altitude_ft=-2000.0)
    response = client.post("/api/fr24/clusters", json=payload)
    assert response.status_code == 400


def test_fr24_clusters_invalid_id_format_rejected():
    client = _authed_client()
    payload = _cluster_payload(id="../../etc/passwd")
    response = client.post("/api/fr24/clusters", json=payload)
    assert response.status_code == 400


def test_fr24_clusters_manual_bounds_missing_value_rejected():
    client = _authed_client()
    payload = _cluster_payload(
        use_manual_bounds=True, manual_north=-1, manual_south=-3, manual_west=-56, manual_east=None
    )
    response = client.post("/api/fr24/clusters", json=payload)
    assert response.status_code == 400


def test_fr24_clusters_manual_bounds_invalid_order_rejected():
    client = _authed_client()
    payload = _cluster_payload(
        use_manual_bounds=True, manual_north=-3, manual_south=-1, manual_west=-56, manual_east=-54
    )
    response = client.post("/api/fr24/clusters", json=payload)
    assert response.status_code == 400


def test_fr24_clusters_max_active_enforced():
    client = _authed_client()
    first = client.post("/api/fr24/clusters", json=_cluster_payload(name="c1"))
    assert first.status_code == 200
    second = client.post("/api/fr24/clusters", json=_cluster_payload(name="c2"))
    assert second.status_code == 200
    third = client.post("/api/fr24/clusters", json=_cluster_payload(name="c3"))
    assert third.status_code == 400


def test_fr24_cluster_delete():
    client = _authed_client()
    created = client.post("/api/fr24/clusters", json=_cluster_payload()).json()
    cluster_id = created["id"]
    response = client.delete(f"/api/fr24/clusters/{cluster_id}")
    assert response.status_code == 200
    assert response.json()["deleted"] is True
    missing = client.delete(f"/api/fr24/clusters/{cluster_id}")
    assert missing.status_code == 404


def test_fr24_status_fresh_db():
    client = _authed_client()
    response = client.get("/api/fr24/status")
    assert response.status_code == 200
    body = response.json()
    assert body["budget_state"] == "normal"
    assert body["all_empty_baseline"] == 0


def test_fr24_status_reports_readiness_blockers():
    client = _authed_client()
    body = client.get("/api/fr24/status").json()
    assert body["enabled"] is False
    assert body["enabled_source"] == "default"
    assert body["api_key_configured"] is False
    assert body["api_key_source"] == "default"
    assert body["blockers"] == ["flag_disabled", "missing_api_key", "no_enabled_clusters"]


def test_fr24_status_blockers_clear_as_requirements_met():
    replace_areas([_selected_area_record()], auto_select_all=True)
    client = _authed_client()
    set_setting("flightradar24_api_key", "fr24-test-token")
    set_setting("fr24_enabled", True)
    body = client.get("/api/fr24/status").json()
    assert body["enabled"] is True
    assert body["enabled_source"] == "interface"
    assert body["api_key_configured"] is True
    assert body["blockers"] == ["no_enabled_clusters"]

    created = client.post(
        "/api/fr24/clusters", json=_cluster_payload(area_ids=["funai:test"])
    )
    assert created.status_code == 200
    body = client.get("/api/fr24/status").json()
    assert body["blockers"] == []


def test_fr24_status_reports_budget_pause_blocker():
    replace_areas([_selected_area_record()], auto_select_all=True)
    client = _authed_client()
    set_setting("flightradar24_api_key", "fr24-test-token")
    set_setting("fr24_enabled", True)
    client.post("/api/fr24/clusters", json=_cluster_payload(area_ids=["funai:test"]))
    set_setting("fr24_budget_policy", "pause_fr24")
    set_setting("fr24_monthly_operating_budget", 100)
    bcid = billing_cycle_id(datetime.now(UTC))
    record_fr24_request(bcid, "live/flight-positions/light", "prior", "ok", 100, 200, 100, 0, False)
    body = client.get("/api/fr24/status").json()
    assert body["blockers"] == ["budget_exhausted_paused"]


def test_fr24_test_no_clusters_configured():
    client = _authed_client()
    response = client.post("/api/fr24/test")
    assert response.status_code == 400


def test_fr24_test_with_configured_cluster(monkeypatch):
    replace_areas([_selected_area_record()], auto_select_all=True)
    client = _authed_client()
    created = client.post(
        "/api/fr24/clusters", json=_cluster_payload(area_ids=["funai:test"])
    ).json()
    assert created["calc_bounds"] is not None

    from app.providers.fr24 import LightResult

    captured_kwargs = {}

    async def fake_fetch_light(*args, **kwargs):
        captured_kwargs.update(kwargs)
        return LightResult(observations=[], possibly_truncated=False, raw_count=0, estimated_credits=1)

    monkeypatch.setattr("app.main.fetch_light", fake_fetch_light)
    response = client.post("/api/fr24/test")
    assert response.status_code == 200
    body = response.json()
    assert "aircraft_found" in body
    assert "estimated_credits" in body
    assert captured_kwargs["limit"] == 1


def test_fr24_test_blocked_when_budget_exhausted_under_pause_policy():
    replace_areas([_selected_area_record()], auto_select_all=True)
    client = _authed_client()
    client.post("/api/fr24/clusters", json=_cluster_payload(area_ids=["funai:test"]))

    set_setting("fr24_budget_policy", "pause_fr24")
    set_setting("fr24_monthly_operating_budget", 100)
    bcid = billing_cycle_id(datetime.now(timezone.utc))
    record_fr24_request(bcid, "live/flight-positions/light", "prior", "ok", 100, 200, 100, 0, False)

    response = client.post("/api/fr24/test")
    assert response.status_code == 400
