from __future__ import annotations

import asyncio
import email.utils
import logging
from datetime import datetime, timezone

import httpx

from ..config import env_settings
from ..i18n import t
from ..database import (
    get_query_regions,
    provider_requests_today,
    record_provider_request,
)
from ..settings_store import get_setting
from .base import AircraftObservation
from .readsb import normalize_readsb

logger = logging.getLogger(__name__)


def _lang() -> str:
    return str(get_setting("language") or "pt")

PROVIDER_INFO = {
    "adsb_lol": {
        "name": "ADSB.lol",
        "cost": "Free/open data",
        "key": None,
        "note": "Default PoC source; public point/radius endpoint, no published SLA.",
    },
    "airplanes_live": {
        "name": "Airplanes.live",
        "cost": "Free non-commercial tier",
        "key": None,
        "note": "Comparison source; enforced maximum of 500 requests/day.",
    },
    "adsbexchange": {
        "name": "ADS-B Exchange",
        "cost": "Paid",
        "key": "adsbexchange_api_key",
        "note": "Strong fit for unfiltered ADS-B/Mode S/MLAT radius queries.",
    },
    "flightradar24": {
        "name": "Flightradar24 API",
        "cost": "Paid credits",
        "key": "flightradar24_api_key",
        "note": "Adds operator and route metadata; overlapping broad queries can consume credits.",
    },
}


class ProviderFailure(RuntimeError):
    pass


def _headers() -> dict[str, str]:
    cfg = env_settings()
    return {"User-Agent": cfg.user_agent, "Accept": "application/json"}


def _retry_delay(response: httpx.Response | None, attempt: int) -> float:
    if response is not None:
        value = response.headers.get("Retry-After")
        if value:
            if value.isdigit():
                return min(float(value), 30)
            try:
                parsed = email.utils.parsedate_to_datetime(value)
                return min(max(0, (parsed - datetime.now(timezone.utc)).total_seconds()), 30)
            except (TypeError, ValueError):
                pass
    return min(2**attempt, 10)


async def _get_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict | None = None,
    headers: dict[str, str] | None = None,
    provider: str | None = None,
) -> dict:
    last_error: Exception | None = None
    for attempt in range(3):
        response: httpx.Response | None = None
        request_made = False
        try:
            if provider == "airplanes_live" and provider_requests_today(provider) >= 500:
                raise ProviderFailure(t("err_provider_daily_limit", _lang()))
            response = await client.get(url, params=params, headers=headers)
            request_made = True
            if response.status_code in (401, 403, 404):
                return None
            if response.status_code == 429 or response.status_code >= 500:
                response.raise_for_status()
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ProviderFailure(t("err_provider_non_object", _lang()))
            if provider:
                record_provider_request(provider, True)
            return payload
        except (httpx.HTTPError, ValueError, ProviderFailure) as exc:
            if request_made and provider:
                record_provider_request(provider, False)
            last_error = exc
            if not request_made and provider == "airplanes_live":
                break
            if attempt < 2:
                await asyncio.sleep(_retry_delay(response, attempt))
    raise ProviderFailure(str(last_error) if last_error else t("err_provider_request_failed", _lang()))


async def _readsb_region(
    client: httpx.AsyncClient,
    provider: str,
    region: dict,
) -> list[AircraftObservation]:
    cfg = env_settings()
    if provider == "adsb_lol":
        url = (
            f"https://api.adsb.lol/v2/point/{region['latitude']}/"
            f"{region['longitude']}/{region['radius_nm']}"
        )
        headers = _headers()
    elif provider == "airplanes_live":
        url = (
            f"https://api.airplanes.live/v2/point/{region['latitude']}/"
            f"{region['longitude']}/{region['radius_nm']}"
        )
        headers = _headers()
    elif provider == "adsbexchange":
        key = get_setting("adsbexchange_api_key")
        if not key:
            raise ProviderFailure(t("err_adsbexchange_key_missing", _lang()))
        url = (
            "https://gateway.adsbexchange.com/api/aircraft/v2/lat/"
            f"{region['latitude']}/lon/{region['longitude']}/dist/{region['radius_nm']}"
        )
        # ADS-B Exchange's official examples use the api-auth header.
        headers = {**_headers(), "api-auth": key, "Accept-Encoding": "gzip"}
    else:
        raise ProviderFailure(f"{t('err_unsupported_readsb_provider', _lang())}: {provider}")

    payload = await _get_json(
        client, url, headers=headers, provider=provider
    )

    response_now = float(payload.get("now") or datetime.now(timezone.utc).timestamp())
    observations: list[AircraftObservation] = []
    for raw in payload.get("ac") or payload.get("aircraft") or []:
        item = normalize_readsb(raw, response_now, region["id"], provider)
        if item and item.seen_pos_seconds <= cfg.position_max_age_seconds:
            observations.append(item)
    return observations


async def fetch_provider_region(provider: str, region: dict) -> list[AircraftObservation]:
    timeout = httpx.Timeout(env_settings().http_timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        if provider == "flightradar24":
            raise ProviderFailure(t("err_flightradar24_grid_retired", _lang()))
        return await _readsb_region(client, provider, region)


async def fetch_all() -> tuple[list[AircraftObservation], set[str], list[str], int]:
    cfg = env_settings()
    regions = get_query_regions()
    providers = [
        provider
        for provider in get_setting("flight_providers")
        if provider in PROVIDER_INFO
    ] or ["adsb_lol"]
    if "flightradar24" in providers:
        # Must be filtered out here, before the all-providers-must-succeed
        # check below is built -- leaving it in the loop would make every
        # region permanently fail that check (flightradar24 can never
        # succeed in this grid anymore), which would silently disable
        # disappearance detection for every OTHER enabled provider too.
        logger.warning(
            "flightradar24 is configured in FLIGHT_PROVIDERS but is no longer polled "
            "through the general region grid; configure FR24 clusters and enable "
            "FR24_ENABLED instead. Skipping it this cycle."
        )
        providers = [provider for provider in providers if provider != "flightradar24"]

    observations: dict[str, AircraftObservation] = {}
    successful_by_region: dict[str, set[str]] = {
        region["id"]: set() for region in regions
    }
    errors: list[str] = []
    requests_successful = 0

    timeout = httpx.Timeout(cfg.http_timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        for provider in providers:
            for region in regions:
                try:
                    items = await _readsb_region(client, provider, region)
                    successful_by_region[region["id"]].add(provider)
                    requests_successful += 1
                    for item in items:
                        previous = observations.get(item.hex)
                        if previous is None or item.observed_at > previous.observed_at:
                            observations[item.hex] = item
                except Exception as exc:
                    logger.warning("Provider request failed %s/%s: %s", provider, region["id"], exc)
                    errors.append(f"{provider}/{region['id']}: {exc}")
                if cfg.api_request_delay_ms:
                    await asyncio.sleep(cfg.api_request_delay_ms / 1000)

    fully_successful_regions = {
        region_id
        for region_id, succeeded in successful_by_region.items()
        if set(providers).issubset(succeeded)
    }
    return list(observations.values()), fully_successful_regions, errors, requests_successful


async def test_provider(provider: str) -> dict:
    if provider not in PROVIDER_INFO:
        raise ProviderFailure(t("err_unknown_provider", _lang()))
    regions = get_query_regions()
    if not regions:
        raise ProviderFailure(t("err_select_areas_first", _lang()))
    items = await fetch_provider_region(provider, regions[0])
    return {
        "provider": provider,
        "region": regions[0]["id"],
        "aircraft": len(items),
    }
