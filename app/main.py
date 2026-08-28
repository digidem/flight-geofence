import asyncio
import calendar
import hashlib
import json
import logging
import secrets
import time
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StrictBool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import fr24_credits
from .auth import check_password, require_auth
from .boundary_sync import sync_boundaries
from .config import env_settings
from .coverage import regenerate_query_regions
from .database import (
    active_states,
    area_counts,
    areas_by_ids,
    bulk_area_selection,
    cleanup_logs,
    cleanup_provider_events,
    cleanup_stale_states,
    credits_used_this_cycle,
    database_ok,
    delete_fr24_cluster,
    event_counts,
    fr24_cluster_area_ids,
    fr24_cluster_missing_area_ids,
    get_event,
    get_fr24_cluster,
    get_fr24_enrichment,
    get_fr24_track_by_event,
    get_query_regions,
    init_db,
    latest_fr24_poll,
    latest_poll,
    latest_sync,
    list_areas,
    list_events,
    list_fr24_clusters,
    query_logs,
    record_config_audit,
    retryable_email_events,
    review_event,
    save_fr24_cluster,
    save_fr24_track,
    save_poll_run,
    selected_area_ids,
    set_area_selection,
    set_fr24_cluster_areas,
    update_event_email,
)
from .detection import classify_aircraft, process_missing, process_observation
from .emailer import send_event_email
from .fr24_clusters import (
    active_cluster_overlaps,
    bounds_of,
    compute_cluster_bounds,
    coverage_geojson,
    geometry_version_hash,
    validate_manual_bounds,
)
from .fr24_scheduler import fr24_polling_loop
from .geofences import GeofenceIndex
from .i18n import get_translations, t
from .locks import exclusive_job_lock
from .providers import PROVIDER_INFO, fetch_all, test_provider
from .providers.fr24 import FR24Failure, fetch_light, fetch_track
from .settings_store import (
    SETTING_DEFS,
    clear_setting,
    get_setting,
    public_settings,
    set_setting,
    setting_source,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

APP_VERSION = "0.5.5"
cfg = env_settings()
poll_lock = asyncio.Lock()
sync_lock = asyncio.Lock()
background_tasks: list[asyncio.Task] = []
login_failures: dict[str, list[float]] = {}


class LoginPayload(BaseModel):
    password: str = Field(min_length=1, max_length=1024)


class SelectionPayload(BaseModel):
    selected: bool
    ids: list[str] = Field(default_factory=list, max_length=5000)
    category: str = ""
    search: str = Field(default="", max_length=200)


class ReviewPayload(BaseModel):
    status: str
    notes: str = Field(default="", max_length=4000)


class SettingsPayload(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)
    clear: list[str] = Field(default_factory=list, max_length=100)


class FR24ClusterPayload(BaseModel):
    id: str | None = None
    name: str = Field(min_length=1, max_length=200)
    enabled: bool = True
    buffer_km: float = Field(ge=1, le=100)
    min_altitude_ft: float = Field(ge=-2000, le=60000)
    max_altitude_ft: float = Field(ge=-2000, le=60000)
    categories: list[str] = Field(default_factory=lambda: ["T", "H", "N"], max_length=12)
    area_ids: list[str] = Field(default_factory=list, max_length=500)
    use_manual_bounds: bool = False
    manual_north: float | None = None
    manual_south: float | None = None
    manual_west: float | None = None
    manual_east: float | None = None


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
            "base-uri 'self'; form-action 'self'"
        )
        if request.url.path.startswith("/api/") or request.url.path == "/":
            response.headers["Cache-Control"] = "no-store"
        return response


class CsrfMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if (
            request.method in {"POST", "PUT", "PATCH", "DELETE"}
            and request.url.path.startswith("/api/")
            and request.url.path != "/api/auth/login"
        ):
            expected = request.session.get("csrf_token")
            supplied = request.headers.get("X-CSRF-Token")
            if not expected or not supplied or not secrets.compare_digest(expected, supplied):
                return JSONResponse(status_code=403, content={"detail": "Invalid CSRF token"})
        return await call_next(request)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _sync_due() -> bool:
    sync = latest_sync()
    if not sync or not sync.get("success") or not sync.get("completed_at"):
        return True
    try:
        completed = datetime.fromisoformat(sync["completed_at"])
    except ValueError:
        return True
    return utc_now() - completed >= timedelta(days=cfg.boundary_sync_interval_days)


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _login_allowed(key: str) -> bool:
    cutoff = time.time() - 15 * 60
    recent = [stamp for stamp in login_failures.get(key, []) if stamp >= cutoff]
    login_failures[key] = recent
    return len(recent) < 8


def _record_login_failure(key: str) -> None:
    login_failures.setdefault(key, []).append(time.time())


def _clear_login_failures(key: str) -> None:
    login_failures.pop(key, None)


async def run_boundary_sync() -> dict:
    lang = str(get_setting("language") or "pt")
    if sync_lock.locked():
        return {"status": "skipped", "reason": t("err_sync_running", lang)}
    async with sync_lock:
        return await sync_boundaries()


async def retry_email_queue() -> int:
    sent_or_updated = 0
    for event in retryable_email_events():
        status, error = await send_event_email(event)
        update_event_email(event["id"], status, error)
        sent_or_updated += 1
    return sent_or_updated


async def run_coverage_cycle() -> dict:
    lang = str(get_setting("language") or "pt")
    if poll_lock.locked():
        return {"status": "skipped", "reason": t("err_poll_running", lang)}
    async with poll_lock:
        with exclusive_job_lock("coverage-poll") as acquired:
            if not acquired:
                return {"status": "skipped", "reason": t("err_poll_running_process", lang)}
            return await _run_coverage_cycle_locked()


async def _run_coverage_cycle_locked() -> dict:
    phase = get_setting("operating_phase")
    providers = [
        provider
        for provider in get_setting("flight_providers")
        if provider in PROVIDER_INFO
    ] or ["adsb_lol"]
    regions = get_query_regions()
    run = {
        "id": str(uuid.uuid4()),
        "started_at": utc_now().isoformat(),
        "completed_at": None,
        "success": 0,
        "phase": phase,
        "providers_json": json.dumps(providers),
        "regions_total": len(regions),
        "requests_successful": 0,
        "aircraft_returned": 0,
        "candidate_aircraft": 0,
        "events_created": 0,
        "error_message": None,
    }
    save_poll_run(run)
    fr24_auto_delete = bool(get_setting("fr24_auto_delete_enabled"))
    cleanup_stale_states(
        cfg.state_retention_days,
        exclude_provider=None if fr24_auto_delete else "flightradar24",
    )
    # Call and observation logs are the operator's audit trail; trim them on the
    # same cadence so the window stays bounded without a separate job.
    cleanup_logs(cfg.log_retention_days)
    if fr24_auto_delete:
        cleanup_provider_events("flightradar24", min(cfg.fr24_retention_days, 29))
    # Retry past live notifications even when no coverage regions currently exist,
    # but respect an operator downgrade to Shadow/Review as an immediate mail pause.
    if phase == "live":
        await retry_email_queue()
    lang = str(get_setting("language") or "pt")
    if not regions:
        run.update(
            {
                "completed_at": utc_now().isoformat(),
                "error_message": t("err_no_regions", lang),
            }
        )
        save_poll_run(run)
        return run

    try:
        observations, successful_regions, errors, requests_successful = await fetch_all()
        index = GeofenceIndex()
        events_created = 0
        candidate_count = 0
        for observation in observations:
            classification, _ = classify_aircraft(observation)
            if classification != "scheduled_airline":
                candidate_count += 1
            events_created += await process_observation(observation, index, phase)
        events_created += await process_missing(
            successful_regions,
            {observation.hex for observation in observations},
            phase,
        )
        run.update(
            {
                "completed_at": utc_now().isoformat(),
                "success": 1 if requests_successful else 0,
                "requests_successful": requests_successful,
                "aircraft_returned": len(observations),
                "candidate_aircraft": candidate_count,
                "events_created": events_created,
                "error_message": "; ".join(errors)[:4000] if errors else None,
            }
        )
    except Exception as exc:
        logger.exception("Coverage cycle failed")
        run.update(
            {
                "completed_at": utc_now().isoformat(),
                "error_message": str(exc)[:4000],
            }
        )
    save_poll_run(run)
    return run


async def boundary_loop() -> None:
    await asyncio.sleep(3)
    while True:
        try:
            if cfg.boundary_sync_enabled and _sync_due():
                await run_boundary_sync()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Boundary scheduler error")
        await asyncio.sleep(max(1, cfg.boundary_sync_check_hours) * 3600)


async def polling_loop() -> None:
    await asyncio.sleep(max(1, cfg.scheduler_initial_delay_seconds))
    while True:
        try:
            await run_coverage_cycle()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Polling scheduler error")
        await asyncio.sleep(max(30, int(get_setting("poll_interval_seconds"))))


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg.validate_runtime_security()
    init_db()
    background_tasks.clear()
    background_tasks.extend(
        [
            asyncio.create_task(boundary_loop()),
            asyncio.create_task(polling_loop()),
            asyncio.create_task(fr24_polling_loop()),
        ]
    )
    yield
    for task in background_tasks:
        task.cancel()
    await asyncio.gather(*background_tasks, return_exceptions=True)
    background_tasks.clear()


app = FastAPI(
    title="Flight Geofence Alerts",
    version=APP_VERSION,
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
# Starlette applies middleware in reverse registration order. Register the
# session middleware after CSRF so request.session exists when CSRF runs.
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CsrfMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=cfg.app_secret_key,
    session_cookie="flight_geofence_session",
    same_site="strict",
    https_only=cfg.session_https_only,
    max_age=60 * 60 * 12,
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=cfg.trusted_host_list or ["*"])
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def index():
    return FileResponse(static_dir / "index.html")


@app.get("/events/{event_id}")
async def event_detail(event_id: str):
    return RedirectResponse(url=f"/#/events/{event_id}", status_code=302)


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "version": APP_VERSION}


@app.get("/readyz")
async def readyz():
    if not database_ok():
        raise HTTPException(status_code=503, detail="Database check failed")
    return {"status": "ready", "version": APP_VERSION}


@app.get("/api/i18n")
async def i18n_endpoint():
    return get_translations()


@app.get("/api/auth/status")
async def auth_status(request: Request):
    authenticated = bool(request.session.get("authenticated"))
    return {
        "authenticated": authenticated,
        "csrf_token": request.session.get("csrf_token") if authenticated else None,
    }


@app.post("/api/auth/login")
async def login(request: Request, payload: LoginPayload):
    key = _client_key(request)
    if not _login_allowed(key):
        raise HTTPException(status_code=429, detail="Too many failed login attempts")
    if not check_password(payload.password):
        _record_login_failure(key)
        await asyncio.sleep(0.35)
        raise HTTPException(status_code=401, detail="Invalid password")
    _clear_login_failures(key)
    request.session.clear()
    request.session["authenticated"] = True
    request.session["csrf_token"] = secrets.token_urlsafe(32)
    return {
        "authenticated": True,
        "csrf_token": request.session["csrf_token"],
    }


@app.post("/api/auth/logout")
async def logout(request: Request):
    request.session.clear()
    return {"authenticated": False}


def _live_readiness_errors() -> list[str]:
    lang = str(get_setting("language") or "pt")
    provider = str(get_setting("email_provider"))
    errors: list[str] = []
    if provider == "console":
        errors.append(t("err_live_need_resend_smtp", lang))
    elif provider == "resend" and not get_setting("resend_api_key"):
        errors.append(t("err_live_need_resend_key", lang))
    elif provider == "smtp" and not all(
        [get_setting("smtp_host"), get_setting("smtp_username"), get_setting("smtp_password")]
    ):
        errors.append(t("err_live_need_smtp", lang))
    if not get_setting("alert_recipients"):
        errors.append(t("err_live_need_recipients", lang))
    return errors


def _warnings(counts: dict, regions: list[dict]) -> list[str]:
    lang = str(get_setting("language") or "pt")
    warnings: list[str] = []
    if counts["total"] == 0:
        warnings.append(t("warn_boundaries_not_synced", lang))
    if counts["selected"] == 0:
        warnings.append(t("warn_no_areas_selected", lang))
    providers = get_setting("flight_providers")
    interval = int(get_setting("poll_interval_seconds"))
    per_provider_daily = int(len(regions) * 86400 / max(interval, 1)) if regions else 0
    if "airplanes_live" in providers and per_provider_daily > 500:
        warnings.append(t("warn_airplanes_limit", lang).replace("{n}", str(per_provider_daily)))
    if get_setting("operating_phase") == "live":
        warnings.extend(_live_readiness_errors())
    effective_stop_minutes = max(
        int(get_setting("stop_min_duration_seconds")) / 60,
        (int(get_setting("min_inside_observations_for_stop")) - 1) * interval / 60,
    )
    warnings.append(
        t("warn_earliest_stop", lang).replace("{n}", f"{effective_stop_minutes:.1f}")
    )
    return warnings


@app.get("/api/status")
async def status(request: Request):
    require_auth(request)
    counts = area_counts()
    regions = get_query_regions()
    providers = get_setting("flight_providers")
    interval = int(get_setting("poll_interval_seconds"))
    estimated_requests = (
        int(len(regions) * len(providers) * 86400 / max(interval, 1)) if regions else 0
    )
    counts_by_event = event_counts()
    return {
        "version": APP_VERSION,
        "phase": get_setting("operating_phase"),
        "areas": counts,
        "query_regions": len(regions),
        "estimated_requests_per_day": estimated_requests,
        "latest_sync": latest_sync(),
        "latest_poll": latest_poll(),
        "active_states": len(active_states()),
        "events": counts_by_event,
        "providers": [
            {"id": provider, **PROVIDER_INFO[provider]}
            for provider in providers
            if provider in PROVIDER_INFO
        ],
        "warnings": _warnings(counts, regions),
    }


@app.get("/api/settings")
async def settings_get(request: Request):
    require_auth(request)
    return {"settings": public_settings(), "provider_options": PROVIDER_INFO}


@app.post("/api/settings")
async def settings_update(request: Request, payload: SettingsPayload):
    require_auth(request)
    errors: dict[str, str] = {}
    updated: list[str] = []
    cleared: list[str] = []
    for key in payload.clear:
        if key not in SETTING_DEFS:
            continue
        try:
            clear_setting(key)
            cleared.append(key)
        except Exception as exc:
            errors[key] = str(exc)
    for key, value in payload.values.items():
        if key not in SETTING_DEFS:
            continue
        if SETTING_DEFS[key].secret and (value is None or str(value).strip() == ""):
            continue
        try:
            set_setting(key, value)
            updated.append(key)
        except Exception as exc:
            errors[key] = str(exc)
    if not errors and get_setting("operating_phase") == "live":
        readiness = _live_readiness_errors()
        if readiness:
            # Roll the phase back to review when it is not locked by the environment.
            try:
                set_setting("operating_phase", "review")
                updated.append("operating_phase")
            except ValueError:
                pass
            errors["operating_phase"] = "; ".join(readiness)
    return {
        "updated": sorted(set(updated)),
        "cleared": cleared,
        "errors": errors,
        "settings": public_settings(),
    }


@app.get("/api/areas")
async def areas_get(
    request: Request,
    search: str = "",
    category: str = "",
    selected: str = "",
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    require_auth(request)
    return list_areas(search, category, selected, limit, offset)


@app.post("/api/areas/selection")
async def areas_selection(request: Request, payload: SelectionPayload):
    require_auth(request)
    lang = str(get_setting("language") or "pt")
    with exclusive_job_lock("boundary-sync") as boundaries_available:
        if not boundaries_available:
            raise HTTPException(status_code=409, detail=t("err_sync_conflict", lang))
        with exclusive_job_lock("coverage-poll") as poll_available:
            if not poll_available:
                raise HTTPException(status_code=409, detail=t("err_poll_conflict", lang))
            previous_selection = selected_area_ids()
            if payload.ids:
                changed = set_area_selection(payload.ids, payload.selected)
            else:
                changed = bulk_area_selection(
                    payload.selected, payload.category, payload.search
                )
            try:
                regions = await asyncio.to_thread(regenerate_query_regions)
            except RuntimeError as exc:
                # Selection and generated regions are one logical configuration change.
                # Restore the previous selection if coverage generation rejects the change.
                bulk_area_selection(False)
                if previous_selection:
                    set_area_selection(previous_selection, True)
                await asyncio.to_thread(regenerate_query_regions)
                raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"changed": changed, "query_regions": len(regions), "counts": area_counts()}


@app.post("/api/boundaries/sync")
async def boundaries_sync(request: Request):
    require_auth(request)
    return await run_boundary_sync()


@app.post("/api/poll")
async def manual_poll(request: Request):
    require_auth(request)
    return await run_coverage_cycle()


@app.post("/api/providers/{provider}/test")
async def provider_test(request: Request, provider: str):
    require_auth(request)
    try:
        return await test_provider(provider)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/email/test")
async def email_test(request: Request):
    require_auth(request)
    lang = str(get_setting("language") or "pt")
    event = {
        "id": str(uuid.uuid4()),
        "event_type": "PROBABLE_STOP",
        "aircraft_hex": "TEST01",
        "callsign": "TEST",
        "registration": None,
        "aircraft_type": None,
        "area_names": [t("err_config_test_area", lang)],
        "occurred_at": utc_now().isoformat(),
        "latitude": 0,
        "longitude": 0,
        "altitude_ft": None,
        "ground_speed_kt": None,
        "provider": "configuration-test",
        "reason": t("err_config_test_reason", lang),
        "airline_classification": "test",
        "details": {},
    }
    status_value, error = await send_event_email(event)
    if status_value == "failed":
        raise HTTPException(status_code=400, detail=error or t("err_email_test_failed", lang))
    return {"status": status_value, "error": error}


@app.get("/api/events")
async def events_get(
    request: Request,
    limit: int = Query(100, ge=1, le=500),
    event_type: str = "",
    review_status: str = "",
):
    require_auth(request)
    return {"events": list_events(limit, event_type, review_status)}


@app.post("/api/events/{event_id}/review")
async def event_review(request: Request, event_id: str, payload: ReviewPayload):
    require_auth(request)
    lang = str(get_setting("language") or "pt")
    if not review_event(event_id, payload.status, payload.notes):
        raise HTTPException(status_code=400, detail=t("err_invalid_review", lang))
    return {"updated": True}


@app.get("/api/fr24/clusters")
async def fr24_clusters_get(request: Request):
    require_auth(request)
    clusters = list_fr24_clusters()
    result = []
    for cluster in clusters:
        item = dict(cluster)
        item["area_ids"] = fr24_cluster_area_ids(cluster["id"])
        item["missing_area_ids"] = fr24_cluster_missing_area_ids(cluster["id"])
        item["categories"] = json.loads(cluster["categories_json"])
        result.append(item)
    # One batched geometry fetch for every member area across all clusters,
    # keyed by id, so the coverage minimap adds exactly one query per panel
    # load regardless of how many clusters exist.
    geometries = {
        row["id"]: row
        for row in areas_by_ids([aid for item in result for aid in item["area_ids"]])
    }
    for item in result:
        item["coverage_geojson"] = coverage_geojson(item, geometries, item["area_ids"])
    return {
        "clusters": result,
        "overlap_warnings": active_cluster_overlaps(clusters),
        "max_active_clusters": cfg.fr24_max_active_clusters,
    }


@app.post("/api/fr24/clusters")
async def fr24_clusters_save(request: Request, payload: FR24ClusterPayload):
    require_auth(request)
    if payload.id is not None:
        try:
            uuid.UUID(payload.id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid cluster id") from exc

    unknown_categories = sorted(set(payload.categories) - fr24_credits.CATEGORY_ENUM)
    if unknown_categories:
        raise HTTPException(status_code=400, detail=f"Unknown categories: {', '.join(unknown_categories)}")
    if not payload.categories:
        raise HTTPException(status_code=400, detail="At least one category is required")
    if payload.min_altitude_ft >= payload.max_altitude_ft:
        raise HTTPException(status_code=400, detail="min_altitude_ft must be less than max_altitude_ft")

    existing = list_fr24_clusters()
    active_count = len([c for c in existing if c.get("enabled") and c["id"] != payload.id])
    if payload.enabled and active_count + 1 > cfg.fr24_max_active_clusters:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {cfg.fr24_max_active_clusters} active clusters allowed",
        )

    if payload.use_manual_bounds:
        bounds_values = (payload.manual_north, payload.manual_south, payload.manual_west, payload.manual_east)
        if None in bounds_values:
            raise HTTPException(status_code=400, detail="Manual bounds require all four values")
        try:
            validate_manual_bounds(*bounds_values)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    areas = areas_by_ids(payload.area_ids) if payload.area_ids else []
    if payload.enabled and not areas and not payload.use_manual_bounds:
        # An enabled cluster with neither member areas nor manual bounds has
        # no bounds to poll at all -- it would occupy one of the (at most 2)
        # active cluster slots, report a nonzero credit baseline as if it
        # were operational, and the scheduler would just error on it every
        # cycle. Reject rather than silently accept a cluster that can never
        # actually monitor anything.
        raise HTTPException(
            status_code=400,
            detail="An enabled cluster needs at least one member area or manual bounds",
        )
    calc_bounds = None
    if areas:
        try:
            calc_bounds = compute_cluster_bounds([a["geometry_json"] for a in areas], payload.buffer_km)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    cluster_id = payload.id or str(uuid.uuid4())
    manual_bounds_tuple = (
        (payload.manual_north, payload.manual_south, payload.manual_west, payload.manual_east)
        if payload.use_manual_bounds
        else None
    )
    version_hash = geometry_version_hash(
        [a["id"] for a in areas],
        [str(a.get("updated_at") or "") for a in areas],
        payload.buffer_km,
        manual_bounds_tuple,
    )

    old_cluster = get_fr24_cluster(cluster_id)
    cluster_record = {
        "id": cluster_id,
        "name": payload.name,
        "enabled": 1 if payload.enabled else 0,
        "buffer_km": payload.buffer_km,
        "min_altitude_ft": payload.min_altitude_ft,
        "max_altitude_ft": payload.max_altitude_ft,
        "categories_json": json.dumps(payload.categories),
        "calc_north": calc_bounds["north"] if calc_bounds else None,
        "calc_south": calc_bounds["south"] if calc_bounds else None,
        "calc_west": calc_bounds["west"] if calc_bounds else None,
        "calc_east": calc_bounds["east"] if calc_bounds else None,
        "manual_north": payload.manual_north,
        "manual_south": payload.manual_south,
        "manual_west": payload.manual_west,
        "manual_east": payload.manual_east,
        "use_manual_bounds": 1 if payload.use_manual_bounds else 0,
        "geometry_version_hash": version_hash,
    }
    save_fr24_cluster(cluster_record)
    set_fr24_cluster_areas(cluster_id, payload.area_ids)
    record_config_audit(
        f"fr24_cluster:{cluster_id}",
        json.dumps(old_cluster) if old_cluster else None,
        json.dumps(cluster_record),
        "admin",
    )
    return {"id": cluster_id, "calc_bounds": calc_bounds}


@app.delete("/api/fr24/clusters/{cluster_id}")
async def fr24_cluster_delete_endpoint(request: Request, cluster_id: str):
    require_auth(request)
    old_cluster = get_fr24_cluster(cluster_id)
    if not delete_fr24_cluster(cluster_id):
        raise HTTPException(status_code=404, detail="Cluster not found")
    record_config_audit(
        f"fr24_cluster:{cluster_id}",
        json.dumps(old_cluster) if old_cluster else None,
        None,
        "admin",
    )
    return {"deleted": True}


@app.get("/api/logs")
def logs_index(
    request: Request,
    limit: int = 100,
    offset: int = 0,
    kind: str = "all",
    provider: str | None = None,
    hex: str | None = None,
    inside: int = 0,
):
    """Operator audit trail: provider calls and every observation, so a
    non-finding can be reviewed instead of taken on trust."""
    require_auth(request)
    if kind not in {"all", "call", "observation"}:
        raise HTTPException(status_code=400, detail="kind must be all, call or observation")
    rows, total = query_logs(
        limit=limit,
        offset=offset,
        kind=kind,
        provider=(provider or None),
        aircraft_hex=(hex or None),
        inside_only=bool(inside),
    )
    region_names = {r["id"]: r.get("name") for r in get_query_regions()}
    cluster_names = {c["id"]: c.get("name") for c in list_fr24_clusters()}
    items = []
    for row in rows:
        region_id = row.get("region_id")
        items.append(
            {
                **row,
                "on_ground": None if row.get("on_ground") is None else bool(row["on_ground"]),
                "inside": None if row.get("inside") is None else bool(row["inside"]),
                "region_name": region_names.get(region_id) or cluster_names.get(region_id),
                "area_names": json.loads(row.pop("area_names_json") or "[]")
                if row.get("area_names_json")
                else [],
            }
        )
    return {
        "rows": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "retention_days": cfg.log_retention_days,
    }


@app.get("/api/fr24/status")
async def fr24_status(request: Request):
    require_auth(request)
    clusters = list_fr24_clusters()
    enabled_clusters = [c for c in clusters if c.get("enabled")]
    bcid = fr24_credits.billing_cycle_id(datetime.now(timezone.utc))
    used = credits_used_this_cycle(bcid)
    operating_budget = int(get_setting("fr24_monthly_operating_budget"))
    poll_interval = int(get_setting("fr24_poll_interval_seconds"))
    baseline = (
        fr24_credits.all_empty_baseline(len(enabled_clusters), poll_interval)
        if enabled_clusters
        else 0
    )

    now = datetime.now(timezone.utc)
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    elapsed_fraction = (now.day - 1 + now.hour / 24) / days_in_month if days_in_month else 0
    projected = fr24_credits.projected_end_of_cycle_credits(used, elapsed_fraction)

    enabled = bool(get_setting("fr24_enabled"))
    api_key_configured = bool(get_setting("flightradar24_api_key"))
    budget_state = fr24_credits.budget_state(used, operating_budget)
    # Every independent reason the background poller might not be spending
    # credits right now, so the dashboard can explain "Enabled: No" instead
    # of just asserting it. Mirrors the scheduler's own gates
    # (app/fr24_scheduler.py) one-for-one.
    blockers: list[str] = []
    if not enabled:
        blockers.append("flag_disabled")
    if not api_key_configured:
        blockers.append("missing_api_key")
    if not enabled_clusters:
        blockers.append("no_enabled_clusters")
    if (
        get_setting("fr24_budget_policy") == "pause_fr24"
        and budget_state == "exhausted"
    ):
        blockers.append("budget_exhausted_paused")

    return {
        "enabled": enabled,
        "enabled_source": setting_source("fr24_enabled"),
        "api_key_configured": api_key_configured,
        "api_key_source": setting_source("flightradar24_api_key"),
        "blockers": blockers,
        "active_clusters": len(enabled_clusters),
        "max_active_clusters": cfg.fr24_max_active_clusters,
        "plan_monthly_credits": int(get_setting("fr24_plan_monthly_credits")),
        "operating_budget": operating_budget,
        "promotional_credits": int(get_setting("fr24_promotional_credits")) or None,
        "credits_used_this_cycle": used,
        "budget_state": budget_state,
        "all_empty_baseline": baseline,
        "projected_end_of_cycle_credits": projected,
        "billing_cycle_id": bcid,
        "latest_poll": latest_fr24_poll(),
        "overlap_warnings": active_cluster_overlaps(clusters),
        # Retention visibility (roadmap §6.6): expose both effective windows
        # and the auto-delete gate. Additive-only -- existing consumers keep
        # working; presentation stays in the dashboard.
        "retention_events_days": min(cfg.fr24_retention_days, 29),
        "retention_state_days": cfg.state_retention_days,
        "auto_delete_enabled": bool(get_setting("fr24_auto_delete_enabled")),
    }


@app.post("/api/fr24/test")
async def fr24_test(request: Request):
    require_auth(request)
    bcid = fr24_credits.billing_cycle_id(datetime.now(timezone.utc))
    used = credits_used_this_cycle(bcid)
    operating_budget = int(get_setting("fr24_monthly_operating_budget"))
    budget_state = fr24_credits.budget_state(used, operating_budget)
    policy = get_setting("fr24_budget_policy")
    if policy == "pause_fr24" and budget_state == "exhausted":
        # Matches the scheduler's own hard block exactly (see
        # app/fr24_scheduler.py) -- a manual test call shouldn't be able to
        # spend in a state the automatic loop itself refuses to spend in.
        raise HTTPException(status_code=400, detail="FR24 budget exhausted (policy=pause_fr24)")
    clusters = [c for c in list_fr24_clusters() if c.get("enabled")]
    if not clusters:
        raise HTTPException(status_code=400, detail="Configure at least one enabled FR24 cluster first")
    cluster = clusters[0]
    bounds = bounds_of(cluster)
    if bounds is None:
        raise HTTPException(status_code=400, detail="Cluster has no computed bounds yet")
    categories = json.loads(cluster["categories_json"])
    timeout = httpx.Timeout(cfg.http_timeout_seconds)
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            result = await fetch_light(
                client,
                north=bounds["north"],
                south=bounds["south"],
                west=bounds["west"],
                east=bounds["east"],
                categories=categories,
                min_altitude_ft=cluster["min_altitude_ft"],
                max_altitude_ft=cluster["max_altitude_ft"],
                limit=1,
                cluster_id=cluster["id"],
                billing_cycle_id=fr24_credits.billing_cycle_id(datetime.now(timezone.utc)),
            )
    except FR24Failure as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "cluster_id": cluster["id"],
        "aircraft_found": result.raw_count,
        "estimated_credits": result.estimated_credits,
    }


# --- Manual FR24 Tracks ------------------------------------------------------
# Tracks are the most expensive endpoint (~40 credits per returned flight) and
# are fetched ONLY through this authenticated, explicitly confirmed, audited
# action -- no automated path ever calls fetch_track(). The GET endpoint is
# the cost/availability preview; fetch_track() owns all fr24_request_log
# accounting, so these routes never call record_fr24_request themselves.


class TrackFetchRequest(BaseModel):
    confirm: StrictBool = False  # B1: JSON "true"/1 must NOT coerce into consent


def _resolve_event_fr24_id(event: dict[str, Any]) -> str | None:
    """FR24 ID lookup order: event details first, then the enrichment row for
    the episode. Events persist the episode ID only (app/detection.py);
    enrichment persists the FR24 ID explicitly."""
    details = event.get("details")
    if isinstance(details, dict):
        direct = details.get("fr24_id")
        if isinstance(direct, str) and direct.strip():
            return direct.strip()
        episode_id = details.get("episode_id")
        if episode_id:
            enrichment = get_fr24_enrichment(event["aircraft_hex"], str(episode_id))
            if enrichment:
                candidate = enrichment.get("fr24_id")
                if isinstance(candidate, str) and candidate.strip():
                    return candidate.strip()
    return None


def _pause_fr24_budget_block() -> bool:
    """True only when spending is paused: policy=pause_fr24 AND budget
    exhausted. warn_only / continue_until_provider_rejects never block a
    deliberate manual spend -- only the paused state does."""
    if get_setting("fr24_budget_policy") != "pause_fr24":
        return False
    bcid = fr24_credits.billing_cycle_id(datetime.now(UTC))
    used = credits_used_this_cycle(bcid)
    operating_budget = int(get_setting("fr24_monthly_operating_budget"))
    return fr24_credits.budget_state(used, operating_budget) == "exhausted"


@app.get("/api/fr24/events/{event_id}/track")
async def fr24_track_status(request: Request, event_id: str):
    require_auth(request)
    event = get_event(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    fr24_id = _resolve_event_fr24_id(event)
    existing = get_fr24_track_by_event(event_id, equivalent_fr24_id=fr24_id)
    blocked_reason = None
    if not fr24_id:
        blocked_reason = "missing_fr24_id"
    elif existing:
        blocked_reason = "already_fetched"
    elif _pause_fr24_budget_block():
        blocked_reason = "budget_exhausted_pause_fr24"
    return {
        "available": blocked_reason is None,
        "event_id": event_id,
        "fr24_id": fr24_id,
        "already_fetched": existing is not None,
        "estimated_credits": fr24_credits.estimate_track_credits(1),
        "blocked_reason": blocked_reason,
    }


@app.post("/api/fr24/events/{event_id}/track")
async def fr24_track_fetch(request: Request, event_id: str, payload: TrackFetchRequest):
    require_auth(request)
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="Track fetch requires confirm=true")
    event = get_event(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    fr24_id = _resolve_event_fr24_id(event)
    if not fr24_id:
        raise HTTPException(status_code=409, detail="missing_fr24_id")
    if get_fr24_track_by_event(event_id, equivalent_fr24_id=fr24_id):
        raise HTTPException(status_code=409, detail="already_fetched")
    # Per-ID cross-process lock closes the duplicate-spend window between the
    # pre-check above and the INSERT; UNIQUE(fr24_id) remains the final guard.
    lock_name = f"fr24-track-{hashlib.sha256(fr24_id.encode('utf-8')).hexdigest()}"
    with exclusive_job_lock(lock_name) as acquired:
        if not acquired:
            raise HTTPException(status_code=409, detail="request_in_progress")
        if get_fr24_track_by_event(event_id, equivalent_fr24_id=fr24_id):
            raise HTTPException(status_code=409, detail="already_fetched")
        if _pause_fr24_budget_block():
            raise HTTPException(
                status_code=409,
                detail="FR24 budget exhausted (policy=pause_fr24): manual track fetch refused",
            )
        try:
            timeout = httpx.Timeout(cfg.http_timeout_seconds)
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                track_payload = await fetch_track(
                    client,
                    fr24_id,
                    billing_cycle_id=fr24_credits.billing_cycle_id(datetime.now(UTC)),
                )
        except FR24Failure as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        # flight-tracks returns a bare array of flights; credits bill per flight,
        # so records_returned stays the flight count. Track points are reported
        # separately -- they are what the operator actually wanted to see.
        records_returned = len(track_payload)
        track_points = sum(
            len(flight.get("tracks") or [])
            for flight in track_payload
            if isinstance(flight, dict)
        )
        saved = save_fr24_track(
            event_id=event_id,
            aircraft_hex=event["aircraft_hex"],
            fr24_id=fr24_id,
            payload=track_payload,
            requested_by="authenticated_admin",
            estimated_credits=fr24_credits.estimate_track_credits(records_returned),
        )
        if not saved:
            # Integrity loser: the parent event may have been deleted mid-flight.
            if get_event(event_id) is None:
                raise HTTPException(status_code=404, detail="Event not found")
            raise HTTPException(status_code=409, detail="already_fetched")
        record_config_audit(f"fr24_track:{event_id}", None, fr24_id, "authenticated_admin")
        stored = get_fr24_track_by_event(event_id)
        return {
            "fetched": True,
            "event_id": event_id,
            "fr24_id": fr24_id,
            "records_returned": records_returned,
            "track_points": track_points,
            "estimated_credits": fr24_credits.estimate_track_credits(records_returned),
            "created_at": stored["created_at"] if stored else "",
        }
