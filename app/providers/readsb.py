from datetime import datetime, timezone
from typing import Any

from .base import AircraftObservation


def number(value: Any) -> float | None:
    try:
        result = float(value)
        return result if result == result else None
    except (TypeError, ValueError):
        return None


def normalize_readsb(
    raw: dict,
    response_now: float,
    region_id: str,
    provider: str,
) -> AircraftObservation | None:
    if response_now > 10_000_000_000:
        response_now /= 1000.0
    aircraft_hex = str(raw.get("hex") or "").lstrip("~").strip().lower()
    latitude = number(raw.get("lat"))
    longitude = number(raw.get("lon"))
    seen_pos = number(raw.get("seen_pos"))
    if (
        not aircraft_hex
        or latitude is None
        or longitude is None
        or seen_pos is None
        or seen_pos < 0
        or not -90 <= latitude <= 90
        or not -180 <= longitude <= 180
    ):
        return None

    alt_baro = raw.get("alt_baro")
    on_ground = isinstance(alt_baro, str) and alt_baro.lower() == "ground"
    altitude = None if on_ground else number(alt_baro)
    if altitude is None:
        altitude = number(raw.get("alt_geom"))

    try:
        observed_at = datetime.fromtimestamp(response_now - seen_pos, tz=timezone.utc)
    except (ValueError, OSError, OverflowError):
        return None

    return AircraftObservation(
        hex=aircraft_hex,
        # Normalize callsign: strip whitespace, uppercase for cross-provider merging
        callsign=str(raw.get("flight") or "").strip().upper() or None,
        registration=str(raw.get("r") or "").strip().upper() or None,
        aircraft_type=str(raw.get("t") or "").strip().upper() or None,
        latitude=latitude,
        longitude=longitude,
        altitude_ft=altitude,
        on_ground=on_ground,
        ground_speed_kt=number(raw.get("gs")),
        track_deg=number(raw.get("track")),
        observed_at=observed_at,
        seen_pos_seconds=seen_pos,
        region_id=region_id,
        provider=provider,
        source_type=str(raw.get("type") or "") or None,
    )
