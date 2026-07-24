import asyncio
import io
import json
import zipfile
from datetime import datetime, timedelta, timezone

import httpx
from fastapi.testclient import TestClient
from shapely.geometry import Polygon, mapping


def observation(**overrides):
    from app.providers.base import AircraftObservation

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
        observed_at=datetime.now(timezone.utc),
        seen_pos_seconds=1,
        region_id="region-test",
        provider="adsb_lol",
    )
    values.update(overrides)
    return AircraftObservation(**values)


def selected_area_record():
    geometry = Polygon(
        [(-55.1, -1.1), (-54.9, -1.1), (-54.9, -0.9), (-55.1, -0.9), (-55.1, -1.1)]
    )
    return {
        "id": "funai:test",
        "source": "FUNAI",
        "external_id": "test",
        "name": "Test Indigenous Territory",
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


def test_readsb_timestamp_milliseconds_and_validation():
    from app.providers.readsb import normalize_readsb

    item = normalize_readsb(
        {"hex": "e49abc", "lat": -1, "lon": -55, "seen_pos": 2, "alt_baro": 1000, "gs": 80},
        1_700_000_000_000,
        "region-1",
        "adsb_lol",
    )
    assert item is not None
    assert item.observed_at.year == 2023
    assert normalize_readsb(
        {"hex": "bad", "lat": 100, "lon": -55, "seen_pos": 2},
        1_700_000_000,
        "region-1",
        "adsb_lol",
    ) is None


def test_fr24_numeric_timestamp_parsing():
    from app.providers.providers import _parse_fr24_timestamp

    seconds = _parse_fr24_timestamp(1_700_000_000)
    milliseconds = _parse_fr24_timestamp(1_700_000_000_000)
    assert seconds is not None and seconds.year == 2023
    assert milliseconds == seconds


def test_airline_and_unknown_classification():
    from app.detection import classify_aircraft

    assert classify_aircraft(observation(callsign="AZU1234"))[0] == "scheduled_airline"
    assert classify_aircraft(observation())[0] == "unknown_candidate"


def test_settings_environment_precedence_and_validation(monkeypatch):
    from app.config import env_settings
    from app.settings_store import get_setting, set_setting

    monkeypatch.setenv("POLL_INTERVAL_SECONDS", "600")
    env_settings.cache_clear()
    assert get_setting("poll_interval_seconds") == 600
    try:
        set_setting("poll_interval_seconds", 300)
        raise AssertionError("environment-controlled setting should be locked")
    except ValueError:
        pass
    monkeypatch.delenv("POLL_INTERVAL_SECONDS")
    env_settings.cache_clear()
    try:
        set_setting("poll_interval_seconds", 5)
        raise AssertionError("invalid interval should fail")
    except ValueError:
        pass


def test_safe_zip_rejects_path_traversal(tmp_path):
    from app.boundary_sync import _safe_extract

    archive_path = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("../escape.txt", "bad")
    try:
        _safe_extract(archive_path, tmp_path / "out")
        raise AssertionError("path traversal should fail")
    except RuntimeError:
        pass


def test_adsbexchange_uses_official_api_auth_header(monkeypatch):
    from app.config import env_settings
    from app.database import replace_query_regions
    from app.providers.providers import _readsb_region
    from app.settings_store import set_setting

    env_settings.cache_clear()
    set_setting("adsbexchange_api_key", "secret-key")
    replace_query_regions(
        [{
            "id": "r1", "name": "r1", "latitude": -1, "longitude": -55,
            "radius_nm": 10, "north": 0, "south": -2, "west": -56, "east": -54,
        }]
    )
    seen = {}

    async def handler(request):
        seen.update(request.headers)
        return httpx.Response(200, json={"now": 1_700_000_000_000, "ac": []})

    transport = httpx.MockTransport(handler)

    async def run():
        async with httpx.AsyncClient(transport=transport) as client:
            await _readsb_region(client, "adsbexchange", {
                "id": "r1", "latitude": -1, "longitude": -55, "radius_nm": 10
            })

    asyncio.run(run())
    assert seen.get("api-auth") == "secret-key"
    assert "x-api-key" not in seen


def test_stop_timer_does_not_include_high_speed_observation(monkeypatch):
    from app.database import get_state, replace_areas
    from app.detection import process_observation
    from app.geofences import GeofenceIndex
    from app.settings_store import set_setting

    replace_areas([selected_area_record()], True)
    set_setting("min_inside_observations_for_stop", 2)
    set_setting("stop_min_duration_seconds", 30)
    set_setting("stop_max_speed_kt", 20)
    index = GeofenceIndex()
    base_time = datetime.now(timezone.utc)

    asyncio.run(process_observation(observation(observed_at=base_time, ground_speed_kt=90), index, "shadow"))
    asyncio.run(process_observation(observation(observed_at=base_time + timedelta(seconds=40), ground_speed_kt=10), index, "shadow"))
    state = get_state("e49abc")
    assert state is not None
    assert state["stop_alerted"] == 0
    assert state["stationary_since"] == (base_time + timedelta(seconds=40)).isoformat()


def test_outside_requires_confirmation_before_closing_episode():
    from app.database import get_state, replace_areas
    from app.detection import process_observation
    from app.geofences import GeofenceIndex
    from app.settings_store import set_setting

    replace_areas([selected_area_record()], True)
    set_setting("outside_confirmation_observations", 2)
    index = GeofenceIndex()
    base_time = datetime.now(timezone.utc)
    asyncio.run(process_observation(observation(observed_at=base_time), index, "shadow"))
    outside = observation(latitude=-2, longitude=-55, observed_at=base_time + timedelta(seconds=60))
    asyncio.run(process_observation(outside, index, "shadow"))
    state = get_state("e49abc")
    assert state and state["episode_id"] and state["outside_observations"] == 1
    outside.observed_at = base_time + timedelta(seconds=120)
    asyncio.run(process_observation(outside, index, "shadow"))
    state = get_state("e49abc")
    assert state and state["episode_id"] is None


def test_api_authentication_csrf_and_security_headers():
    from app.main import app

    with TestClient(app) as client:
        unauthenticated = client.get("/api/status")
        assert unauthenticated.status_code == 401
        login = client.post("/api/auth/login", json={"password": "correct-horse-battery-staple"})
        assert login.status_code == 200
        csrf = login.json()["csrf_token"]
        blocked = client.post("/api/poll")
        assert blocked.status_code == 403
        allowed = client.post("/api/poll", headers={"X-CSRF-Token": csrf})
        assert allowed.status_code == 200
        response = client.get("/")
        assert response.headers["x-frame-options"] == "DENY"
        assert "default-src 'self'" in response.headers["content-security-policy"]


def test_interface_secret_is_encrypted_and_redacted(monkeypatch):
    from app.config import env_settings
    from app.database import get_db_setting
    from app.settings_store import public_settings, set_setting

    # Clear env var and cache to allow interface setting
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    env_settings.cache_clear()

    # Use a setting that isn't controlled by env
    secret = "test-secret-value-not-plaintext"
    set_setting("smtp_password", secret)
    encrypted = get_db_setting("smtp_password")
    assert encrypted is not None
    assert secret not in encrypted
    public = public_settings()["smtp_password"]
    assert public["value"] is None
    assert public["configured"] is True
    assert public["source"] == "interface"


def test_cross_process_job_lock_is_non_reentrant():
    from app.locks import exclusive_job_lock

    with exclusive_job_lock("test-job") as first:
        assert first is True
        with exclusive_job_lock("test-job") as second:
            assert second is False


def test_fallback_boundary_ids_do_not_collide_for_different_polygons():
    from app.boundary_sync import _stable_id

    first = Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)])
    second = Polygon([(2, 2), (3, 2), (3, 3), (2, 3), (2, 2)])
    first_id = _stable_id("FUNAI", None, "Repeated name", "PA", first)
    second_id = _stable_id("FUNAI", None, "Repeated name", "PA", second)
    assert first_id != second_id


def test_query_region_ids_are_deterministic():
    from app.coverage import regenerate_query_regions
    from app.database import replace_areas

    replace_areas([selected_area_record()], True)
    first = regenerate_query_regions()
    second = regenerate_query_regions()
    assert first
    assert [item["id"] for item in first] == [item["id"] for item in second]


def test_invalid_selection_change_is_rolled_back(monkeypatch):
    from app.database import replace_areas, selected_area_ids
    from app.main import app

    first = selected_area_record()
    second = dict(first)
    second["id"] = "funai:test-2"
    second["external_id"] = "test-2"
    second["name"] = "Second Test Territory"
    replace_areas([first, second], True)
    before = selected_area_ids()

    calls = 0

    def regenerate_once_then_succeed():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("selection requires too many regions")
        return []

    monkeypatch.setattr("app.main.regenerate_query_regions", regenerate_once_then_succeed)
    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login",
            json={"password": "correct-horse-battery-staple"},
        )
        csrf = login.json()["csrf_token"]
        response = client.post(
            "/api/areas/selection",
            headers={"X-CSRF-Token": csrf},
            json={"selected": False, "ids": [first["id"]]},
        )
        assert response.status_code == 400
    assert selected_area_ids() == before


def test_boundary_record_builder_filters_states_and_neighboring_units():
    import geopandas as gpd

    from app.boundary_sync import _records_from_frames

    territories = gpd.GeoDataFrame(
        {
            "terrai_cod": [1, 2],
            "terrai_nom": ["PA Territory", "SP Territory"],
            "uf_sigla": ["PA", "SP"],
            "fase_ti": ["Regularizada", "Regularizada"],
        },
        geometry=[
            Polygon([(-55.1, -1.1), (-54.9, -1.1), (-54.9, -0.9), (-55.1, -0.9)]),
            Polygon([(-47.1, -23.1), (-46.9, -23.1), (-46.9, -22.9), (-47.1, -22.9)]),
        ],
        crs="EPSG:4326",
    )
    conservation = gpd.GeoDataFrame(
        {
            "id_uc": [10, 11],
            "nome_uc": ["Neighboring UC", "Far UC"],
            "uf": ["PA", "GO"],
            "situacao": ["Ativa", "Ativa"],
            "categoria": ["Reserva", "Parque"],
        },
        geometry=[
            Polygon([(-54.95, -1.05), (-54.8, -1.05), (-54.8, -0.9), (-54.95, -0.9)]),
            Polygon([(-50.1, -15.1), (-49.9, -15.1), (-49.9, -14.9), (-50.1, -14.9)]),
        ],
        crs="EPSG:4326",
    )
    records = _records_from_frames(
        territories,
        conservation,
        {"updated": "2026-03", "url": "official-test", "name": "test"},
    )
    names = {record["name"] for record in records}
    assert names == {"PA Territory", "Neighboring UC"}
    assert next(record for record in records if record["name"] == "PA Territory")["phase"] == "Regularizada"


def test_runtime_security_rejects_weak_or_public_insecure_configuration(monkeypatch):
    from app.config import env_settings

    monkeypatch.setenv("ADMIN_PASSWORD", "short")
    monkeypatch.setenv("APP_SECRET_KEY", "x" * 64)
    env_settings.cache_clear()
    try:
        env_settings().validate_runtime_security()
        raise AssertionError("weak password should be rejected")
    except RuntimeError:
        pass

    monkeypatch.setenv("ADMIN_PASSWORD", "strong-enough-password")
    monkeypatch.setenv("BIND_ADDRESS", "0.0.0.0")
    monkeypatch.setenv("SESSION_HTTPS_ONLY", "false")
    env_settings.cache_clear()
    try:
        env_settings().validate_runtime_security()
        raise AssertionError("public insecure cookie configuration should be rejected")
    except RuntimeError:
        pass


def test_boolean_interface_setting_round_trip():
    from app.settings_store import get_setting, set_setting

    set_setting("smtp_starttls", False)
    assert get_setting("smtp_starttls") is False
    set_setting("smtp_starttls", "true")
    assert get_setting("smtp_starttls") is True


def test_provider_http_attempts_are_counted_across_retries(monkeypatch):
    from app.database import provider_requests_today
    from app.providers.providers import _get_json

    calls = 0

    async def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(500, json={"error": "temporary"})
        return httpx.Response(200, json={"ok": True})

    monkeypatch.setattr("app.providers.providers._retry_delay", lambda response, attempt: 0)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await _get_json(client, "https://provider.test", provider="adsb_lol")

    assert asyncio.run(run()) == {"ok": True}
    assert calls == 2
    assert provider_requests_today("adsb_lol") == 2


def test_config_has_new_source_urls():
    from app.config import EnvSettings

    fields = EnvSettings.model_fields
    assert "funai_user_agent" in fields
    assert "icmbio_wfs_url" in fields
    assert "icmbio_wfs_typename" in fields
    assert "raisg_anps_url" in fields


def test_download_icmbio_converts_geojson_to_geodataframe(tmp_path):
    import geopandas as gpd

    from app.boundary_sync import _download_icmbio
    from app.config import env_settings

    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "MultiPolygon",
                    "coordinates": [
                        [[[-55.1, -1.1], [-54.9, -1.1], [-54.9, -0.9], [-55.1, -0.9], [-55.1, -1.1]]]
                    ],
                },
                "properties": {
                    "nomeuc": "Test UC",
                    "cnuc": "0000.00.0001",
                    "uf": "PA",
                    "categoria_": "Parque Nacional",
                },
            }
        ],
    }

    def handler(request):
        return httpx.Response(200, json=geojson)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    cfg = env_settings()

    result = _download_icmbio(client, tmp_path, cfg)
    assert result is not None
    assert isinstance(result, gpd.GeoDataFrame)
    assert len(result) == 1
    assert result.iloc[0]["nomeuc"] == "Test UC"
    assert result.geometry.geom_type.iloc[0] == "MultiPolygon"


def test_download_raisg_anps_converts_arcgis_json(tmp_path):
    import geopandas as gpd

    from app.boundary_sync import _download_raisg_anps
    from app.config import env_settings

    arcgis_json = {
        "features": [
            {
                "attributes": {
                    "nombre": "Test Protected Area",
                    "categoria": "Floresta Nacional",
                    "pais": "Brasil",
                    "fuente": "ISA,2025",
                },
                "geometry": {
                    "rings": [
                        [[-55.1, -1.1], [-54.9, -1.1], [-54.9, -0.9], [-55.1, -0.9], [-55.1, -1.1]]
                    ]
                },
            }
        ]
    }

    def handler(request):
        return httpx.Response(200, json=arcgis_json)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    cfg = env_settings()

    result = _download_raisg_anps(client, tmp_path, cfg)
    assert result is not None
    assert isinstance(result, gpd.GeoDataFrame)
    assert len(result) == 1
    assert result.iloc[0]["nombre"] == "Test Protected Area"
    assert result.geometry.geom_type.iloc[0] == "Polygon"


def test_download_funai_uses_custom_user_agent(tmp_path, monkeypatch):
    from app.boundary_sync import _download_funai
    from app.config import env_settings

    captured_headers = {}

    def mock_download(client, url, destination, params=None):
        # Capture the client's headers to verify User-Agent
        captured_headers.update(dict(client.headers))
        # Create a valid ZIP file
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("tis_poligonais.shp", b"\x00" * 500)
            zf.writestr("tis_poligonais.shx", b"\x00" * 500)
            zf.writestr("tis_poligonais.dbf", b"\x00" * 500)
        destination.write_bytes(buf.getvalue())

    monkeypatch.setattr("app.boundary_sync._download", mock_download)

    def handler(request):
        return httpx.Response(200)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    cfg = env_settings()

    result = _download_funai(client, tmp_path, cfg)
    assert result is not None
    assert result.exists()
    assert "mozilla" in captured_headers.get("user-agent", "").lower()


def test_fallback_chain_uses_icmbio_when_available(tmp_path):
    import geopandas as gpd

    from app.boundary_sync import _download_icmbio
    from app.config import env_settings

    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "MultiPolygon",
                    "coordinates": [
                        [[[-55.1, -1.1], [-54.9, -1.1], [-54.9, -0.9], [-55.1, -0.9], [-55.1, -1.1]]]
                    ],
                },
                "properties": {"nomeuc": "ICMBio UC", "cnuc": "0000.00.0001", "uf": "PA"},
            }
        ],
    }

    def handler(request):
        return httpx.Response(200, json=geojson)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    cfg = env_settings()

    result = _download_icmbio(client, tmp_path, cfg)
    assert result is not None
    assert len(result) == 1
    assert result.iloc[0]["nomeuc"] == "ICMBio UC"


def test_nonmonotonic_observation_is_rejected():
    from app.database import get_state, replace_areas
    from app.detection import process_observation
    from app.geofences import GeofenceIndex

    replace_areas([selected_area_record()], True)
    index = GeofenceIndex()
    base_time = datetime(2026, 7, 24, 12, 0, 0, tzinfo=timezone.utc)

    first = observation(observed_at=base_time)
    result1 = asyncio.run(process_observation(first, index, "shadow"))
    state = get_state("e49abc")
    assert state is not None
    assert state["episode_id"] is not None

    older = observation(observed_at=base_time - timedelta(seconds=60))
    result2 = asyncio.run(process_observation(older, index, "shadow"))
    assert result2 == 0
    state_after = get_state("e49abc")
    assert state_after is not None
    assert state_after["episode_id"] == state["episode_id"]


def test_disappearance_event_created_on_missing_polls():
    from app.database import (
        get_state,
        insert_event,
        list_events,
        replace_areas,
        upsert_state,
    )
    from app.detection import process_missing
    from app.settings_store import set_setting

    replace_areas([selected_area_record()], True)
    set_setting("min_inside_observations_for_disappearance", 2)
    set_setting("disappear_after_successful_polls", 1)

    base_time = datetime(2026, 7, 24, 12, 0, 0, tzinfo=timezone.utc)
    upsert_state(
        {
            "aircraft_hex": "e49abc",
            "callsign": None,
            "registration": None,
            "aircraft_type": None,
            "airline_classification": "unknown_candidate",
            "classification_reason": "test",
            "last_seen_at": base_time.isoformat(),
            "last_provider": "adsb_lol",
            "last_region_id": "region-test",
            "latitude": -1.0,
            "longitude": -55.0,
            "altitude_ft": 2000,
            "ground_speed_kt": 50,
            "area_ids_json": json.dumps(["funai:test"]),
            "area_names_json": json.dumps(["Test Indigenous Territory"]),
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

    events = asyncio.run(
        process_missing(successful_regions={"region-test"}, observed_hexes=set(), phase="shadow")
    )
    assert events == 1
    disappeared = list_events(event_type="DISAPPEARED")
    assert len(disappeared) == 1
    assert disappeared[0]["aircraft_hex"] == "e49abc"


def test_provider_failure_does_not_trigger_disappearance():
    from app.database import (
        list_events,
        replace_areas,
        upsert_state,
    )
    from app.detection import process_missing
    from app.settings_store import set_setting

    replace_areas([selected_area_record()], True)
    set_setting("min_inside_observations_for_disappearance", 2)
    set_setting("disappear_after_successful_polls", 1)

    base_time = datetime(2026, 7, 24, 12, 0, 0, tzinfo=timezone.utc)
    upsert_state(
        {
            "aircraft_hex": "e49abc",
            "callsign": None,
            "registration": None,
            "aircraft_type": None,
            "airline_classification": "unknown_candidate",
            "classification_reason": "test",
            "last_seen_at": base_time.isoformat(),
            "last_provider": "adsb_lol",
            "last_region_id": "region-test",
            "latitude": -1.0,
            "longitude": -55.0,
            "altitude_ft": 2000,
            "ground_speed_kt": 50,
            "area_ids_json": json.dumps(["funai:test"]),
            "area_names_json": json.dumps(["Test Indigenous Territory"]),
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

    events = asyncio.run(
        process_missing(successful_regions=set(), observed_hexes=set(), phase="shadow")
    )
    assert events == 0
    assert len(list_events(event_type="DISAPPEARED")) == 0


def test_episode_deduplication_prevents_duplicate_events():
    from app.database import insert_event

    event = {
        "id": "test-event-1",
        "deduplication_key": "e49abc-20260724T120000:DISAPPEARED",
        "event_type": "DISAPPEARED",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "aircraft_hex": "e49abc",
        "callsign": None,
        "registration": None,
        "aircraft_type": None,
        "airline_classification": "unknown_candidate",
        "area_ids_json": "[]",
        "area_names_json": "[]",
        "latitude": -1.0,
        "longitude": -55.0,
        "altitude_ft": 2000,
        "ground_speed_kt": 50,
        "reason": "test dedup",
        "confidence": "medium",
        "provider": "adsb_lol",
        "phase": "shadow",
        "email_status": "not_applicable",
        "details_json": "{}",
    }
    assert insert_event(event) is True

    duplicate = dict(event)
    duplicate["id"] = "test-event-2"
    assert insert_event(duplicate) is False


def test_email_retry_backoff_and_exhaustion():
    from app.database import (
        get_event,
        insert_event,
        retryable_email_events,
        update_event_email,
    )

    event = {
        "id": "retry-test-1",
        "deduplication_key": "retry-ep-1:DISAPPEARED",
        "event_type": "DISAPPEARED",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "aircraft_hex": "e49abc",
        "callsign": None,
        "registration": None,
        "aircraft_type": None,
        "airline_classification": "unknown_candidate",
        "area_ids_json": "[]",
        "area_names_json": "[]",
        "latitude": -1.0,
        "longitude": -55.0,
        "altitude_ft": 2000,
        "ground_speed_kt": 50,
        "reason": "test retry",
        "confidence": "medium",
        "provider": "adsb_lol",
        "phase": "live",
        "email_status": "pending",
        "details_json": "{}",
    }
    assert insert_event(event) is True
    assert len(retryable_email_events()) == 1

    update_event_email("retry-test-1", "failed", "smtp timeout")
    state = get_event("retry-test-1")
    assert state["email_attempts"] == 1
    assert state["email_next_attempt_at"] is not None
    assert state["email_error"] == "smtp timeout"

    update_event_email("retry-test-1", "failed", "smtp timeout 2")
    update_event_email("retry-test-1", "failed", "smtp timeout 3")
    update_event_email("retry-test-1", "failed", "smtp timeout 4")
    state = get_event("retry-test-1")
    assert state["email_attempts"] == 4
    assert state["email_next_attempt_at"] is None
    assert len(retryable_email_events()) == 0
