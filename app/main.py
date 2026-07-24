import asyncio
import json
import logging
import secrets
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .auth import check_password, require_auth
from .boundary_sync import sync_boundaries
from .config import env_settings
from .coverage import regenerate_query_regions
from .database import (
    active_states,
    area_counts,
    bulk_area_selection,
    cleanup_provider_events,
    cleanup_stale_states,
    database_ok,
    event_counts,
    get_query_regions,
    init_db,
    latest_poll,
    latest_sync,
    list_areas,
    list_events,
    retryable_email_events,
    review_event,
    save_poll_run,
    selected_area_ids,
    set_area_selection,
    update_event_email,
)
from .detection import classify_aircraft, process_missing, process_observation
from .emailer import send_event_email
from .geofences import GeofenceIndex
from .locks import exclusive_job_lock
from .providers import PROVIDER_INFO, fetch_all, test_provider
from .settings_store import (
    SETTING_DEFS,
    clear_setting,
    get_setting,
    public_settings,
    set_setting,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

APP_VERSION = "0.4.0"
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
    if sync_lock.locked():
        return {"status": "skipped", "reason": "Boundary sync already running"}
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
    if poll_lock.locked():
        return {"status": "skipped", "reason": "Coverage cycle already running"}
    async with poll_lock:
        with exclusive_job_lock("coverage-poll") as acquired:
            if not acquired:
                return {"status": "skipped", "reason": "Coverage cycle already running in another process"}
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
    cleanup_stale_states(cfg.state_retention_days)
    cleanup_provider_events("flightradar24", min(cfg.fr24_retention_days, 29))
    # Retry past live notifications even when no coverage regions currently exist,
    # but respect an operator downgrade to Shadow/Review as an immediate mail pause.
    if phase == "live":
        await retry_email_queue()
    if not regions:
        run.update(
            {
                "completed_at": utc_now().isoformat(),
                "error_message": "No query regions. Sync and select protected areas first.",
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
        [asyncio.create_task(boundary_loop()), asyncio.create_task(polling_loop())]
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


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "version": APP_VERSION}


@app.get("/readyz")
async def readyz():
    if not database_ok():
        raise HTTPException(status_code=503, detail="Database check failed")
    return {"status": "ready", "version": APP_VERSION}


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
    provider = str(get_setting("email_provider"))
    errors: list[str] = []
    if provider == "console":
        errors.append("Choose Resend or SMTP before enabling Live phase")
    elif provider == "resend" and not get_setting("resend_api_key"):
        errors.append("Resend API key is missing")
    elif provider == "smtp" and not all(
        [get_setting("smtp_host"), get_setting("smtp_username"), get_setting("smtp_password")]
    ):
        errors.append("SMTP host, username and password are required")
    if not get_setting("alert_recipients"):
        errors.append("At least one alert recipient is required")
    return errors


def _warnings(counts: dict, regions: list[dict]) -> list[str]:
    warnings: list[str] = []
    if counts["total"] == 0:
        warnings.append("Official boundaries have not been synchronized yet.")
    if counts["selected"] == 0:
        warnings.append("No protected areas are selected.")
    providers = get_setting("flight_providers")
    interval = int(get_setting("poll_interval_seconds"))
    per_provider_daily = int(len(regions) * 86400 / max(interval, 1)) if regions else 0
    if "airplanes_live" in providers and per_provider_daily > 500:
        warnings.append(
            f"Airplanes.live would require about {per_provider_daily} requests/day; "
            "the app enforces its 500-request daily ceiling."
        )
    if "flightradar24" in providers:
        warnings.append(
            "Flightradar24 charges per returned flight; overlapping broad regions can consume credits quickly."
        )
    if get_setting("operating_phase") == "live":
        warnings.extend(_live_readiness_errors())
    effective_stop_minutes = max(
        int(get_setting("stop_min_duration_seconds")) / 60,
        (int(get_setting("min_inside_observations_for_stop")) - 1) * interval / 60,
    )
    warnings.append(
        f"With the current interval, the earliest probable-stop confirmation is roughly "
        f"{effective_stop_minutes:.1f} minutes."
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
    with exclusive_job_lock("boundary-sync") as boundaries_available:
        if not boundaries_available:
            raise HTTPException(status_code=409, detail="Boundary sync is currently running")
        with exclusive_job_lock("coverage-poll") as poll_available:
            if not poll_available:
                raise HTTPException(status_code=409, detail="Flight poll is currently running")
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
    event = {
        "id": str(uuid.uuid4()),
        "event_type": "PROBABLE_STOP",
        "aircraft_hex": "TEST01",
        "callsign": "TEST",
        "registration": None,
        "aircraft_type": None,
        "area_names": ["Configuration test"],
        "occurred_at": utc_now().isoformat(),
        "latitude": 0,
        "longitude": 0,
        "altitude_ft": None,
        "ground_speed_kt": None,
        "provider": "configuration-test",
        "reason": "Email configuration test; this is not an aircraft alert.",
        "airline_classification": "test",
        "details": {},
    }
    status_value, error = await send_event_email(event)
    if status_value == "failed":
        raise HTTPException(status_code=400, detail=error or "Email test failed")
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
    if not review_event(event_id, payload.status, payload.notes):
        raise HTTPException(status_code=400, detail="Invalid review status or event")
    return {"updated": True}
