#!/usr/bin/env python3
"""Optional manual external-link checker.

Disabled by default.  Enable with::

    RUN_EXTERNAL_LINK_TESTS=1 python scripts/check_external_links.py

Never runs in CI or normal test suites.  Never sends application secrets.
Treats 401, 403, and 429 as inconclusive rather than broken.
"""

from __future__ import annotations

import os
import sys
import time
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import Any

# Only run when explicitly enabled
if os.environ.get("RUN_EXTERNAL_LINK_TESTS") != "1":
    print("External link checks disabled. Set RUN_EXTERNAL_LINK_TESTS=1 to enable.")
    sys.exit(0)


# ---------------------------------------------------------------------------
# Fixture data
# ---------------------------------------------------------------------------

FIXTURES: dict[str, Any] = {
    "icao_hex": "e48324",
    "registration": "PT-MEJ",
    "callsign": "GLO1234",
    "flight_number": "G31234",
    "airport_icao": "SBGR",
    "airport_iata": "GRU",
    "latitude": -23.431274,
    "longitude": -46.469954,
    "isa_territory_id": 4184,
}

USER_AGENT = "flight-geofence-link-checker/1.0 (manual audit)"
TIMEOUT = 15  # seconds


# ---------------------------------------------------------------------------
# URL builder (mirrors app/links.py patterns)
# ---------------------------------------------------------------------------

def build_test_urls() -> list[tuple[str, str]]:
    """Build (label, url) pairs from fixtures."""
    f = FIXTURES
    h = f["icao_hex"].lower()
    reg = f["registration"].upper().replace("-", "")
    cs = f["callsign"].upper()
    fn = f["flight_number"].lower()
    ic = f["airport_icao"].upper()
    ia = f["airport_iata"].lower()
    lat = f["latitude"]
    lng = f["longitude"]

    return [
        ("ADSB.lol hex", f"https://globe.adsb.lol/?icao={h}"),
        ("ADS-B Exchange hex", f"https://globe.adsbexchange.com/?icao={h}"),
        ("Airplanes.live hex", f"https://globe.airplanes.live/?icao={h}"),
        ("ANAC RAB specific", f"https://aeronaves.anac.gov.br/aeronaves/cons_rab_print.asp?nf={reg}"),
        ("ANAC RAB search", "https://aeronaves.anac.gov.br/aeronaves/cons_rab.asp"),
        ("FR24 registration", f"https://www.flightradar24.com/data/aircraft/{reg.lower()}"),
        ("FlightAware callsign", f"https://www.flightaware.com/live/flight/{cs}"),
        ("FR24 flight number", f"https://www.flightradar24.com/data/flights/{fn}"),
        ("Google Maps position", f"https://www.google.com/maps/search/?api=1&query={lat}%2C{lng}"),
        ("OpenStreetMap position", f"https://www.openstreetmap.org/?mlat={lat}&mlon={lng}#map=13/{lat}/{lng}"),
        ("AISWEB airport", f"https://aisweb.decea.mil.br/?codigo={ic}&i=aerodromos"),
        ("FlightAware airport", f"https://www.flightaware.com/live/airport/{ic}"),
        ("FR24 airport", f"https://www.flightradar24.com/data/airports/{ia}"),
        ("OurAirports", "https://ourairports.com/airports/SBGR/"),
        ("TerrasIndigenas search", "https://terrasindigenas.org.br/"),
        ("CNUC search", "https://cnuc.mma.gov.br/pesquisar"),
        ("ICAO type reference", "https://www.icao.int/operational-safety/doc-8643-aircraft-type-designators/search"),
        ("ADSB.lol homepage", "https://adsb.lol/"),
        ("Airplanes.live homepage", "https://airplanes.live/"),
        ("ADS-B Exchange homepage", "https://www.adsbexchange.com/"),
        ("FR24 homepage", "https://www.flightradar24.com/"),
    ]


# ---------------------------------------------------------------------------
# Check logic
# ---------------------------------------------------------------------------

@dataclass
class CheckResult:
    label: str
    url: str
    status: str  # "success" | "inconclusive" | "dns_failure" | "http_error" | "exception"
    http_code: int | None
    final_host: str
    latency_ms: int
    detail: str = ""


def check_url(label: str, url: str) -> CheckResult:
    start = time.monotonic()
    try:
        req = urllib.request.Request(url, method="GET", headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            latency = int((time.monotonic() - start) * 1000)
            code = resp.status
            final_host = resp.url.split("/")[2] if "/" in resp.url else ""
            if code == 200:
                return CheckResult(label, url, "success", code, final_host, latency)
            elif code in (401, 403, 429):
                return CheckResult(label, url, "inconclusive", code, final_host, latency,
                                   "anti-bot or rate-limited")
            else:
                return CheckResult(label, url, "http_error", code, final_host, latency)
    except urllib.error.HTTPError as exc:
        latency = int((time.monotonic() - start) * 1000)
        code = exc.code
        if code in (401, 403, 429):
            return CheckResult(label, url, "inconclusive", code, "", latency,
                               "anti-bot or rate-limited")
        return CheckResult(label, url, "http_error", code, "", latency, str(exc.reason))
    except urllib.error.URLError as exc:
        latency = int((time.monotonic() - start) * 1000)
        reason = str(exc.reason)
        if "Name or service not known" in reason or "getaddrinfo" in reason:
            return CheckResult(label, url, "dns_failure", None, "", latency, reason)
        return CheckResult(label, url, "exception", None, "", latency, reason)
    except Exception as exc:
        latency = int((time.monotonic() - start) * 1000)
        return CheckResult(label, url, "exception", None, "", latency, str(exc))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    urls = build_test_urls()
    results: list[CheckResult] = []

    print(f"Checking {len(urls)} URLs...\n")

    for label, url in urls:
        result = check_url(label, url)
        results.append(result)
        status_icon = {
            "success": "OK",
            "inconclusive": "??",
            "dns_failure": "DNS",
            "http_error": "ERR",
            "exception": "EXC",
        }[result.status]
        latency_str = f"{result.latency_ms}ms"
        detail = f" ({result.detail})" if result.detail else ""
        print(f"  [{status_icon}] {result.label:<30} {result.http_code or '-':>4}  {latency_str:>7}{detail}")
        time.sleep(0.5)  # Be polite

    # Summary
    print("\n" + "=" * 70)
    counts: dict[str, int] = {}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1

    print(f"Total: {len(results)}")
    for status, count in sorted(counts.items()):
        print(f"  {status}: {count}")

    inconclusive = [r for r in results if r.status == "inconclusive"]
    if inconclusive:
        print("\nInconclusive (anti-bot/rate-limited — likely working in browser):")
        for r in inconclusive:
            print(f"  {r.label}: {r.url}")

    failures = [r for r in results if r.status in ("dns_failure", "http_error", "exception")]
    if failures:
        print("\nFailures (may need investigation):")
        for r in failures:
            print(f"  {r.label}: {r.url} — {r.detail}")
    else:
        print("\nNo failures detected.")


if __name__ == "__main__":
    main()
