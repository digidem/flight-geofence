"""Centralized investigation-link builder.

Every external URL generated for emails, the frontend, or event-detail pages
must be produced by a function in this module.  Direct URL construction in
templates, email renderers, provider adapters, or frontend JS is prohibited.

Note: The frontend (app/static/app.js) duplicates these URL patterns in
JavaScript for dashboard rendering.  Keep both copies in sync when changing
link logic.
"""

from __future__ import annotations

import math
import re
import uuid
from dataclasses import dataclass
from typing import Literal
from urllib.parse import quote, urlencode

from .config import env_settings

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

LinkKind = Literal[
    "event",
    "live_tracking",
    "registration",
    "flight",
    "airport",
    "map",
    "protected_area",
    "source",
]


@dataclass(frozen=True)
class InvestigationLink:
    label: str
    url: str
    kind: LinkKind
    priority: int  # lower = higher priority


# ---------------------------------------------------------------------------
# Hostname allowlist
# ---------------------------------------------------------------------------

_ALLOWED_HOSTS: frozenset[str] = frozenset({
    "globe.adsb.lol",
    "globe.adsbexchange.com",
    "globe.airplanes.live",
    "aeronaves.anac.gov.br",
    "www.flightradar24.com",
    "www.flightaware.com",
    "ourairports.com",
    "aisweb.decea.mil.br",
    "terrasindigenas.org.br",
    "www.socioambiental.org",
    "cnuc.mma.gov.br",
    "adsb.lol",
    "airplanes.live",
    "www.adsbexchange.com",
    "www.icao.int",
    "www.google.com",
    "www.openstreetmap.org",
})

# Regex for Brazilian civil registration prefix
_BRAZILIAN_REG_RE = re.compile(r"^(PP|PR|PS|PT|PU)-?[A-Z0-9]{3}$")

# ICAO hex: exactly 6 hex digits
_ICAO_HEX_RE = re.compile(r"^[0-9a-fA-F]{6}$")

# Valid ICAO callsign: 2-12 uppercase alphanumeric or hyphen
_CALLSIGN_RE = re.compile(r"^[A-Z0-9-]{2,12}$")


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _is_valid_icao_hex(value: str) -> bool:
    return bool(_ICAO_HEX_RE.match(value))


def _is_valid_callsign(value: str) -> bool:
    return bool(_CALLSIGN_RE.match(value))


def _is_valid_registration(value: str) -> bool:
    normalized = value.upper().replace("-", "")
    return len(normalized) >= 2 and normalized.isalnum() and any(c.isalpha() for c in normalized)


def _is_brazilian_registration(value: str) -> bool:
    return bool(_BRAZILIAN_REG_RE.match(value))


def _valid_lat_lng(lat: float | None, lng: float | None) -> tuple[float, float] | None:
    if lat is None or lng is None:
        return None
    try:
        lat_f = float(lat)
        lng_f = float(lng)
    except (TypeError, ValueError):
        return None
    if math.isnan(lat_f) or math.isnan(lng_f):
        return None
    if math.isinf(lat_f) or math.isinf(lng_f):
        return None
    if not (-90 <= lat_f <= 90) or not (-180 <= lng_f <= 180):
        return None
    return (lat_f, lng_f)


def _is_valid_event_id(event_id: str) -> bool:
    if not event_id:
        return False
    try:
        uuid.UUID(str(event_id))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


# ---------------------------------------------------------------------------
# Link builders
# ---------------------------------------------------------------------------


def event_link(event_id: str) -> InvestigationLink | None:
    """Canonical link to the authenticated event-detail page."""
    if not _is_valid_event_id(event_id):
        return None
    base = str(getattr(env_settings(), "dashboard_base_url", "")).rstrip("/")
    if not base:
        return None
    # Validate the base URL has a safe scheme
    from urllib.parse import urlparse
    parsed = urlparse(base)
    if parsed.scheme not in ("https", "http"):
        return None
    if parsed.username or parsed.password:
        return None
    return InvestigationLink(
        label="Open event in Flight Geofence Alerts",
        url=f"{base}/events/{event_id}",
        kind="event",
        priority=0,
    )


def aircraft_hex_links(hex_code: str | None) -> list[InvestigationLink]:
    """Tracking-service links for a validated ICAO 24-bit address."""
    if not hex_code:
        return []
    hex_clean = hex_code.strip()
    if hex_clean.startswith("~"):
        return []
    if not _is_valid_icao_hex(hex_clean):
        return []
    h = hex_clean.lower()
    return [
        InvestigationLink("ADSB.lol", f"https://globe.adsb.lol/?icao={h}", "live_tracking", 1),
        InvestigationLink("ADS-B Exchange", f"https://globe.adsbexchange.com/?icao={h}", "live_tracking", 2),
        InvestigationLink("Airplanes.live", f"https://globe.airplanes.live/?icao={h}", "live_tracking", 3),
    ]


def registration_links(registration: str | None) -> list[InvestigationLink]:
    """Lookup links for an aircraft registration."""
    if not registration:
        return []
    reg = registration.strip()
    normalized = reg.upper().replace("-", "")
    if not _is_valid_registration(reg):
        return []

    links: list[InvestigationLink] = []

    # Brazilian civil registrations → ANAC RAB
    if _is_brazilian_registration(reg.upper()):
        anac_url = (
            "https://aeronaves.anac.gov.br/aeronaves/cons_rab_print.asp?"
            + urlencode({"nf": normalized})
        )
        links.append(InvestigationLink("ANAC RAB", anac_url, "registration", 1))
        links.append(InvestigationLink(
            "Search ANAC RAB",
            "https://aeronaves.anac.gov.br/aeronaves/cons_rab.asp",
            "registration",
            2,
        ))

    # FR24 registration page (all syntactically valid registrations)
    fr24_url = f"https://www.flightradar24.com/data/aircraft/{normalized.lower()}"
    links.append(InvestigationLink("Flightradar24", fr24_url, "registration", 3))

    return links


def callsign_links(callsign: str | None) -> list[InvestigationLink]:
    """FlightAware link for a validated ICAO callsign."""
    if not callsign:
        return []
    cs = callsign.strip()
    if not _is_valid_callsign(cs):
        return []
    return [
        InvestigationLink(
            "FlightAware",
            f"https://www.flightaware.com/live/flight/{cs.upper()}",
            "flight",
            1,
        ),
    ]


def flight_number_links(flight_number: str | None) -> list[InvestigationLink]:
    """FR24 flight-history link — only when a commercial flight number is explicitly available."""
    if not flight_number:
        return []
    fn = flight_number.strip()
    if not fn or not fn.replace("-", "").isalnum() or len(fn) > 10:
        return []
    return [
        InvestigationLink(
            "Flightradar24",
            f"https://www.flightradar24.com/data/flights/{fn.lower()}",
            "flight",
            1,
        ),
    ]


def aircraft_type_links(aircraft_type: str | None) -> list[InvestigationLink]:
    """Aircraft type is displayed as plain text only.

    Returns a single generic ICAO reference link (not per-type).
    """
    if not aircraft_type:
        return []
    return [
        InvestigationLink(
            "ICAO aircraft type reference",
            "https://www.icao.int/operational-safety/doc-8643-aircraft-type-designators/search",
            "source",
            10,
        ),
    ]


def position_links(latitude: float | None, longitude: float | None) -> list[InvestigationLink]:
    """Map links for validated coordinates."""
    coords = _valid_lat_lng(latitude, longitude)
    if coords is None:
        return []
    lat_f, lng_f = coords
    lat_s = f"{lat_f:.6f}"
    lng_s = f"{lng_f:.6f}"
    return [
        InvestigationLink(
            "Google Maps",
            "https://www.google.com/maps/search/?api=1&query=" + quote(f"{lat_s},{lng_s}"),
            "map",
            1,
        ),
        InvestigationLink(
            "OpenStreetMap",
            (
                f"https://www.openstreetmap.org/?mlat={lat_s}&mlon={lng_s}"
                f"#map=13/{lat_s}/{lng_s}"
            ),
            "map",
            2,
        ),
    ]


def airport_links(
    icao: str | None = None,
    iata: str | None = None,
    ourairports_ident: str | None = None,
) -> list[InvestigationLink]:
    """Airport lookup links from available codes."""
    links: list[InvestigationLink] = []
    seen: set[str] = set()

    def _add(label: str, url: str, priority: int) -> None:
        if url not in seen:
            seen.add(url)
            links.append(InvestigationLink(label, url, "airport", priority))

    # AISWEB for Brazilian ICAO codes (start with S)
    if icao:
        icao_clean = icao.strip().upper()
        if len(icao_clean) == 4 and icao_clean.startswith("S"):
            _add(
                "AISWEB",
                f"https://aisweb.decea.mil.br/?codigo={icao_clean}&i=aerodromos",
                1,
            )

    # FlightAware for valid ICAO codes
    if icao:
        icao_clean = icao.strip().upper()
        if len(icao_clean) == 4 and icao_clean.isalnum():
            _add(
                "FlightAware",
                f"https://www.flightaware.com/live/airport/{icao_clean}",
                2,
            )

    # OurAirports for trusted ident
    if ourairports_ident:
        ident = ourairports_ident.strip().upper()
        if ident and all(c.isalnum() or c == "-" for c in ident):
            _add(
                "OurAirports",
                f"https://ourairports.com/airports/{ident}/",
                3,
            )

    # FR24 for validated IATA codes
    if iata:
        iata_clean = iata.strip().upper()
        if len(iata_clean) == 3 and iata_clean.isalpha():
            _add(
                "Flightradar24",
                f"https://www.flightradar24.com/data/airports/{iata_clean.lower()}",
                4,
            )

    return links


def protected_area_links(areas: list[dict] | None) -> list[InvestigationLink]:
    """Internal and external links for protected areas.

    Each area dict is expected to have at least: id, name, category, source.
    Optional keys: external_id, source_url.
    """
    if not areas:
        return []

    base = str(getattr(env_settings(), "dashboard_base_url", "")).rstrip("/")
    links: list[InvestigationLink] = []

    for area in areas:
        area_id = area.get("id", "")
        name = area.get("name", "Protected area")
        category = area.get("category", "")

        # Internal area page
        if area_id and base:
            links.append(InvestigationLink(
                name,
                f"{base}/areas/{area_id}",
                "protected_area",
                1,
            ))

        # Source-specific external links
        if category == "indigenous_territory":
            # TerrasIndígenas no Brasil — only with a verified numeric ISA ID
            isa_id = area.get("isa_id")
            if isa_id is not None:
                try:
                    isa_num = int(isa_id)
                    links.append(InvestigationLink(
                        name,
                        f"https://terrasindigenas.org.br/pt-br/terras-indigenas/{isa_num}",
                        "protected_area",
                        2,
                    ))
                except (ValueError, TypeError):
                    pass
            else:
                # Generic search portal when no verified ISA ID
                links.append(InvestigationLink(
                    "Search Terras Indígenas no Brasil",
                    "https://terrasindigenas.org.br/",
                    "protected_area",
                    10,
                ))

        elif category == "conservation_unit":
            # CNUC — generic search only (no direct record URL)
            links.append(InvestigationLink(
                "Search CNUC",
                "https://cnuc.mma.gov.br/pesquisar",
                "protected_area",
                10,
            ))

    return links


def provider_links(provider_id: str | None) -> list[InvestigationLink]:
    """Provider homepage links from the allowlist."""
    if not provider_id:
        return []
    PROVIDER_LINKS: dict[str, tuple[str, str]] = {
        "adsb_lol": ("ADSB.lol", "https://adsb.lol/"),
        "airplanes_live": ("Airplanes.live", "https://airplanes.live/"),
        "adsbexchange": ("ADS-B Exchange", "https://www.adsbexchange.com/"),
        "flightradar24": ("Flightradar24", "https://www.flightradar24.com/"),
    }
    entry = PROVIDER_LINKS.get(provider_id)
    if not entry:
        return []
    label, url = entry
    return [InvestigationLink(label, url, "source", 10)]
