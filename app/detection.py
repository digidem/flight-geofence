import json
import math
import uuid
from datetime import datetime, timezone

from .config import env_settings
from .database import (
    active_states,
    get_state,
    insert_event,
    record_observation_log,
    update_event_email,
    upsert_state,
)
from .emailer import send_event_email
from .geofences import GeofenceIndex
from .providers import AircraftObservation
from .settings_store import get_setting


def now() -> datetime:
    return datetime.now(timezone.utc)


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = (
        math.sin(dp / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    )
    return 2 * radius * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def classify_aircraft(observation: AircraftObservation) -> tuple[str, str]:
    cfg = env_settings()
    if observation.callsign:
        prefix = observation.callsign[:3]
        if prefix in cfg.airline_prefix_set:
            return "scheduled_airline", f"callsign prefix {prefix}"
    if observation.operator:
        operator_code = observation.operator.strip().upper()
        if operator_code in cfg.airline_prefix_set:
            return "scheduled_airline", f"operator code {operator_code}"
    if observation.aircraft_type and observation.aircraft_type in cfg.airliner_type_set:
        return "scheduled_airline", f"airliner type {observation.aircraft_type}"
    if observation.callsign or observation.aircraft_type or observation.registration:
        return "non_airline_candidate", "no configured scheduled-airline rule matched"
    return "unknown_candidate", "callsign, registration and type unavailable"


def _event(
    event_type: str,
    observation: AircraftObservation,
    state: dict,
    areas: list,
    reason: str,
    phase: str,
) -> dict:
    area_ids = [area.id for area in areas] if areas else json.loads(state["area_ids_json"])
    area_names = [area.name for area in areas] if areas else json.loads(state["area_names_json"])
    return {
        "id": str(uuid.uuid4()),
        "deduplication_key": f"{state['episode_id']}:{event_type}",
        "event_type": event_type,
        "occurred_at": now().isoformat(),
        "aircraft_hex": observation.hex,
        "callsign": observation.callsign,
        "registration": observation.registration,
        "aircraft_type": observation.aircraft_type,
        "airline_classification": state["airline_classification"],
        "area_ids_json": json.dumps(area_ids),
        "area_names_json": json.dumps(area_names, ensure_ascii=False),
        "latitude": observation.latitude,
        "longitude": observation.longitude,
        "altitude_ft": observation.altitude_ft,
        "ground_speed_kt": observation.ground_speed_kt,
        "reason": reason,
        "confidence": "medium",
        "provider": observation.provider,
        # The observation's own timestamp (when FR24 reported this position),
        # not now() -- for a DISAPPEARED event in particular, process_missing
        # builds a synthetic observation from the last real sighting, which
        # can be many cycles (and many minutes) older than event creation
        # time, and occurred_at already captures "when we created this row".
        "fr24_received_at": (
            observation.observed_at.isoformat() if observation.provider == "flightradar24" else None
        ),
        "phase": phase,
        "email_status": (
            "pending"
            if phase == "live"
            else ("shadow" if phase == "shadow" else "review_only")
        ),
        "details_json": json.dumps(
            {
                "episode_id": state["episode_id"],
                "classification_reason": state["classification_reason"],
                "last_region_id": observation.region_id,
                "source_type": observation.source_type,
                "origin": observation.origin,
                "destination": observation.destination,
                "operator": observation.operator,
                "on_ground": observation.on_ground,
            }
        ),
    }


async def _persist(event: dict, phase: str) -> bool:
    if not insert_event(event):
        return False
    if phase != "live":
        return True
    public = dict(event)
    public["area_ids"] = json.loads(public.pop("area_ids_json"))
    public["area_names"] = json.loads(public.pop("area_names_json"))
    public["details"] = json.loads(public.pop("details_json"))
    status, error = await send_event_email(public)
    update_event_email(event["id"], status, error)
    return True


def _close_episode(state: dict, observation: AircraftObservation, classification: str, reason: str) -> None:
    state.update(
        {
            "callsign": observation.callsign,
            "registration": observation.registration,
            "aircraft_type": observation.aircraft_type,
            "airline_classification": classification,
            "classification_reason": reason,
            "last_seen_at": observation.observed_at.isoformat(),
            "last_provider": observation.provider,
            "last_region_id": observation.region_id,
            "latitude": observation.latitude,
            "longitude": observation.longitude,
            "altitude_ft": observation.altitude_ft,
            "ground_speed_kt": observation.ground_speed_kt,
            "area_ids_json": "[]",
            "area_names_json": "[]",
            "inside_since": None,
            "inside_observations": 0,
            "outside_observations": 0,
            "stationary_since": None,
            "stationary_anchor_lat": None,
            "stationary_anchor_lon": None,
            "missing_cycles": 0,
            "episode_id": None,
            "stop_alerted": 0,
            "disappeared_alerted": 0,
            "updated_at": now().isoformat(),
        }
    )
    upsert_state(state)


def _log_observation(
    observation: AircraftObservation,
    areas: list,
    classification: str,
    disposition: str,
    reason: str,
) -> None:
    """Record every observation the pipeline sees, inside a selected area or
    not. aircraft_state keeps only the newest row per aircraft and the
    outside-with-no-episode path below persists nothing at all, so this table
    is the only way to review afterwards why a given aircraft was not a
    finding."""
    record_observation_log(
        provider=observation.provider,
        region_id=observation.region_id,
        aircraft_hex=observation.hex,
        callsign=observation.callsign,
        registration=observation.registration,
        aircraft_type=observation.aircraft_type,
        latitude=observation.latitude,
        longitude=observation.longitude,
        altitude_ft=observation.altitude_ft,
        ground_speed_kt=observation.ground_speed_kt,
        on_ground=bool(observation.on_ground),
        observed_at=observation.observed_at.isoformat(),
        inside=bool(areas),
        area_ids=[a.id for a in areas],
        area_names=[a.name for a in areas],
        classification=classification,
        disposition=disposition,
        disposition_reason=reason,
    )


async def process_observation(
    observation: AircraftObservation,
    index: GeofenceIndex,
    phase: str,
) -> int:
    areas = index.matches(observation.latitude, observation.longitude)
    previous = get_state(observation.hex)
    classification, classification_reason = classify_aircraft(observation)
    observed_at = observation.observed_at.isoformat()

    if previous:
        last_seen = parse_time(previous.get("last_seen_at"))
        if last_seen and observation.observed_at <= last_seen:
            _log_observation(
                observation, areas, classification, "stale_position",
                "Position is not newer than the last one already recorded for "
                "this aircraft; ignored so out-of-order data cannot rewrite state.",
            )
            return 0

    if not areas:
        if not (previous and previous.get("episode_id")):
            _log_observation(
                observation, areas, classification, "outside_no_episode",
                "Observed outside every selected protected area with no open "
                "episode; nothing to track and no event possible.",
            )
        if previous and previous.get("episode_id"):
            previous["outside_observations"] = int(previous.get("outside_observations") or 0) + 1
            previous.update(
                {
                    "last_seen_at": observed_at,
                    "last_provider": observation.provider,
                    "last_region_id": observation.region_id,
                    "latitude": observation.latitude,
                    "longitude": observation.longitude,
                    "altitude_ft": observation.altitude_ft,
                    "ground_speed_kt": observation.ground_speed_kt,
                    "missing_cycles": 0,
                    "updated_at": now().isoformat(),
                }
            )
            if previous["outside_observations"] >= int(
                get_setting("outside_confirmation_observations")
            ):
                _log_observation(
                    observation, areas, classification, "episode_closed_by_leaving",
                    "Confirmed outside the selected area(s); the episode closed "
                    "without an event, which is the expected exit path.",
                )
                _close_episode(previous, observation, classification, classification_reason)
            else:
                _log_observation(
                    observation, areas, classification, "outside_pending_confirmation",
                    "Seen outside the area but not yet enough outside observations "
                    "to confirm departure; the episode stays open.",
                )
                upsert_state(previous)
        elif previous:
            _close_episode(previous, observation, classification, classification_reason)
        return 0

    area_ids = [area.id for area in areas]
    area_names = [area.name for area in areas]
    continuing = bool(
        previous
        and previous.get("episode_id")
        and json.loads(previous.get("area_ids_json") or "[]")
    )
    stop_speed = float(get_setting("stop_max_speed_kt"))
    low_speed = observation.on_ground or (
        observation.ground_speed_kt is not None
        and observation.ground_speed_kt <= stop_speed
    )

    if not continuing:
        _log_observation(
            observation, areas, classification, "inside_new_episode",
            "First observation inside the selected area(s); a new episode opened.",
        )
        upsert_state(
            {
                "aircraft_hex": observation.hex,
                "callsign": observation.callsign,
                "registration": observation.registration,
                "aircraft_type": observation.aircraft_type,
                "airline_classification": classification,
                "classification_reason": classification_reason,
                "last_seen_at": observed_at,
                "last_provider": observation.provider,
                "last_region_id": observation.region_id,
                "latitude": observation.latitude,
                "longitude": observation.longitude,
                "altitude_ft": observation.altitude_ft,
                "ground_speed_kt": observation.ground_speed_kt,
                "area_ids_json": json.dumps(area_ids),
                "area_names_json": json.dumps(area_names, ensure_ascii=False),
                "inside_since": observed_at,
                "inside_observations": 1,
                "outside_observations": 0,
                "stationary_since": observed_at if low_speed else None,
                "stationary_anchor_lat": observation.latitude if low_speed else None,
                "stationary_anchor_lon": observation.longitude if low_speed else None,
                "missing_cycles": 0,
                "episode_id": f"{observation.hex}-{observation.observed_at.strftime('%Y%m%dT%H%M%S')}",
                "stop_alerted": 0,
                "disappeared_alerted": 0,
                "updated_at": now().isoformat(),
            }
        )
        return 0

    state = previous
    had_gap = int(state.get("missing_cycles") or 0) > 0
    _log_observation(
        observation, areas, classification, "inside_continuing",
        "Continuing observation inside the selected area(s); episode advancing "
        f"toward the stop and disappearance thresholds{' after a coverage gap' if had_gap else ''}.",
    )
    state.update(
        {
            "callsign": observation.callsign,
            "registration": observation.registration,
            "aircraft_type": observation.aircraft_type,
            "airline_classification": classification,
            "classification_reason": classification_reason,
            "last_seen_at": observed_at,
            "last_provider": observation.provider,
            "last_region_id": observation.region_id,
            "latitude": observation.latitude,
            "longitude": observation.longitude,
            "altitude_ft": observation.altitude_ft,
            "ground_speed_kt": observation.ground_speed_kt,
            "area_ids_json": json.dumps(area_ids),
            "area_names_json": json.dumps(area_names, ensure_ascii=False),
            "inside_observations": int(state.get("inside_observations") or 0) + 1,
            "outside_observations": 0,
            "missing_cycles": 0,
            "updated_at": now().isoformat(),
        }
    )

    anchor_lat = state.get("stationary_anchor_lat")
    anchor_lon = state.get("stationary_anchor_lon")
    if had_gap or not low_speed:
        state.update(
            {
                "stationary_anchor_lat": observation.latitude if low_speed else None,
                "stationary_anchor_lon": observation.longitude if low_speed else None,
                "stationary_since": observed_at if low_speed else None,
            }
        )
    elif anchor_lat is None or anchor_lon is None:
        state.update(
            {
                "stationary_anchor_lat": observation.latitude,
                "stationary_anchor_lon": observation.longitude,
                "stationary_since": observed_at,
            }
        )
    else:
        distance = haversine_m(
            float(anchor_lat),
            float(anchor_lon),
            observation.latitude,
            observation.longitude,
        )
        if distance > float(get_setting("stationary_radius_meters")):
            state.update(
                {
                    "stationary_anchor_lat": observation.latitude,
                    "stationary_anchor_lon": observation.longitude,
                    "stationary_since": observed_at,
                }
            )

    stationary_since = parse_time(state.get("stationary_since"))
    stationary_seconds = (
        (observation.observed_at - stationary_since).total_seconds()
        if stationary_since
        else 0
    )
    events = 0
    if (
        classification != "scheduled_airline"
        and not state.get("stop_alerted")
        and state["inside_observations"]
        >= int(get_setting("min_inside_observations_for_stop"))
        and low_speed
        and stationary_seconds >= int(get_setting("stop_min_duration_seconds"))
    ):
        event = _event(
            "PROBABLE_STOP",
            observation,
            state,
            areas,
            (
                f"{state['inside_observations']} fresh inside observations; "
                "ground/low-speed movement remained within the configured radius "
                f"for about {int(stationary_seconds)} seconds."
            ),
            phase,
        )
        if await _persist(event, phase):
            state["stop_alerted"] = 1
            events += 1
    upsert_state(state)
    return events


async def process_missing(
    successful_regions: set[str],
    observed_hexes: set[str],
    phase: str,
) -> int:
    events = 0
    for state in active_states():
        if state["aircraft_hex"] in observed_hexes:
            continue
        if state.get("last_region_id") not in successful_regions:
            continue
        if not state.get("episode_id") or not state.get("area_ids"):
            continue
        if int(state.get("outside_observations") or 0) > 0:
            continue
        if state.get("airline_classification") == "scheduled_airline":
            continue

        state["missing_cycles"] = int(state.get("missing_cycles") or 0) + 1
        altitude = state.get("altitude_ft")
        qualifies = (
            int(state.get("inside_observations") or 0)
            >= int(get_setting("min_inside_observations_for_disappearance"))
            and (
                altitude is None
                or float(altitude)
                <= float(get_setting("disappear_max_altitude_ft"))
            )
        )
        if (
            qualifies
            and not state.get("disappeared_alerted")
            and state["missing_cycles"]
            >= int(get_setting("disappear_after_successful_polls"))
        ):
            observation = AircraftObservation(
                hex=state["aircraft_hex"],
                callsign=state.get("callsign"),
                registration=state.get("registration"),
                aircraft_type=state.get("aircraft_type"),
                latitude=float(state["latitude"]),
                longitude=float(state["longitude"]),
                altitude_ft=altitude,
                on_ground=False,
                ground_speed_kt=state.get("ground_speed_kt"),
                track_deg=None,
                observed_at=parse_time(state.get("last_seen_at")) or now(),
                seen_pos_seconds=0,
                region_id=state["last_region_id"],
                provider=state.get("last_provider") or "unknown",
            )
            event_state = {
                **state,
                "area_ids_json": json.dumps(state["area_ids"]),
                "area_names_json": json.dumps(state["area_names"], ensure_ascii=False),
            }
            event = _event(
                "DISAPPEARED",
                observation,
                event_state,
                [],
                (
                    "Last observed inside selected protected area(s); absent from "
                    f"{state['missing_cycles']} complete successful coverage cycles "
                    "for the last region."
                ),
                phase,
            )
            if await _persist(event, phase):
                state["disappeared_alerted"] = 1
                events += 1

        db_state = dict(state)
        db_state["area_ids_json"] = json.dumps(db_state.pop("area_ids"))
        db_state["area_names_json"] = json.dumps(
            db_state.pop("area_names"), ensure_ascii=False
        )
        db_state["updated_at"] = now().isoformat()
        upsert_state(db_state)
    return events
