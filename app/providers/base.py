from dataclasses import dataclass
from datetime import datetime


@dataclass
class AircraftObservation:
    hex: str
    callsign: str | None
    registration: str | None
    aircraft_type: str | None
    latitude: float
    longitude: float
    altitude_ft: float | None
    on_ground: bool
    ground_speed_kt: float | None
    track_deg: float | None
    observed_at: datetime
    seen_pos_seconds: float
    region_id: str
    provider: str
    source_type: str | None = None
    origin: str | None = None
    destination: str | None = None
    operator: str | None = None
    fr24_id: str | None = None
