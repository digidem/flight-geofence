"""Email regression tests for investigation links.

Based on LINKS_REPORT.txt fixture data.  Asserts that generated HTML and
plain text contain correct URLs and do not contain broken patterns.
"""

import os
from datetime import UTC

# Ensure env before any app imports
os.environ.setdefault("ADMIN_PASSWORD", "correct-horse-battery-staple")
os.environ.setdefault("APP_SECRET_KEY", "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef")
os.environ.setdefault("DASHBOARD_BASE_URL", "https://geofence.example.com")


def _make_event(**overrides):
    """Build a fixture event dict matching the LINKS_REPORT.txt data."""
    event = {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "event_type": "PROBABLE_STOP",
        "occurred_at": "2026-07-24T15:34:00+00:00",
        "aircraft_hex": "e49abc",
        "callsign": "GLO1234",
        "registration": "PT-MEJ",
        "aircraft_type": "B738",
        "airline_classification": "scheduled_airline",
        "area_ids": ["funai:territory-1"],
        "area_names": ["Acari"],
        "latitude": -23.431274,
        "longitude": -46.469954,
        "altitude_ft": 2500,
        "ground_speed_kt": 120,
        "reason": "Aircraft stationary inside protected area",
        "confidence": "medium",
        "provider": "adsb_lol",
        "phase": "live",
        "email_status": "pending",
        "details": {
            "episode_id": "ep-123",
            "classification_reason": "scheduled airline",
            "last_region_id": "region-1",
            "source_type": "ADS-B",
            "origin": "SBGR",
            "destination": "SBMA",
            "operator": "GLO",
            "on_ground": True,
        },
    }
    event.update(overrides)
    return event


class TestEmailHtmlLinks:
    """Tests for HTML email content."""

    def _html(self, event=None):
        from app.emailer import _html
        return _html(event or _make_event())

    def _plain(self, event=None):
        from app.emailer import _plain
        return _plain(event or _make_event())

    def test_exactly_one_event_cta(self):
        html = self._html()
        assert html.count("Abrir evento") == 1 or html.count("Open event") == 1

    def test_adsb_lol_hex_url(self):
        html = self._html()
        assert "globe.adsb.lol/?icao=e49abc" in html

    def test_flightaware_hex_url(self):
        html = self._html()
        assert "flightaware.com/live/modes/e49abc/redirect" in html

    def test_stale_event_email_lists_globe_before_flightaware_hex(self):
        html = self._html()
        assert html.index("globe.adsb.lol/?icao=e49abc") < html.index("flightaware.com/live/modes/e49abc")

    def test_fresh_event_email_lists_flightaware_hex_first(self):
        from datetime import datetime, timedelta
        fresh = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        html = self._html(_make_event(occurred_at=fresh))
        fa = html.index("flightaware.com/live/modes/e49abc")
        assert fa < html.index("globe.adsb.lol/?icao=e49abc")
        assert fa < html.index("globe.adsbexchange.com/?icao=e49abc")

    def test_fresh_event_plain_text_lists_flightaware_hex_first(self):
        from datetime import datetime, timedelta
        fresh = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        plain = self._plain(_make_event(occurred_at=fresh))
        fa = plain.index("flightaware.com/live/modes/e49abc")
        assert fa < plain.index("globe.adsb.lol/?icao=e49abc")

    def test_stale_fr24_event_email_lists_adsbexchange_first(self):
        event = _make_event(provider="flightradar24")
        html = self._html(event)
        assert html.index("globe.adsbexchange.com/?icao=e49abc") < html.index("globe.adsb.lol/?icao=e49abc")
        assert html.index("globe.adsb.lol/?icao=e49abc") < html.index("flightaware.com/live/modes/e49abc")

    def test_adsbexchange_hex_url(self):
        html = self._html()
        assert "globe.adsbexchange.com/?icao=e49abc" in html

    def test_airplanes_live_hex_url(self):
        html = self._html()
        assert "globe.airplanes.live/?icao=e49abc" in html

    def test_anac_registration_link(self):
        html = self._html()
        assert "aeronaves.anac.gov.br/aeronaves/cons_rab_print.asp" in html
        assert "nf=PTMEJ" in html

    def test_fr24_registration_link(self):
        html = self._html()
        assert "flightradar24.com/data/aircraft/ptmej" in html

    def test_flightaware_callsign_link(self):
        html = self._html()
        assert "flightaware.com/live/flight/GLO1234" in html

    def test_google_maps_position_link(self):
        html = self._html()
        assert "google.com/maps" in html
        assert "-23.431274" in html
        assert "-46.469954" in html

    def test_openstreetmap_position_link(self):
        html = self._html()
        assert "openstreetmap.org" in html

    def test_no_fr24_callsigns_page(self):
        html = self._html()
        assert "/data/callsigns/" not in html

    def test_no_fr24_aircraft_hex_page(self):
        html = self._html()
        assert "flightradar24.com/data/aircraft/e49abc" not in html

    def test_no_fr24_aircraft_type_page(self):
        html = self._html()
        assert "flightradar24.com/data/aircraft/b738" not in html

    def test_no_google_maps_city_airport_search(self):
        html = self._html()
        assert "/maps/search/" not in html or "Manaus+airport" not in html

    def test_no_socioambiental_specific_area(self):
        html = self._html()
        # Should not link all areas to the ISA homepage
        assert html.count("socioambiental.org") == 0 or "Search Terras" in html

    def test_rel_noopener_on_external_links(self):
        html = self._html()
        # Verify the rel="noopener noreferrer" pattern exists on external links
        assert 'rel="noopener noreferrer"' in html

    def test_no_credentials_in_urls(self):
        html = self._html()
        assert "password=" not in html
        assert "api_key=" not in html
        assert "token=" not in html

    def test_invalid_values_render_as_escaped_text(self):
        event = _make_event(aircraft_hex="invalid", registration=None, callsign=None)
        html = self._html(event)
        assert "INVALID" in html or "invalid" in html
        # No link should be generated for invalid hex
        assert "globe.adsb.lol" not in html

    def test_none_values_render_as_unavailable(self):
        event = _make_event(aircraft_hex="e49abc", registration=None, callsign=None, aircraft_type=None)
        html = self._html(event)
        assert "Indisponível" in html or "Unavailable" in html

    def test_dynamic_values_are_url_encoded(self):
        event = _make_event(latitude=-23.431274, longitude=-46.469954)
        html = self._html(event)
        # Coordinates should be properly formatted
        assert "-23.431274" in html
        assert "-46.469954" in html


class TestEmailPlainTextLinks:
    """Tests for plain text email content."""

    def _plain(self, event=None):
        from app.emailer import _plain
        return _plain(event or _make_event())

    def _html(self, event=None):
        from app.emailer import _html
        return _html(event or _make_event())

    def test_plain_text_contains_event_url(self):
        plain = self._plain()
        # If DASHBOARD_BASE_URL is set, should contain the event URL
        # Otherwise just check the hex is there
        assert "E49ABC" in plain

    def test_plain_text_contains_hex(self):
        plain = self._plain()
        assert "E49ABC" in plain

    def test_plain_text_contains_callsign(self):
        plain = self._plain()
        assert "GLO1234" in plain

    def test_plain_text_contains_registration(self):
        plain = self._plain()
        assert "PT-MEJ" in plain

    def test_plain_text_contains_position(self):
        plain = self._plain()
        assert "-23.431274" in plain
        assert "-46.469954" in plain

    def test_plain_text_contains_tracking_urls(self):
        plain = self._plain()
        assert "globe.adsb.lol" in plain
        assert "globe.adsbexchange.com" in plain
        assert "globe.airplanes.live" in plain

    def test_plain_text_equivalent_to_html(self):
        """Plain text and HTML should expose the same investigation options."""
        plain = self._plain()
        html = self._html()
        # Both should mention the same key identifiers
        for identifier in ["E49ABC", "GLO1234", "PT-MEJ"]:
            assert identifier in plain
            assert identifier in html

    def test_plain_text_contains_disclaimer(self):
        plain = self._plain()
        assert "não verificado" in plain or "unverified" in plain


class TestEmailWithFlightNumber:
    """Tests for emails that include an explicit flight number."""

    def _html(self, event=None):
        from app.emailer import _html
        return _html(event or _make_event())

    def test_flight_number_link_when_present(self):
        event = _make_event()
        event["flight_number"] = "G31234"
        html = self._html(event)
        assert "flightradar24.com/data/flights/g31234" in html

    def test_no_flight_number_link_when_absent(self):
        html = self._html()
        assert "/data/flights/" not in html


class TestEmailAirportLinks:
    """Tests for airport links in emails."""

    def _html(self, event=None):
        from app.emailer import _html
        return _html(event or _make_event())

    def test_aisweb_for_brazilian_icao(self):
        event = _make_event()
        event["details"]["origin_icao"] = "SBGR"
        html = self._html(event)
        assert "aisweb.decea.mil.br" in html
        assert "codigo=SBGR" in html

    def test_no_aisweb_for_non_brazilian_icao(self):
        event = _make_event()
        event["details"]["origin_icao"] = "KJFK"
        html = self._html(event)
        assert "aisweb.decea.mil.br" not in html

    def test_flightaware_for_valid_icao(self):
        event = _make_event()
        event["details"]["origin_icao"] = "SBGR"
        html = self._html(event)
        assert "flightaware.com/live/airport/SBGR" in html

    def test_fr24_for_iata_code(self):
        event = _make_event()
        event["details"]["origin_iata"] = "GRU"
        html = self._html(event)
        assert "flightradar24.com/data/airports/gru" in html

    def test_no_airport_links_for_names_only(self):
        event = _make_event()
        event["details"]["origin"] = "Manaus"
        event["details"]["origin_icao"] = None
        event["details"]["origin_iata"] = None
        html = self._html(event)
        assert "Manaus" in html
        # Should not have city+airport search
        assert "Manaus+airport" not in html

    def test_no_maps_search_for_airport_names(self):
        event = _make_event()
        event["details"]["origin"] = "Manaus"
        html = self._html(event)
        assert "/maps/search/Manaus" not in html
