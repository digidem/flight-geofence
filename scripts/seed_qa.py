#!/usr/bin/env python3
"""Seed the local flight-geofence DB with deterministic test data so the
Eventos review queue + investigation drawer (#15) can be exercised by
hand.

Usage:
    env DATABASE_PATH=data/runtime/flight_alerts.db \
        uv run python scripts/seed_qa.py [--reset]

The script is idempotent: --reset wipes events/areas first; without --reset
it keeps existing rows and only adds the QA fixtures if the event id is
absent. No live provider calls, no email side effects.

It also seeds a small area (TI Raposa Serra do Sol, ~3 km square near
Boa Vista / RR) so the Monitoramento map renders a polygon and the
event dots land inside a visible region.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Add the repo root to sys.path so we can import app.* without packaging.
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.config import env_settings  # noqa: E402  (after sys.path mutation)

# A small square near Boa Vista/RR. Real-world area name so the operator
# can recognise the seed data.
TI_RAPOSA_ID = "ti-raposa-serra-do-sol-qa"
TI_RAPOSA_NAME = "Terra Indígena Raposa Serra do Sol"
TI_RAPOSA_CENTER_LON = -61.3975
TI_RAPOSA_CENTER_LAT = 3.6750
TI_RAPOSA_HALF_DEG = 0.02  # ~4 km half-side -> ~4 km square in lat/lon

# A slightly different area to make the Eventos list look like the
# monitoring scenario — multiple protected areas, multiple events.
PN_SerraDoDivisor_ID = "pn-serra-do-divisor-qa"
PN_SerraDoDivisor_NAME = "Parque Nacional da Serra do Divisor"
PN_SerraDoDivisor_CENTER_LON = -73.4770
PN_SerraDoDivisor_CENTER_LAT = -8.3500
PN_SerraDoDivisor_HALF_DEG = 0.015


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _box_polygon(lon: float, lat: float, half: float) -> dict:
    return {
        "type": "Polygon",
        "coordinates": [[
            [lon - half, lat - half],
            [lon + half, lat - half],
            [lon + half, lat + half],
            [lon - half, lat + half],
            [lon - half, lat - half],
        ]],
    }


def _bbox_of(lon: float, lat: float, half: float) -> tuple[float, float, float, float]:
    return lon - half, lat - half, lon + half, lat + half


def ensure_areas(conn: sqlite3.Connection, reset: bool) -> list[str]:
    """Insert the two seed areas. Returns their ids."""
    if reset:
        conn.execute("DELETE FROM events")
        conn.execute("DELETE FROM areas")
        print("  --reset: cleared events + areas tables")

    areas = [
        {
            "id": TI_RAPOSA_ID,
            "name": TI_RAPOSA_NAME,
            "category": "indigenous_territory",
            "state": "RR",
            "phase": "live",
            "selected": 1,
            "lon": TI_RAPOSA_CENTER_LON,
            "lat": TI_RAPOSA_CENTER_LAT,
            "half": TI_RAPOSA_HALF_DEG,
        },
        {
            "id": PN_SerraDoDivisor_ID,
            "name": PN_SerraDoDivisor_NAME,
            "category": "conservation_unit",
            "state": "AC",
            "phase": "live",
            "selected": 1,
            "lon": PN_SerraDoDivisor_CENTER_LON,
            "lat": PN_SerraDoDivisor_CENTER_LAT,
            "half": PN_SerraDoDivisor_HALF_DEG,
        },
    ]

    now = _now_iso()
    for area in areas:
        lon, lat, half = area["lon"], area["lat"], area["half"]
        min_lon, min_lat, max_lon, max_lat = _bbox_of(lon, lat, half)
        geometry = json.dumps(_box_polygon(lon, lat, half))
        conn.execute(
            """
            INSERT INTO areas(
                id, source, external_id, name, category, state, phase, selected,
                geometry_json, min_lon, min_lat, max_lon, max_lat,
                source_date, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                category=excluded.category,
                state=excluded.state,
                phase=excluded.phase,
                selected=excluded.selected,
                geometry_json=excluded.geometry_json,
                min_lon=excluded.min_lon,
                min_lat=excluded.min_lat,
                max_lon=excluded.max_lon,
                max_lat=excluded.max_lat,
                updated_at=excluded.updated_at
            """,
            (
                area["id"],
                "qa-seed",
                area["id"],
                area["name"],
                area["category"],
                area["state"],
                area["phase"],
                area["selected"],
                geometry,
                min_lon, min_lat, max_lon, max_lat,
                now, now,
            ),
        )

    print(f"  areas: {len(areas)} seeded (TI Raposa Serra do Sol, PN Serra do Divisor)")
    return [a["id"] for a in areas]


def ensure_events(conn: sqlite3.Connection, area_ids: list[str], reset: bool) -> list[str]:
    """Insert QA fixture events. Returns the inserted event ids (new only)."""

    # Eight fixture events across 4 review statuses, two areas, two event
    # types, with two distinct aircraft so the Monitoramento map shows two
    # dots.
    base = datetime.now(UTC).replace(microsecond=0)
    fixtures = [
        # (label, area_idx, event_type, hex, callsign, registration, lat, lon, alt, gs, review_status, review_notes)
        (
            "PROBABLE_STOP @ Raposa", 0, "PROBABLE_STOP",
            "ABC123", "TAP123", "PT-ABC1",
            TI_RAPOSA_CENTER_LAT + 0.005, TI_RAPOSA_CENTER_LON + 0.008,
            3200, 12, "unreviewed", None,
        ),
        (
            "DISAPPEARANCE @ Raposa", 0, "DISAPPEARANCE",
            "ABC123", "TAP123", "PT-ABC1",
            TI_RAPOSA_CENTER_LAT - 0.010, TI_RAPOSA_CENTER_LON + 0.004,
            None, 0, "useful", "Confirmed by visual on FR24 playback.",
        ),
        (
            "PROBABLE_STOP @ Serra do Divisor", 1, "PROBABLE_STOP",
            "DEF456", "GLO456", "PT-DEF2",
            PN_SerraDoDivisor_CENTER_LAT + 0.003, PN_SerraDoDivisor_CENTER_LON - 0.006,
            1500, 8, "noise", "Bird survey flight — out of scope.",
        ),
        (
            "DISAPPEARANCE @ Serra do Divisor", 1, "DISAPPEARANCE",
            "DEF456", "GLO456", "PT-DEF2",
            PN_SerraDoDivisor_CENTER_LAT + 0.008, PN_SerraDoDivisor_CENTER_LON - 0.004,
            1100, 95, "uncertain", None,
        ),
        (
            "Earlier PROBABLE_STOP @ Raposa", 0, "PROBABLE_STOP",
            "ABC123", "TAP123", "PT-ABC1",
            TI_RAPOSA_CENTER_LAT - 0.003, TI_RAPOSA_CENTER_LON - 0.007,
            3000, 14, "unreviewed", None,
        ),
        (
            "Old DISAPPEARANCE @ Raposa", 0, "DISAPPEARANCE",
            "ABC123", "TAP123", "PT-ABC1",
            TI_RAPOSA_CENTER_LAT + 0.012, TI_RAPOSA_CENTER_LON - 0.010,
            None, 0, "useful", None,
        ),
        (
            "Recent useful @ Serra do Divisor", 1, "PROBABLE_STOP",
            "DEF456", "GLO456", "PT-DEF2",
            PN_SerraDoDivisor_CENTER_LAT - 0.006, PN_SerraDoDivisor_CENTER_LON + 0.005,
            1800, 22, "useful", "Logged with neighbouring base.",
        ),
        (
            "Recent noise @ Raposa", 0, "PROBABLE_STOP",
            "ABC123", "TAP123", "PT-ABC1",
            TI_RAPOSA_CENTER_LAT + 0.001, TI_RAPOSA_CENTER_LON - 0.002,
            3400, 18, "noise", "Commuter overflight, recurring.",
        ),
    ]

    inserted: list[str] = []
    for offset_min, fix in enumerate(fixtures):
        # Stagger occurred_at so the list is interesting and the
        # Monitoramento "recent events" picks the most recent.
        occurred = (base - timedelta(minutes=offset_min * 17)).isoformat().replace("+00:00", "Z")
        (
            label, area_idx, event_type, hex_code, callsign, reg,
            lat, lon, alt, gs, review_status, review_notes,
        ) = fix
        area_id = area_ids[area_idx]
        event_id = f"qa-{event_type.lower()}-{hex_code.lower()}-{offset_min:02d}"
        dedupe_key = f"qa-seed:{event_id}"

        # Skip if already present (unless --reset). The ON CONFLICT below
        # updates the row in case the operator re-runs to refresh notes.
        existing = conn.execute(
            "SELECT id FROM events WHERE deduplication_key = ?", (dedupe_key,)
        ).fetchone()
        if existing and not reset:
            continue

        # Pick a confidence value aligned with the event type.
        confidence = "high" if event_type == "PROBABLE_STOP" else "medium"

        # Use a deterministic reviewed_at for non-unreviewed rows so the
        # UI displays a stable date.
        reviewed_at = None
        if review_status != "unreviewed":
            reviewed_at = (base - timedelta(hours=2 + offset_min)).isoformat().replace("+00:00", "Z")

        # Stable area_ids + area_names JSON (the same area twice for the
        # events that are inside the box, just to match what the
        # production detection loop stores).
        area_ids_json = json.dumps([area_id])
        area_names_json = json.dumps([
            "Terra Indígena Raposa Serra do Sol" if area_id == TI_RAPOSA_ID
            else "Parque Nacional da Serra do Divisor"
        ])
        details_json = json.dumps({
            "source_type": "qa_seed",
            "episode_id": f"qa-ep-{event_id[-6:]}",
        })

        conn.execute(
            """
            INSERT INTO events(
                id, deduplication_key, event_type, occurred_at,
                aircraft_hex, callsign, registration, aircraft_type,
                airline_classification,
                area_ids_json, area_names_json,
                latitude, longitude, altitude_ft, ground_speed_kt,
                reason, confidence, provider, phase,
                email_status,
                review_status, review_notes, reviewed_at,
                details_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                event_type=excluded.event_type,
                occurred_at=excluded.occurred_at,
                aircraft_hex=excluded.aircraft_hex,
                callsign=excluded.callsign,
                registration=excluded.registration,
                aircraft_type=excluded.aircraft_type,
                area_ids_json=excluded.area_ids_json,
                area_names_json=excluded.area_names_json,
                latitude=excluded.latitude,
                longitude=excluded.longitude,
                altitude_ft=excluded.altitude_ft,
                ground_speed_kt=excluded.ground_speed_kt,
                reason=excluded.reason,
                confidence=excluded.confidence,
                provider=excluded.provider,
                phase=excluded.phase,
                review_status=excluded.review_status,
                review_notes=excluded.review_notes,
                reviewed_at=excluded.reviewed_at,
                details_json=excluded.details_json
            """,
            (
                event_id, dedupe_key, event_type, occurred,
                hex_code, callsign, reg, "C172",
                "scheduled_airline",
                area_ids_json, area_names_json,
                lat, lon, alt, gs,
                f"QA seed: {label}",
                confidence, "qa-seed", "live",
                "not_applicable",
                review_status, review_notes, reviewed_at,
                details_json,
            ),
        )
        inserted.append(event_id)

    by_status: dict[str, int] = {}
    for fix in fixtures:
        by_status[fix[10]] = by_status.get(fix[10], 0) + 1
    summary = ", ".join(f"{k}={v}" for k, v in sorted(by_status.items()))
    print(f"  events: {len(inserted)} inserted (status mix: {summary})")
    print(f"  total events in DB: {conn.execute('SELECT COUNT(*) FROM events').fetchone()[0]}")
    return inserted


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed QA fixtures for #15")
    parser.add_argument(
        "--reset", action="store_true",
        help="Wipe events + areas first (idempotent otherwise)",
    )
    args = parser.parse_args()

    settings = env_settings()
    db_path = settings.database_path
    if not db_path:
        print("env_settings().database_path is empty; set DATABASE_PATH or .env",
              file=sys.stderr)
        return 1

    print(f"Seeding into {db_path}")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        area_ids = ensure_areas(conn, reset=args.reset)
        ensure_events(conn, area_ids, reset=args.reset)
        conn.commit()
    finally:
        conn.close()

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
