"""Flightradar24 Explorer-plan HTTP adapter.

Cost-controlled Light polling for the two-cluster scheduler, exceptional
Count calibration, selective Summary Full enrichment, manual Tracks, and
daily Usage sync. This module is never called from the generic
free-provider polling grid in app/providers/providers.py -- FR24 clusters
are polled by their own dedicated scheduler with their own credit
accounting, on their own cadence. Functions here accept an already-open
httpx.AsyncClient rather than creating one per call, per
FLIGHTRADAR_API.md section 4's "one reusable HTTP client" requirement --
the client's lifecycle belongs to that future scheduler.
"""

from __future__ import annotations

import asyncio
import email.utils
import logging
import random
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from .. import fr24_credits
from ..config import env_settings
from ..database import record_fr24_request, record_observation_log
from ..i18n import t
from ..settings_store import get_setting
from .base import AircraftObservation
from .readsb import number

logger = logging.getLogger(__name__)

FR24_BASE_URL = "https://fr24api.flightradar24.com"
# 400/401/402/403/404 are not retried: retrying an invalid request, an
# invalid credential, a credit/payment problem, or a missing resource cannot
# succeed on attempt 2 or 3, and burning attempts against a paid API on a
# guaranteed-failure request wastes latency for nothing.
_NO_RETRY_STATUSES = {400, 401, 402, 403, 404}
_SUMMARY_BATCH_SIZE = 10  # conservative limit -- see FLIGHTRADAR_API.md sec. 11


class FR24Failure(RuntimeError):
    """Raised for any FR24 request that could not be completed.

    Callers (the future scheduler) must never treat this as an aircraft
    disappearance signal -- see AGENTS.md detection invariants. Carries
    .latency_ms and .retry_count so callers can still log the attempt.
    """

    latency_ms: int | None = None
    retry_count: int = 0


def _lang() -> str:
    return str(get_setting("language") or "pt")


def _headers() -> dict[str, str]:
    key = get_setting("flightradar24_api_key")
    if not key:
        raise FR24Failure(t("err_flightradar24_key_missing", _lang()))
    cfg = env_settings()
    return {
        "User-Agent": cfg.user_agent,
        "Accept": "application/json",
        "Accept-Version": "v1",
        "Authorization": f"Bearer {key}",
    }


def _retry_delay(response: httpx.Response | None, attempt: int) -> float:
    if response is not None:
        value = response.headers.get("Retry-After")
        if value:
            # An explicit server-specified Retry-After is honored as-is, no jitter added.
            if value.isdigit():
                return min(float(value), 30)
            try:
                parsed = email.utils.parsedate_to_datetime(value)
                return min(max(0, (parsed - datetime.now(timezone.utc)).total_seconds()), 30)
            except (TypeError, ValueError):
                pass
    # Jitter so two clusters backing off together (shared client, shared
    # cadence) don't retry in lockstep and re-hit a rate limit simultaneously.
    return min(2**attempt, 10) * random.uniform(0.5, 1.0)


def _sanitize_for_log(url: str) -> str:
    # Never let a bearer token or full query string reach logs/exceptions.
    return url.split("?", 1)[0]


def _bounds_param(north: float, south: float, west: float, east: float) -> str:
    return f"{north},{south},{west},{east}"


def _altitude_range_param(min_ft: float, max_ft: float) -> str:
    return f"{int(min_ft)}-{int(max_ft)}"


async def _request(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    *,
    params: dict | None = None,
    expect: str = "object",
) -> tuple[dict | list, dict]:
    """One logical FR24 request with bounded retries. Returns (payload, meta)
    where meta has keys latency_ms, retry_count. Raises FR24Failure (with
    .latency_ms/.retry_count set) on unrecoverable failure -- never returns
    None/empty as a substitute for a real failure.

    ``expect`` selects the required top-level JSON shape: "object" (default)
    or "list" (flight-tracks returns a bare array).

    Callers log exactly one fr24_request_log row per logical call (see
    record_fr24_request usage below), with meta["retry_count"] recording how
    many of the (at most 3) real HTTP attempts happened. Whether FR24 itself
    bills credits for attempts that failed before the logged one succeeded is
    not publicly documented (same caveat as fr24_credits.py's cost
    constants) -- estimated_credits reflects only the logged outcome, so a
    row with retry_count > 0 is a signal to treat it as a potential
    undercount when reconciling against FR24's own reported_credits.
    """
    url = f"{FR24_BASE_URL}{path}"
    headers = _headers()
    started = datetime.now(timezone.utc)
    last_error: Exception | None = None
    response: httpx.Response | None = None
    attempt = 0
    for attempt in range(3):
        # Reset every attempt: _retry_delay must never read a stale response
        # (e.g. an earlier attempt's Retry-After) after a later attempt fails
        # with a transport error rather than an HTTP status.
        response = None
        try:
            response = await client.request(method, url, params=params, headers=headers)
            response.raise_for_status()
            payload = response.json()
            if expect == "list":
                if not isinstance(payload, list):
                    raise ValueError(t("err_provider_non_list", _lang()))
            elif not isinstance(payload, dict):
                raise ValueError(t("err_provider_non_object", _lang()))
            latency_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
            return payload, {"latency_ms": latency_ms, "retry_count": attempt}
        except httpx.HTTPStatusError as exc:
            last_error = exc
            if exc.response is not None and exc.response.status_code in _NO_RETRY_STATUSES:
                break
            if attempt < 2:
                await asyncio.sleep(_retry_delay(response, attempt))
        except (httpx.HTTPError, ValueError) as exc:
            last_error = exc
            if attempt < 2:
                await asyncio.sleep(_retry_delay(response, attempt))
    latency_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
    # last_error (httpx exceptions embed the full request URL, query string
    # included) gets the same query-stripping as our own URL -- surfaced
    # messages must never carry request parameters.
    failure = FR24Failure(
        f"FR24 request failed for {_sanitize_for_log(url)}: {_sanitize_for_log(str(last_error))}"
    )
    failure.latency_ms = latency_ms
    failure.retry_count = attempt
    raise failure


def parse_fr24_timestamp(value: object) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp /= 1000
        try:
            return datetime.fromtimestamp(timestamp, tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    text = str(value).strip()
    if text.replace(".", "", 1).isdigit():
        return parse_fr24_timestamp(float(text))
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def normalize_light_observation(raw: dict, cluster_id: str) -> AircraftObservation | None:
    cfg = env_settings()
    # fr24_id is not an ICAO 24-bit identifier and is unsuitable as a
    # cross-provider key; hex is validated and used for that instead.
    fr24_id = str(raw.get("fr24_id") or "").strip() or None
    aircraft_hex = str(raw.get("hex") or "").strip().lower()
    latitude = number(raw.get("lat"))
    longitude = number(raw.get("lon"))
    if (
        not aircraft_hex
        or latitude is None
        or longitude is None
        or not -90 <= latitude <= 90
        or not -180 <= longitude <= 180
    ):
        return None
    observed = parse_fr24_timestamp(raw.get("timestamp"))
    if observed is None:
        return None
    current = datetime.now(timezone.utc)
    skew_seconds = (observed - current).total_seconds()
    if skew_seconds > 60:  # small clock-skew allowance; reject clearly-future timestamps
        return None
    age = max(0.0, (current - observed).total_seconds())
    if age > cfg.position_max_age_seconds:
        return None
    altitude = number(raw.get("alt"))
    callsign = str(raw.get("callsign") or raw.get("flight") or "").strip().upper() or None
    return AircraftObservation(
        hex=aircraft_hex,
        callsign=callsign,
        registration=str(raw.get("reg") or "").strip().upper() or None,
        aircraft_type=str(raw.get("type") or "").strip().upper() or None,
        latitude=latitude,
        longitude=longitude,
        altitude_ft=altitude,
        on_ground=bool(raw.get("on_ground")) or altitude == 0,
        ground_speed_kt=number(raw.get("gspeed")),
        track_deg=number(raw.get("track")),
        observed_at=observed,
        seen_pos_seconds=age,
        region_id=cluster_id,
        provider="flightradar24",
        source_type=str(raw.get("source") or "") or None,
        fr24_id=fr24_id,
    )


@dataclass
class LightResult:
    observations: list[AircraftObservation]
    possibly_truncated: bool
    raw_count: int
    estimated_credits: int


def _log_dropped_aircraft(raw: object, cluster_id: str, disposition: str) -> None:
    """An aircraft FR24 returned (and billed) that never reaches detection --
    stale beyond POSITION_MAX_AGE_SECONDS, future-dated, or unparseable.
    Without a row here the difference between "returned" and "processed" is
    invisible, which is exactly the gap the audit trail exists to close."""
    data = raw if isinstance(raw, dict) else {}
    hex_code = str(data.get("hex") or "").strip().lower() or "unknown"
    reason = (
        "Position older than POSITION_MAX_AGE_SECONDS (or future-dated/unparseable); "
        "FR24 returned and billed this aircraft but detection never saw it."
        if disposition == "dropped_stale_or_unusable"
        else "Provider returned a record that was not a JSON object."
    )
    record_observation_log(
        provider="flightradar24",
        region_id=cluster_id,
        aircraft_hex=hex_code,
        callsign=str(data.get("callsign") or data.get("flight") or "").strip().upper() or None,
        registration=str(data.get("reg") or "").strip().upper() or None,
        aircraft_type=str(data.get("type") or "").strip().upper() or None,
        latitude=None,
        longitude=None,
        altitude_ft=None,
        ground_speed_kt=None,
        on_ground=False,
        observed_at=None,
        inside=False,
        area_ids=[],
        area_names=[],
        classification=None,
        disposition=disposition,
        disposition_reason=reason,
    )


async def fetch_light(
    client: httpx.AsyncClient,
    *,
    north: float,
    south: float,
    west: float,
    east: float,
    categories: list[str],
    min_altitude_ft: float,
    max_altitude_ft: float,
    limit: int,
    cluster_id: str,
    billing_cycle_id: str,
) -> LightResult:
    params = {
        "bounds": _bounds_param(north, south, west, east),
        "categories": ",".join(categories),
        "altitude_ranges": _altitude_range_param(min_altitude_ft, max_altitude_ft),
        "limit": limit,
    }
    try:
        payload, meta = await _request(
            client, "GET", "/api/live/flight-positions/light", params=params
        )
        raw_records = payload.get("data")
        if not isinstance(raw_records, list):
            raise FR24Failure("FR24 Light response missing/invalid 'data' field (schema mismatch)")
        observations = []
        for raw in raw_records:
            if not isinstance(raw, dict):
                _log_dropped_aircraft(raw, cluster_id, "dropped_malformed_record")
                continue
            item = normalize_light_observation(raw, cluster_id)
            if item is None:
                # Billed for, counted in records_returned, but never reaches
                # detection -- log it or the aircraft vanishes silently.
                _log_dropped_aircraft(raw, cluster_id, "dropped_stale_or_unusable")
                continue
            observations.append(item)
        raw_count = len(raw_records)
        possibly_truncated = raw_count >= limit
        estimated_credits = fr24_credits.estimate_light_credits(raw_count)
    except FR24Failure as exc:
        record_fr24_request(
            billing_cycle_id,
            "live/flight-positions/light",
            cluster_id,
            "failed",
            0,
            0,
            getattr(exc, "latency_ms", None),
            getattr(exc, "retry_count", 0),
            False,
        )
        raise
    except Exception as exc:
        # A malformed record (e.g. a non-dict list element) must not escape
        # as a raw, unlogged AttributeError/TypeError -- it's still a paid,
        # billable request and still must never look like a clean empty poll.
        record_fr24_request(
            billing_cycle_id,
            "live/flight-positions/light",
            cluster_id,
            "failed",
            0,
            0,
            meta["latency_ms"],
            meta["retry_count"],
            False,
        )
        raise FR24Failure(f"FR24 Light response parsing failed: {exc}") from exc
    record_fr24_request(
        billing_cycle_id,
        "live/flight-positions/light",
        cluster_id,
        "ok",
        raw_count,
        estimated_credits,
        meta["latency_ms"],
        meta["retry_count"],
        possibly_truncated,
    )
    return LightResult(
        observations=observations,
        possibly_truncated=possibly_truncated,
        raw_count=raw_count,
        estimated_credits=estimated_credits,
    )


async def fetch_count(
    client: httpx.AsyncClient,
    *,
    north: float,
    south: float,
    west: float,
    east: float,
    categories: list[str],
    min_altitude_ft: float,
    max_altitude_ft: float,
    cluster_id: str,
    billing_cycle_id: str,
) -> int:
    params = {
        "bounds": _bounds_param(north, south, west, east),
        "categories": ",".join(categories),
        "altitude_ranges": _altitude_range_param(min_altitude_ft, max_altitude_ft),
    }
    try:
        payload, meta = await _request(
            client, "GET", "/api/live/flight-positions/count", params=params
        )
        # Real schema (verified against the live FR24 sandbox):
        # {"data": [{"record_count": 123}]} -- count lives in data[0].
        data = payload.get("data") if isinstance(payload, dict) else None
        first = data[0] if isinstance(data, list) and data else None
        count_raw = first.get("record_count") if isinstance(first, dict) else None
        if not isinstance(count_raw, (int, float)) or isinstance(count_raw, bool):
            raise FR24Failure(
                "FR24 Count response missing/invalid 'data[0].record_count' field (schema mismatch)"
            )
        count = int(count_raw)
    except FR24Failure as exc:
        record_fr24_request(
            billing_cycle_id,
            "live/flight-positions/count",
            cluster_id,
            "failed",
            0,
            0,
            getattr(exc, "latency_ms", None),
            getattr(exc, "retry_count", 0),
            False,
        )
        raise
    except Exception as exc:
        record_fr24_request(
            billing_cycle_id,
            "live/flight-positions/count",
            cluster_id,
            "failed",
            0,
            0,
            meta["latency_ms"],
            meta["retry_count"],
            False,
        )
        raise FR24Failure(f"FR24 Count response parsing failed: {exc}") from exc
    # Count's own credit cost is not publicly documented (see
    # fr24_credits.py's module docstring) -- record 0 rather than guess, so a
    # wrong estimate doesn't silently corrupt budget totals. The dashboard
    # (later chunk) must show Count usage as unestimated, not free.
    record_fr24_request(
        billing_cycle_id,
        "live/flight-positions/count",
        cluster_id,
        "ok",
        count,
        0,
        meta["latency_ms"],
        meta["retry_count"],
        False,
    )
    return count


async def fetch_summary_full(
    client: httpx.AsyncClient, fr24_ids: list[str], *, billing_cycle_id: str
) -> list[dict]:
    """Batches at _SUMMARY_BATCH_SIZE ids per request, one fr24_request_log
    row per batch."""
    unique_ids = list(dict.fromkeys(fr24_ids))
    results: list[dict] = []
    for i in range(0, len(unique_ids), _SUMMARY_BATCH_SIZE):
        batch = unique_ids[i : i + _SUMMARY_BATCH_SIZE]
        params = {"flight_ids": ",".join(batch)}
        try:
            payload, meta = await _request(client, "GET", "/api/flight-summary/full", params=params)
            rows = payload.get("data")
            if not isinstance(rows, list):
                raise FR24Failure(
                    "FR24 Summary Full response missing/invalid 'data' field (schema mismatch)"
                )
        except FR24Failure as exc:
            record_fr24_request(
                billing_cycle_id,
                "flight-summary/full",
                None,
                "failed",
                0,
                0,
                getattr(exc, "latency_ms", None),
                getattr(exc, "retry_count", 0),
                False,
            )
            raise
        except Exception as exc:
            record_fr24_request(
                billing_cycle_id,
                "flight-summary/full",
                None,
                "failed",
                0,
                0,
                meta["latency_ms"],
                meta["retry_count"],
                False,
            )
            raise FR24Failure(f"FR24 Summary Full response parsing failed: {exc}") from exc
        results.extend(rows)
        estimated_credits = fr24_credits.estimate_summary_full_credits(len(rows))
        record_fr24_request(
            billing_cycle_id,
            "flight-summary/full",
            None,
            "ok",
            len(rows),
            estimated_credits,
            meta["latency_ms"],
            meta["retry_count"],
            False,
        )
    return results


async def fetch_track(client: httpx.AsyncClient, fr24_id: str, *, billing_cycle_id: str) -> list:
    """Manual, authenticated-action-only in the admin UI (a later chunk) --
    this function only performs the HTTP call and records its cost.

    Real schema (verified against the live FR24 sandbox): a top-level array
    of flight objects, each {"fr24_id": ..., "tracks": [...]} -- credits are
    billed per returned flight (FLIGHTRADAR_API.md sec. 12)."""
    params = {"flight_id": fr24_id}
    try:
        payload, meta = await _request(
            client, "GET", "/api/flight-tracks", params=params, expect="list"
        )
        rows = payload
    except FR24Failure as exc:
        record_fr24_request(
            billing_cycle_id,
            "flight-tracks",
            None,
            "failed",
            0,
            0,
            getattr(exc, "latency_ms", None),
            getattr(exc, "retry_count", 0),
            False,
        )
        raise
    except Exception as exc:
        record_fr24_request(
            billing_cycle_id, "flight-tracks", None, "failed", 0, 0, meta["latency_ms"], meta["retry_count"], False
        )
        raise FR24Failure(f"FR24 Tracks response parsing failed: {exc}") from exc
    estimated_credits = fr24_credits.estimate_track_credits(len(rows))
    record_fr24_request(
        billing_cycle_id,
        "flight-tracks",
        None,
        "ok",
        len(rows),
        estimated_credits,
        meta["latency_ms"],
        meta["retry_count"],
        False,
    )
    return payload


async def fetch_usage(client: httpx.AsyncClient, period: str) -> dict:
    # Not logged to fr24_request_log: Usage's own credit cost is undocumented
    # and it runs at most a few times a day from a daily sync job, not as
    # part of the recurring poll-cycle credit accounting that table tracks.
    if period not in {"24h", "7d", "30d", "1y"}:
        raise ValueError(f"unsupported usage period: {period}")
    payload, _meta = await _request(client, "GET", "/api/usage", params={"period": period})
    return payload
