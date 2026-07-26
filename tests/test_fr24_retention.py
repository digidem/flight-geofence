"""FR24 retention: auto-deletion defaults off (operator has confirmed
governmental authority to retain data indefinitely; FLIGHTRADAR_API.md
sec. 17's 30-day deletion requirement has a written-agreement exception).
"""

import asyncio
from datetime import UTC, datetime, timedelta

from app.database import get_event, insert_event
from app.settings_store import set_setting


def _old_fr24_event(event_id="old-fr24-event"):
    old_time = (datetime.now(UTC) - timedelta(days=40)).isoformat()
    return {
        "id": event_id,
        "deduplication_key": f"{event_id}:PROBABLE_STOP",
        "event_type": "PROBABLE_STOP",
        "occurred_at": old_time,
        "aircraft_hex": "abc123",
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
        "reason": "test",
        "confidence": "medium",
        "provider": "flightradar24",
        "phase": "shadow",
        "email_status": "shadow",
        "details_json": "{}",
    }


def test_fr24_auto_delete_disabled_by_default_preserves_old_events():
    # No query_regions configured -> _run_coverage_cycle_locked returns
    # right after the (now-gated) cleanup call, before ever reaching
    # fetch_all() -- no network mocking needed for this path.
    from app.main import _run_coverage_cycle_locked

    insert_event(_old_fr24_event())
    asyncio.run(_run_coverage_cycle_locked())
    assert get_event("old-fr24-event") is not None


def test_fr24_auto_delete_when_explicitly_enabled_removes_old_events():
    from app.main import _run_coverage_cycle_locked

    set_setting("fr24_auto_delete_enabled", True)
    insert_event(_old_fr24_event())
    asyncio.run(_run_coverage_cycle_locked())
    assert get_event("old-fr24-event") is None


def test_event_builder_sets_fr24_received_at_for_flightradar24_provider():
    from app.detection import _event
    from app.providers.base import AircraftObservation

    # Deliberately far in the past and distinct from "now" -- proves the
    # field uses the observation's own timestamp (when FR24 reported this
    # position), not event-creation time, which the DISAPPEARED path in
    # particular can lag by many minutes.
    old_observed_at = datetime.now(UTC) - timedelta(minutes=17)
    obs = AircraftObservation(
        hex="abc123",
        callsign=None,
        registration=None,
        aircraft_type=None,
        latitude=-1.0,
        longitude=-55.0,
        altitude_ft=1000,
        on_ground=True,
        ground_speed_kt=0,
        track_deg=None,
        observed_at=old_observed_at,
        seen_pos_seconds=1,
        region_id="c1",
        provider="flightradar24",
    )
    state = {
        "episode_id": "abc123-episode",
        "airline_classification": "unknown_candidate",
        "classification_reason": "test",
        "area_ids_json": "[]",
        "area_names_json": "[]",
    }
    event = _event("PROBABLE_STOP", obs, state, [], "test reason", "shadow")
    assert event["fr24_received_at"] == old_observed_at.isoformat()
    assert event["fr24_received_at"] != event["occurred_at"]


def test_event_builder_leaves_fr24_received_at_null_for_other_providers():
    from app.detection import _event
    from app.providers.base import AircraftObservation

    obs = AircraftObservation(
        hex="abc123",
        callsign=None,
        registration=None,
        aircraft_type=None,
        latitude=-1.0,
        longitude=-55.0,
        altitude_ft=1000,
        on_ground=True,
        ground_speed_kt=0,
        track_deg=None,
        observed_at=datetime.now(UTC),
        seen_pos_seconds=1,
        region_id="region-1",
        provider="adsb_lol",
    )
    state = {
        "episode_id": "abc123-episode",
        "airline_classification": "unknown_candidate",
        "classification_reason": "test",
        "area_ids_json": "[]",
        "area_names_json": "[]",
    }
    event = _event("PROBABLE_STOP", obs, state, [], "test reason", "shadow")
    assert event["fr24_received_at"] is None
