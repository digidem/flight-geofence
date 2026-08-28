"""Call and observation audit trail behind the Logs tab.

The load-bearing test here is
``test_observation_outside_every_area_is_now_recorded``: before this feature an
aircraft observed outside every selected area was discarded by
``process_observation`` without persisting anything at all, so an operator had
no way to review why something was *not* a finding. Everything else supports
that guarantee.
"""

import asyncio
import json
from datetime import UTC, datetime, timedelta

from shapely.geometry import Polygon, mapping

from app.database import (
    cleanup_logs,
    db,
    query_logs,
    record_observation_log,
    record_provider_call,
    replace_areas,
)
from app.detection import process_observation
from app.geofences import GeofenceIndex
from app.providers.base import AircraftObservation
from app.providers.providers import _endpoint_label

# Matches the polygon used by the other detection tests.
INSIDE = (-1.0, -55.0)
OUTSIDE = (10.0, 10.0)


def _area_record(area_id="funai:test", name="Test Area"):
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


def _observation(**overrides):
    values = dict(
        hex="e49abc",
        callsign=None,
        registration=None,
        aircraft_type=None,
        latitude=INSIDE[0],
        longitude=INSIDE[1],
        altitude_ft=2000,
        on_ground=False,
        ground_speed_kt=100,
        track_deg=90,
        observed_at=datetime.now(UTC),
        seen_pos_seconds=1,
        region_id="region-test",
        provider="adsb_lol",
    )
    values.update(overrides)
    return AircraftObservation(**values)


def _selected_index():
    replace_areas([_area_record()], True)
    return GeofenceIndex()


def _log_rows():
    with db() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM observation_log")]


# ---------------------------------------------------------------------------
# The guarantee this feature exists for
# ---------------------------------------------------------------------------


def test_observation_outside_every_area_is_now_recorded():
    """The path that previously persisted nothing at all."""
    index = _selected_index()

    events = asyncio.run(
        process_observation(
            _observation(latitude=OUTSIDE[0], longitude=OUTSIDE[1]), index, "shadow"
        )
    )

    assert events == 0
    rows = _log_rows()
    assert len(rows) == 1, "an aircraft matching nothing must still leave a trace"
    assert rows[0]["disposition"] == "outside_no_episode"
    assert rows[0]["inside"] == 0
    assert rows[0]["aircraft_hex"] == "e49abc"
    assert rows[0]["disposition_reason"], "the operator needs a plain-language reason"


def test_observation_inside_area_records_the_matched_area():
    index = _selected_index()

    asyncio.run(process_observation(_observation(), index, "shadow"))

    rows = _log_rows()
    assert len(rows) == 1
    assert rows[0]["disposition"] == "inside_new_episode"
    assert rows[0]["inside"] == 1
    assert json.loads(rows[0]["area_names_json"]) == ["Test Area"]


def test_second_inside_observation_logs_a_continuing_episode():
    index = _selected_index()
    t0 = datetime.now(UTC)
    asyncio.run(process_observation(_observation(observed_at=t0), index, "shadow"))
    asyncio.run(
        process_observation(
            _observation(observed_at=t0 + timedelta(minutes=5)), index, "shadow"
        )
    )

    dispositions = [r["disposition"] for r in _log_rows()]
    assert dispositions.count("inside_new_episode") == 1
    assert dispositions.count("inside_continuing") == 1


def test_out_of_order_position_is_logged_as_stale():
    index = _selected_index()
    t0 = datetime.now(UTC)
    asyncio.run(process_observation(_observation(observed_at=t0), index, "shadow"))
    asyncio.run(
        process_observation(
            _observation(observed_at=t0 - timedelta(minutes=5)), index, "shadow"
        )
    )

    assert "stale_position" in [r["disposition"] for r in _log_rows()]


# ---------------------------------------------------------------------------
# Geometry must never reach the log
# ---------------------------------------------------------------------------


def test_endpoint_label_strips_coordinates_from_the_path():
    """These providers put the region centre and radius in the path itself."""
    assert _endpoint_label("https://api.adsb.lol/v2/point/0.280901/-52.592973/200.0") == "v2/point"
    assert _endpoint_label("https://api.airplanes.live/v2/point/-5.1/-56.2/150") == "v2/point"

    adsbx = _endpoint_label(
        "https://gateway.adsbexchange.com/api/aircraft/v2/lat/1.5/lon/2.5/dist/100"
    )
    assert adsbx == "api/aircraft/v2/lat/lon/dist"
    assert "1.5" not in adsbx and "2.5" not in adsbx and "100" not in adsbx


def test_endpoint_label_drops_the_query_string():
    label = _endpoint_label("https://example.test/v2/point?apiKey=SECRET&lat=-1.0")
    assert "SECRET" not in label
    assert "-1.0" not in label
    assert label == "v2/point"


# ---------------------------------------------------------------------------
# Recorders and querying
# ---------------------------------------------------------------------------


def _seed():
    record_provider_call(
        provider="adsb_lol",
        region_id="r1",
        endpoint="v2/point",
        outcome="failed",
        http_status=429,
        latency_ms=1204,
        error_message="429 Too Many Requests",
    )
    record_provider_call(
        provider="airplanes_live",
        region_id="r2",
        endpoint="v2/point",
        outcome="ok",
        http_status=200,
        latency_ms=330,
        aircraft_returned=0,
    )
    record_observation_log(
        provider="flightradar24",
        region_id="c1",
        aircraft_hex="ab7558",
        callsign="N83740",
        registration=None,
        aircraft_type="C208",
        latitude=-5.1,
        longitude=-56.2,
        altitude_ft=9500.0,
        ground_speed_kt=163.0,
        on_ground=False,
        observed_at="2026-08-28T22:39:10+00:00",
        inside=False,
        area_ids=[],
        area_names=[],
        classification="non_airline_candidate",
        disposition="outside_no_episode",
        disposition_reason="Outside every selected area.",
    )
    record_observation_log(
        provider="adsb_lol",
        region_id="r2",
        aircraft_hex="e48fc9",
        callsign="PRXTZ",
        registration="PR-XTZ",
        aircraft_type=None,
        latitude=-6.0,
        longitude=-57.0,
        altitude_ft=4200.0,
        ground_speed_kt=98.0,
        on_ground=False,
        observed_at="2026-08-28T21:14:02+00:00",
        inside=True,
        area_ids=["a1"],
        area_names=["Munduruku"],
        classification="non_airline_candidate",
        disposition="inside_new_episode",
        disposition_reason="First observation inside.",
    )


def test_query_logs_filters_by_kind_provider_and_inside():
    _seed()

    _, total_all = query_logs()
    assert total_all == 4

    calls, total_calls = query_logs(kind="call")
    assert total_calls == 2
    assert {r["kind"] for r in calls} == {"call"}

    obs, total_obs = query_logs(kind="observation")
    assert total_obs == 2
    assert {r["kind"] for r in obs} == {"observation"}

    _, adsb_only = query_logs(kind="call", provider="adsb_lol")
    assert adsb_only == 1

    inside, total_inside = query_logs(kind="observation", inside_only=True)
    assert total_inside == 1
    assert inside[0]["aircraft_hex"] == "e48fc9"


def test_query_logs_hex_filter_is_case_insensitive():
    _seed()
    rows, total = query_logs(aircraft_hex="AB7558")
    assert total == 1
    assert rows[0]["aircraft_hex"] == "ab7558"


def test_query_logs_total_is_independent_of_limit():
    _seed()
    rows, total = query_logs(limit=1)
    assert total == 4
    assert len(rows) == 1


def test_query_logs_orders_newest_first_across_both_tables():
    _seed()
    rows, _ = query_logs()
    stamps = [r["at"] for r in rows]
    assert stamps == sorted(stamps, reverse=True)


def test_cleanup_logs_trims_only_rows_past_the_window():
    _seed()
    old = (datetime.now(UTC) - timedelta(days=120)).isoformat()
    with db() as conn:
        conn.execute(
            "UPDATE provider_call_log SET requested_at=? WHERE http_status=429", (old,)
        )
        conn.execute(
            "UPDATE observation_log SET recorded_at=? WHERE aircraft_hex='ab7558'", (old,)
        )

    removed = cleanup_logs(90)

    assert removed == 2
    _, total = query_logs()
    assert total == 2


def test_recorders_never_raise_on_bad_input():
    """Losing an audit row must never fail a poll cycle or block detection."""
    record_provider_call(
        provider="adsb_lol",
        region_id=None,
        endpoint=None,
        outcome="ok",
        error_message=None,
    )
    record_observation_log(
        provider="adsb_lol",
        region_id=None,
        aircraft_hex="abc123",
        callsign=None,
        registration=None,
        aircraft_type=None,
        latitude=None,
        longitude=None,
        altitude_ft=None,
        ground_speed_kt=None,
        on_ground=False,
        observed_at=None,
        inside=False,
        area_ids=None,
        area_names=None,
        classification=None,
        disposition="outside_no_episode",
    )
    _, total = query_logs()
    assert total == 2
