"""Independent FR24 two-cluster polling loop.

Runs on its own cadence (FR24_POLL_INTERVAL_SECONDS), fully separate from
the free-provider grid in app/main.py/app/providers/providers.py --
different cost model, different cadence, own cross-process lock, own cycle
history table. Feeds observations into the existing, UNCHANGED detection
primitives (GeofenceIndex, process_observation, process_missing) with
cluster ids as region ids, in their own disjoint id namespace from the
free-provider grid's region ids.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime, timedelta

import httpx

from . import fr24_credits
from .config import env_settings
from .database import (
    credits_used_this_cycle,
    get_fr24_enrichment,
    get_state,
    list_fr24_clusters,
    save_fr24_enrichment,
    save_fr24_poll_run,
    update_fr24_cluster_telemetry,
    utc_now_iso,
)
from .detection import process_missing, process_observation
from .fr24_clusters import bounds_of
from .geofences import GeofenceIndex
from .locks import exclusive_job_lock
from .providers.base import AircraftObservation
from .providers.fr24 import FR24Failure, fetch_count, fetch_light, fetch_summary_full, fetch_usage
from .settings_store import get_setting

logger = logging.getLogger(__name__)

fr24_lock = asyncio.Lock()
# In-memory only -- a process restart just re-syncs slightly early, which is
# harmless for a read-only diagnostic call that isn't part of any budget or
# detection decision.
_last_usage_sync: datetime | None = None
# Per-cluster throttle for Count calibration: a cluster that truncates every
# cycle must not fire Count every cycle too (spec section 22: "Count is
# exceptional rather than routine") -- at most once per hour per cluster.
_last_count_calibration: dict[str, datetime] = {}
_COUNT_CALIBRATION_MIN_INTERVAL = timedelta(hours=1)


def _merge_observation(
    all_observations: dict[str, AircraftObservation], obs: AircraftObservation
) -> None:
    # hex remains the canonical merge/state key, matching every other
    # provider and the rest of the detection schema (aircraft_state is keyed
    # on aircraft_hex). fr24_id is preserved on the observation itself for
    # provenance/enrichment, not used to canonicalize a different key here.
    previous = all_observations.get(obs.hex)
    if previous is None or obs.observed_at > previous.observed_at:
        all_observations[obs.hex] = obs


def _free_grid_actively_tracking(aircraft_hex: str) -> bool:
    """True if a non-FR24 provider currently holds a fresh claim on this
    aircraft's state.

    process_observation always overwrites last_region_id/last_provider to
    whoever most recently supplied an observation. If FR24 briefly observes
    an aircraft the free-provider grid is already tracking, ownership moves
    into FR24's region-id namespace; if FR24 is later disabled, fails, or
    that cluster is removed, the free grid's own process_missing call would
    then skip this aircraft forever (its last_region_id never matches the
    free grid's successful_regions again), silently blinding disappearance
    detection for an aircraft the free grid is still successfully covering.
    Deferring to the free grid's ownership here -- by simply not feeding
    this observation into detection at all this cycle -- prevents FR24 from
    ever taking over an aircraft the free grid is actively, freshly tracking.
    """
    state = get_state(aircraft_hex)
    if not state or state.get("last_provider") == "flightradar24":
        return False
    last_seen = state.get("last_seen_at")
    if not last_seen:
        return False
    try:
        parsed = datetime.fromisoformat(last_seen)
    except ValueError:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    age = (datetime.now(UTC) - parsed).total_seconds()
    return age <= env_settings().position_max_age_seconds


async def _enrich_new_candidates(
    client: httpx.AsyncClient,
    observations: dict[str, AircraftObservation],
    billing_cycle_id: str,
) -> None:
    candidates: list[tuple[str, str, str]] = []  # (hex, episode_id, fr24_id)
    for obs in observations.values():
        if not obs.fr24_id:
            continue
        state = get_state(obs.hex)
        if not state or not state.get("episode_id"):
            continue
        if state.get("area_ids_json", "[]") == "[]":
            continue  # not currently inside a protected area -- not a candidate
        episode_id = state["episode_id"]
        if get_fr24_enrichment(obs.hex, episode_id):
            continue  # already attempted this episode
        candidates.append((obs.hex, episode_id, obs.fr24_id))

    if not candidates:
        return
    fr24_ids = [c[2] for c in candidates]
    try:
        summaries = await fetch_summary_full(client, fr24_ids, billing_cycle_id=billing_cycle_id)
    except FR24Failure as exc:
        # Enrichment failure must never block detection -- it already ran
        # before this call. Mark this episode's attempt as failed (rather
        # than leaving no row at all) so it isn't retried unbounded every
        # single cycle for the life of the episode.
        logger.warning("fr24.enrichment.failed error=%s", exc)
        for aircraft_hex, episode_id, fr24_id in candidates:
            save_fr24_enrichment(
                aircraft_hex=aircraft_hex,
                episode_id=episode_id,
                fr24_id=fr24_id,
                status="failed",
                payload=None,
            )
        return
    summary_by_fr24_id = {
        s.get("fr24_id"): s for s in summaries if isinstance(s, dict) and s.get("fr24_id")
    }
    for aircraft_hex, episode_id, fr24_id in candidates:
        payload = summary_by_fr24_id.get(fr24_id)
        save_fr24_enrichment(
            aircraft_hex=aircraft_hex,
            episode_id=episode_id,
            fr24_id=fr24_id,
            status="ok" if payload else "empty",
            payload=payload,
        )
        logger.info(
            "fr24.enrichment.completed aircraft_hex=%s outcome=%s", aircraft_hex, "ok" if payload else "empty"
        )


async def _maybe_sync_usage(client: httpx.AsyncClient) -> None:
    """At most once per 24h: fetch FR24's own reported usage for
    reconciliation against our estimated_credits totals. Read-only,
    diagnostic -- never gates budget or detection decisions.
    """
    global _last_usage_sync
    if not get_setting("fr24_usage_sync_enabled"):
        return
    now = datetime.now(UTC)
    if _last_usage_sync is not None and now - _last_usage_sync < timedelta(hours=24):
        return
    try:
        usage_24h = await fetch_usage(client, "24h")
        _last_usage_sync = now
        logger.info("fr24.usage.reconciled period=24h outcome=ok summary=%s", usage_24h)
    except Exception as exc:
        # Diagnostic only -- must never break the poll cycle.
        logger.warning("fr24.usage.reconciled period=24h outcome=failed error=%s", exc)


async def run_fr24_cycle() -> dict:
    if fr24_lock.locked():
        return {"status": "skipped", "reason": "already running"}
    async with fr24_lock:
        with exclusive_job_lock("fr24-poll") as acquired:
            if not acquired:
                return {"status": "skipped", "reason": "already running (cross-process)"}
            return await _run_fr24_cycle_locked()


async def _run_fr24_cycle_locked() -> dict:
    cycle_id = str(uuid.uuid4())
    run = {
        "id": cycle_id,
        "started_at": utc_now_iso(),
        "completed_at": None,
        "success": 0,
        "clusters_json": "[]",
        "clusters_successful": 0,
        "aircraft_returned": 0,
        "events_created": 0,
        "estimated_credits": 0,
        "error_message": None,
    }
    save_fr24_poll_run(run)
    logger.info("fr24.poll.started cycle_id=%s", cycle_id)

    if not get_setting("fr24_enabled"):
        run.update({"completed_at": utc_now_iso(), "error_message": "FR24 disabled"})
        save_fr24_poll_run(run)
        return run

    clusters = [c for c in list_fr24_clusters() if c.get("enabled")]
    if not clusters:
        run.update({"completed_at": utc_now_iso(), "error_message": "no enabled clusters"})
        save_fr24_poll_run(run)
        return run
    run["clusters_json"] = json.dumps([c["id"] for c in clusters])

    billing_cycle_id = fr24_credits.billing_cycle_id(datetime.now(UTC))
    operating_budget = int(get_setting("fr24_monthly_operating_budget"))
    used = credits_used_this_cycle(billing_cycle_id)
    budget = fr24_credits.budget_state(used, operating_budget)
    policy = get_setting("fr24_budget_policy")
    if policy == "pause_fr24" and budget == "exhausted":
        run.update(
            {
                "completed_at": utc_now_iso(),
                "error_message": (
                    f"skipped: budget exhausted (policy=pause_fr24, "
                    f"used={used}/{operating_budget})"
                ),
            }
        )
        save_fr24_poll_run(run)
        logger.warning("FR24 cycle skipped: budget exhausted under pause_fr24 policy")
        return run
    if budget != "normal":
        # Unconditional on policy -- FLIGHTRADAR_API.md sec. 13 requires a
        # visible signal at warning-or-worse regardless of which policy is
        # configured, since warn_only and continue_until_provider_rejects
        # would otherwise accumulate cost with zero operator-visible signal
        # (no dashboard exists yet -- this log line is the only one today).
        logger.warning(
            "fr24.budget.warning cycle_id=%s budget_state=%s used=%s operating_budget=%s "
            "policy=%s -- nonessential calls (enrichment, usage sync) suppressed this cycle",
            cycle_id,
            budget,
            used,
            operating_budget,
            policy,
        )

    phase = get_setting("operating_phase")
    all_observations: dict[str, AircraftObservation] = {}
    successful_regions: set[str] = set()
    errors: list[str] = []
    total_estimated_credits = 0

    try:
        timeout = httpx.Timeout(env_settings().http_timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            for index, cluster in enumerate(clusters):
                bounds = bounds_of(cluster)
                if bounds is None:
                    errors.append(f"{cluster['id']}: no computed bounds yet")
                    continue
                categories = json.loads(cluster["categories_json"])
                try:
                    result = await fetch_light(
                        client,
                        north=bounds["north"],
                        south=bounds["south"],
                        west=bounds["west"],
                        east=bounds["east"],
                        categories=categories,
                        min_altitude_ft=cluster["min_altitude_ft"],
                        max_altitude_ft=cluster["max_altitude_ft"],
                        limit=int(get_setting("fr24_response_limit")),
                        cluster_id=cluster["id"],
                        billing_cycle_id=billing_cycle_id,
                    )
                    total_estimated_credits += result.estimated_credits
                    if result.possibly_truncated:
                        errors.append(
                            f"{cluster['id']}: possibly truncated ({result.raw_count} records)"
                        )
                        logger.warning(
                            "fr24.poll.truncated cycle_id=%s cluster_id=%s record_count=%s",
                            cycle_id,
                            cluster["id"],
                            result.raw_count,
                        )
                        # Per FLIGHTRADAR_API.md sec. 9: a possibly-truncated
                        # result must not advance disappearance for this
                        # cluster. Count itself is throttled per cluster
                        # (sec. 22: "exceptional rather than routine") -- a
                        # cluster truncating every cycle must not fire Count
                        # every cycle too.
                        last_calibration = _last_count_calibration.get(cluster["id"])
                        now_ts = datetime.now(UTC)
                        if (
                            last_calibration is None
                            or now_ts - last_calibration >= _COUNT_CALIBRATION_MIN_INTERVAL
                        ):
                            try:
                                count = await fetch_count(
                                    client,
                                    north=bounds["north"],
                                    south=bounds["south"],
                                    west=bounds["west"],
                                    east=bounds["east"],
                                    categories=categories,
                                    min_altitude_ft=cluster["min_altitude_ft"],
                                    max_altitude_ft=cluster["max_altitude_ft"],
                                    cluster_id=cluster["id"],
                                    billing_cycle_id=billing_cycle_id,
                                )
                                _last_count_calibration[cluster["id"]] = now_ts
                                logger.info(
                                    "fr24.count.calibrated cluster_id=%s count=%s", cluster["id"], count
                                )
                            except FR24Failure as count_exc:
                                # A Count failure must not invalidate the
                                # already-received Light records; the cycle
                                # just stays incomplete for disappearance
                                # logic (already true, this cluster was
                                # excluded from successful_regions above).
                                logger.warning(
                                    "FR24 count calibration failed for %s: %s",
                                    cluster["id"],
                                    count_exc,
                                )
                    else:
                        successful_regions.add(cluster["id"])
                        if result.raw_count == 0:
                            logger.info("fr24.poll.empty cycle_id=%s cluster_id=%s", cycle_id, cluster["id"])
                    for obs in result.observations:
                        if _free_grid_actively_tracking(obs.hex):
                            continue
                        _merge_observation(all_observations, obs)
                    update_fr24_cluster_telemetry(
                        cluster["id"], utc_now_iso(), result.raw_count, result.estimated_credits, None
                    )
                except FR24Failure as exc:
                    errors.append(f"{cluster['id']}: {exc}")
                    update_fr24_cluster_telemetry(cluster["id"], utc_now_iso(), None, None, str(exc)[:500])
                    logger.warning(
                        "fr24.poll.failed cycle_id=%s cluster_id=%s error=%s", cycle_id, cluster["id"], exc
                    )
                if index < len(clusters) - 1:
                    delay = max(0, int(get_setting("fr24_inter_cluster_delay_seconds")))
                    await asyncio.sleep(delay)

            index_ = GeofenceIndex()
            events_created = 0
            for observation in all_observations.values():
                events_created += await process_observation(observation, index_, phase)
            events_created += await process_missing(
                successful_regions, set(all_observations.keys()), phase
            )

            if get_setting("fr24_fetch_summary_on_entry") and budget == "normal":
                await _enrich_new_candidates(client, all_observations, billing_cycle_id)

            if budget == "normal":
                await _maybe_sync_usage(client)
    except Exception as exc:
        logger.exception("FR24 cycle failed")
        run.update({"completed_at": utc_now_iso(), "error_message": str(exc)[:4000]})
        save_fr24_poll_run(run)
        return run

    run.update(
        {
            "completed_at": utc_now_iso(),
            "success": 1 if successful_regions else 0,
            "clusters_successful": len(successful_regions),
            "aircraft_returned": len(all_observations),
            "events_created": events_created,
            "estimated_credits": total_estimated_credits,
            "error_message": "; ".join(errors)[:4000] if errors else None,
        }
    )
    logger.info(
        "fr24.poll.completed cycle_id=%s clusters_successful=%s aircraft_returned=%s "
        "events_created=%s estimated_credits=%s",
        cycle_id,
        len(successful_regions),
        len(all_observations),
        events_created,
        total_estimated_credits,
    )
    save_fr24_poll_run(run)
    return run


async def fr24_polling_loop() -> None:
    cfg = env_settings()
    await asyncio.sleep(max(1, cfg.scheduler_initial_delay_seconds))
    while True:
        try:
            await run_fr24_cycle()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("FR24 polling scheduler error")
        interval = max(60, int(get_setting("fr24_poll_interval_seconds")))
        await asyncio.sleep(interval)
