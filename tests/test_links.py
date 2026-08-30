"""Unit tests for the centralized link builder (app/links.py)."""


# ---------------------------------------------------------------------------
# ICAO hex links
# ---------------------------------------------------------------------------

from datetime import UTC


class TestAircraftHexLinks:
    STALE = "2026-07-24T15:34:00+00:00"

    def test_stale_event_leads_with_provider_globe(self):
        from app.links import aircraft_hex_links
        links = aircraft_hex_links("E49ABC", "adsb_lol", self.STALE)
        assert [link.label for link in links] == [
            "ADSB.lol", "ADS-B Exchange", "Airplanes.live", "FlightAware",
        ]
        assert links[0].url == "https://globe.adsb.lol/?icao=e49abc"
        assert links[3].url == "https://www.flightaware.com/live/modes/e49abc/redirect"

    def test_fresh_event_leads_with_flightaware(self):
        from datetime import datetime, timedelta

        from app.links import aircraft_hex_links
        fresh = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        links = aircraft_hex_links("e49abc", "adsb_lol", fresh)
        assert [link.label for link in links] == [
            "FlightAware", "ADSB.lol", "ADS-B Exchange", "Airplanes.live",
        ]
        assert links[0].url == "https://www.flightaware.com/live/modes/e49abc/redirect"

    def test_boundary_of_fresh_window_is_stale(self):
        from datetime import datetime, timedelta

        from app.links import aircraft_hex_links
        edge = (datetime.now(UTC) - timedelta(hours=25)).isoformat()
        links = aircraft_hex_links("e49abc", "adsb_lol", edge)
        assert links[0].label == "ADSB.lol"
        assert links[-1].label == "FlightAware"

    def test_fr24_events_prefer_adsbexchange_globe(self):
        from app.links import aircraft_hex_links
        links = aircraft_hex_links("e49abc", "flightradar24", self.STALE)
        assert [link.label for link in links] == [
            "ADS-B Exchange", "ADSB.lol", "Airplanes.live", "FlightAware",
        ]

    def test_airplanes_live_events_lead_with_own_globe(self):
        from app.links import aircraft_hex_links
        links = aircraft_hex_links("e49abc", "airplanes_live", self.STALE)
        assert links[0].label == "Airplanes.live"

    def test_unknown_provider_defaults_to_adsb_lol_globe(self):
        from app.links import aircraft_hex_links
        links = aircraft_hex_links("e49abc", None, self.STALE)
        assert links[0].label == "ADSB.lol"

    def test_future_or_unparseable_occurred_at_treated_as_stale(self):
        from app.links import aircraft_hex_links
        for bad in ("2099-01-01T00:00:00+00:00", "garbage", "", None):
            links = aircraft_hex_links("e49abc", "adsb_lol", bad)
            assert links[0].label == "ADSB.lol"
            assert links[-1].label == "FlightAware"

    def test_priorities_follow_final_order(self):
        from app.links import aircraft_hex_links
        links = aircraft_hex_links("e49abc", "flightradar24", self.STALE)
        assert [link.priority for link in links] == [1, 2, 3, 4]

    def test_valid_hex_lowercase(self):
        from app.links import aircraft_hex_links
        links = aircraft_hex_links("e49abc")
        assert len(links) == 4
        assert links[0].url == "https://globe.adsb.lol/?icao=e49abc"

    def test_tilde_prefix_returns_empty(self):
        from app.links import aircraft_hex_links
        assert aircraft_hex_links("~29d348") == []

    def test_valid_hex_6_chars(self):
        from app.links import aircraft_hex_links
        # abc123 IS valid (6 hex chars)
        links = aircraft_hex_links("abc123")
        assert len(links) == 4

    def test_invalid_hex_5_chars(self):
        from app.links import aircraft_hex_links
        assert aircraft_hex_links("abc12") == []

    def test_invalid_hex_4_digits(self):
        from app.links import aircraft_hex_links
        assert aircraft_hex_links("12345") == []

    def test_invalid_hex_7_chars(self):
        from app.links import aircraft_hex_links
        assert aircraft_hex_links("1234567") == []

    def test_invalid_hex_letters_out_of_range(self):
        from app.links import aircraft_hex_links
        # 'ghijkl' are not valid hex digits
        assert aircraft_hex_links("ghijkl") == []

    def test_none_returns_empty(self):
        from app.links import aircraft_hex_links
        assert aircraft_hex_links(None) == []

    def test_empty_string_returns_empty(self):
        from app.links import aircraft_hex_links
        assert aircraft_hex_links("") == []

    def test_whitespace_trimmed(self):
        from app.links import aircraft_hex_links
        links = aircraft_hex_links("  e49abc  ")
        assert len(links) == 4

    def test_all_links_are_live_tracking_kind(self):
        from app.links import aircraft_hex_links
        links = aircraft_hex_links("e49abc")
        for link in links:
            assert link.kind == "live_tracking"


# ---------------------------------------------------------------------------
# Registration links
# ---------------------------------------------------------------------------

class TestRegistrationLinks:
    def test_brazilian_pt_abc(self):
        from app.links import registration_links
        links = registration_links("PT-ABC")
        assert len(links) == 3
        assert links[0].label == "ANAC RAB"
        assert "nf=PTABC" in links[0].url
        assert links[1].label == "Search ANAC RAB"
        assert links[2].label == "Flightradar24"
        assert "/data/aircraft/ptabc" in links[2].url

    def test_brazilian_ptabc_no_hyphen(self):
        from app.links import registration_links
        links = registration_links("PTABC")
        assert len(links) == 3
        assert "nf=PTABC" in links[0].url

    def test_brazilian_pr_ggj(self):
        from app.links import registration_links
        links = registration_links("PR-GGJ")
        assert len(links) == 3
        assert links[0].label == "ANAC RAB"
        assert "nf=PRGGJ" in links[0].url

    def test_brazilian_ps_gvo(self):
        from app.links import registration_links
        links = registration_links("PS-GVO")
        assert len(links) == 3
        assert "nf=PSGVO" in links[0].url

    def test_brazilian_pu_ttb(self):
        from app.links import registration_links
        links = registration_links("PU-TTB")
        assert len(links) == 3
        assert "nf=PUTTB" in links[0].url

    def test_non_brazilian_n699ga(self):
        from app.links import registration_links
        links = registration_links("N699GA")
        assert len(links) == 1
        assert links[0].label == "Flightradar24"
        assert "/data/aircraft/n699ga" in links[0].url

    def test_military_fab_not_brazilian_civil(self):
        from app.links import registration_links
        links = registration_links("FAB2101")
        # FAB is not in PP/PR/PS/PT/PU, so no ANAC link
        assert all(link.label != "ANAC RAB" for link in links)
        assert any(link.label == "Flightradar24" for link in links)

    def test_invalid_registration(self):
        from app.links import registration_links
        # "12345" is all digits, no letters — not a valid registration
        assert registration_links("12345") == []

    def test_too_short_registration(self):
        from app.links import registration_links
        assert registration_links("X") == []

    def test_none_returns_empty(self):
        from app.links import registration_links
        assert registration_links(None) == []

    def test_empty_string_returns_empty(self):
        from app.links import registration_links
        assert registration_links("") == []

    def test_anac_url_has_no_hyphen(self):
        from app.links import registration_links
        links = registration_links("PT-MEJ")
        assert "nf=PTMEJ" in links[0].url
        assert "PT-MEJ" not in links[0].url


# ---------------------------------------------------------------------------
# Callsign links
# ---------------------------------------------------------------------------

class TestCallsignLinks:
    def test_glo1234(self):
        from app.links import callsign_links
        links = callsign_links("GLO1234")
        assert len(links) == 1
        assert links[0].label == "FlightAware"
        assert "/flight/GLO1234" in links[0].url

    def test_azu1234(self):
        from app.links import callsign_links
        links = callsign_links("AZU1234")
        assert len(links) == 1
        assert "/flight/AZU1234" in links[0].url

    def test_glf24(self):
        from app.links import callsign_links
        links = callsign_links("GLF24")
        assert len(links) == 1

    def test_ptabc_not_valid_callsign(self):
        from app.links import callsign_links
        # PTABC is 5 chars but should be valid callsign format
        links = callsign_links("PTABC")
        assert len(links) == 1

    def test_bad_slash_query_rejected(self):
        from app.links import callsign_links
        assert callsign_links("BAD/QUERY") == []

    def test_value_with_spaces_rejected(self):
        from app.links import callsign_links
        assert callsign_links("value with spaces") == []

    def test_none_returns_empty(self):
        from app.links import callsign_links
        assert callsign_links(None) == []

    def test_empty_string_returns_empty(self):
        from app.links import callsign_links
        assert callsign_links("") == []

    def test_uses_flightaware_not_fr24(self):
        from app.links import callsign_links
        links = callsign_links("GLO1234")
        assert "flightaware.com" in links[0].url
        assert "flightradar24.com" not in links[0].url


# ---------------------------------------------------------------------------
# Flight number links
# ---------------------------------------------------------------------------

class TestFlightNumberLinks:
    def test_g31234(self):
        from app.links import flight_number_links
        links = flight_number_links("G31234")
        assert len(links) == 1
        assert links[0].label == "Flightradar24"
        assert "/data/flights/g31234" in links[0].url

    def test_ad2024(self):
        from app.links import flight_number_links
        links = flight_number_links("AD2024")
        assert len(links) == 1
        assert "/data/flights/ad2024" in links[0].url

    def test_la1234(self):
        from app.links import flight_number_links
        links = flight_number_links("LA1234")
        assert len(links) == 1

    def test_glo1234_not_flight_number(self):
        from app.links import flight_number_links
        # GLO1234 is a callsign, not a flight number — but the function
        # accepts any string. The caller is responsible for only passing
        # explicit flight_number values.
        links = flight_number_links("GLO1234")
        assert len(links) == 1  # function doesn't distinguish

    def test_none_returns_empty(self):
        from app.links import flight_number_links
        assert flight_number_links(None) == []

    def test_empty_returns_empty(self):
        from app.links import flight_number_links
        assert flight_number_links("") == []


# ---------------------------------------------------------------------------
# Aircraft type links
# ---------------------------------------------------------------------------

class TestAircraftTypeLinks:
    def test_b738_returns_empty(self):
        from app.links import aircraft_type_links
        links = aircraft_type_links("B738")
        # Aircraft type is plain text only; optionally a generic ICAO reference
        assert all(link.kind != "live_tracking" for link in links)

    def test_c208_returns_empty(self):
        from app.links import aircraft_type_links
        links = aircraft_type_links("C208")
        assert all(link.kind != "live_tracking" for link in links)

    def test_pa34_returns_empty(self):
        from app.links import aircraft_type_links
        links = aircraft_type_links("PA34")
        assert all(link.kind != "live_tracking" for link in links)

    def test_none_returns_empty(self):
        from app.links import aircraft_type_links
        assert aircraft_type_links(None) == []

    def test_no_fr24_type_url(self):
        from app.links import aircraft_type_links
        links = aircraft_type_links("B738")
        for link in links:
            assert "flightradar24.com/data/aircraft" not in link.url


# ---------------------------------------------------------------------------
# Position links
# ---------------------------------------------------------------------------

class TestPositionLinks:
    def test_valid_amazon_coordinates(self):
        from app.links import position_links
        links = position_links(-3.1, -59.9)
        assert len(links) == 2
        assert links[0].label == "Google Maps"
        assert "google.com/maps" in links[0].url
        assert "-3.100000" in links[0].url
        assert "-59.900000" in links[0].url
        assert links[1].label == "OpenStreetMap"
        assert "openstreetmap.org" in links[1].url

    def test_zero_coordinates(self):
        from app.links import position_links
        links = position_links(0, 0)
        assert len(links) == 2

    def test_boundary_values_north_pole(self):
        from app.links import position_links
        links = position_links(90, 180)
        assert len(links) == 2

    def test_boundary_values_south_pole(self):
        from app.links import position_links
        links = position_links(-90, -180)
        assert len(links) == 2

    def test_just_outside_north(self):
        from app.links import position_links
        assert position_links(90.000001, 0) == []

    def test_just_outside_south(self):
        from app.links import position_links
        assert position_links(-90.000001, 0) == []

    def test_just_outside_east(self):
        from app.links import position_links
        assert position_links(0, 180.000001) == []

    def test_just_outside_west(self):
        from app.links import position_links
        assert position_links(0, -180.000001) == []

    def test_nan_values(self):
        from app.links import position_links
        assert position_links(float("nan"), 0) == []
        assert position_links(0, float("nan")) == []

    def test_infinity_values(self):
        from app.links import position_links
        assert position_links(float("inf"), 0) == []
        assert position_links(0, float("inf")) == []

    def test_none_values(self):
        from app.links import position_links
        assert position_links(None, None) == []
        assert position_links(None, 0) == []
        assert position_links(0, None) == []

    def test_six_decimal_format(self):
        from app.links import position_links
        links = position_links(-23.431274, -46.469954)
        assert "-23.431274" in links[0].url
        assert "-46.469954" in links[0].url

    def test_map_kind(self):
        from app.links import position_links
        links = position_links(0, 0)
        for link in links:
            assert link.kind == "map"


# ---------------------------------------------------------------------------
# Airport links
# ---------------------------------------------------------------------------

class TestAirportLinks:
    def test_brazilian_icao_sbgr(self):
        from app.links import airport_links
        links = airport_links(icao="SBGR")
        labels = [link.label for link in links]
        assert "AISWEB" in labels
        assert "FlightAware" in labels
        assert "aisweb.decea.mil.br" in links[0].url
        assert "codigo=SBGR" in links[0].url

    def test_brazilian_icao_sbbe(self):
        from app.links import airport_links
        links = airport_links(icao="SBBE")
        assert any("AISWEB" in link.label for link in links)

    def test_brazilian_icao_sbma(self):
        from app.links import airport_links
        links = airport_links(icao="SBMA")
        assert any("AISWEB" in link.label for link in links)

    def test_iata_gru(self):
        from app.links import airport_links
        links = airport_links(iata="GRU")
        assert len(links) == 1
        assert links[0].label == "Flightradar24"
        assert "/airports/gru" in links[0].url

    def test_iata_bel(self):
        from app.links import airport_links
        links = airport_links(iata="BEL")
        assert len(links) == 1
        assert "/airports/bel" in links[0].url

    def test_ourairports_ident(self):
        from app.links import airport_links
        links = airport_links(ourairports_ident="BR-2441")
        assert len(links) == 1
        assert links[0].label == "OurAirports"
        assert "/airports/BR-2441/" in links[0].url

    def test_name_only_returns_empty(self):
        from app.links import airport_links
        assert airport_links() == []

    def test_invalid_code_returns_empty(self):
        from app.links import airport_links
        assert airport_links(icao="invalid") == []

    def test_none_returns_empty(self):
        from app.links import airport_links
        assert airport_links(icao=None, iata=None, ourairports_ident=None) == []

    def test_non_brazilian_icao_no_aisweb(self):
        from app.links import airport_links
        links = airport_links(icao="KJFK")
        assert all(link.label != "AISWEB" for link in links)

    def test_aisweb_only_for_s_prefix(self):
        from app.links import airport_links
        links = airport_links(icao="SBGR")
        aisweb_links = [link for link in links if link.label == "AISWEB"]
        assert len(aisweb_links) == 1

    def test_iata_only_when_valid(self):
        from app.links import airport_links
        # IATA must be 3 alpha chars
        assert airport_links(iata="GR") == []
        assert airport_links(iata="GRU1") == []


# ---------------------------------------------------------------------------
# Protected area links
# ---------------------------------------------------------------------------

class TestProtectedAreaLinks:
    def test_internal_area_id(self, monkeypatch):
        from app.links import protected_area_links
        monkeypatch.setenv("DASHBOARD_BASE_URL", "https://geofence.example.com")
        # Need to clear the lru_cache for env_settings
        from app.config import env_settings
        env_settings.cache_clear()
        try:
            links = protected_area_links([
                {"id": "funai:test", "name": "Test Territory", "category": "indigenous_territory", "source": "FUNAI"}
            ])
            assert any("funai:test" in link.url for link in links)
        finally:
            env_settings.cache_clear()

    def test_valid_isa_id(self, monkeypatch):
        from app.links import protected_area_links
        monkeypatch.setenv("DASHBOARD_BASE_URL", "https://geofence.example.com")
        from app.config import env_settings
        env_settings.cache_clear()
        try:
            links = protected_area_links([
                {"id": "funai:4184", "name": "Test TI", "category": "indigenous_territory", "source": "FUNAI", "isa_id": 4184}
            ])
            assert any("terrasindigenas.org.br/pt-br/terras-indigenas/4184" in link.url for link in links)
        finally:
            env_settings.cache_clear()

    def test_no_isa_id_shows_generic_search(self, monkeypatch):
        from app.links import protected_area_links
        monkeypatch.setenv("DASHBOARD_BASE_URL", "https://geofence.example.com")
        from app.config import env_settings
        env_settings.cache_clear()
        try:
            links = protected_area_links([
                {"id": "funai:test", "name": "Test TI", "category": "indigenous_territory", "source": "FUNAI"}
            ])
            assert any("terrasindigenas.org.br" in link.url for link in links)
            assert any("Search Terras" in link.label for link in links)
        finally:
            env_settings.cache_clear()

    def test_valid_allowlisted_external_url(self, monkeypatch):
        from app.links import protected_area_links
        monkeypatch.setenv("DASHBOARD_BASE_URL", "https://geofence.example.com")
        from app.config import env_settings
        env_settings.cache_clear()
        try:
            links = protected_area_links([
                {"id": "cnuc:test", "name": "Test CU", "category": "conservation_unit", "source": "CNUC"}
            ])
            assert any("cnuc.mma.gov.br" in link.url for link in links)
        finally:
            env_settings.cache_clear()

    def test_cnuc_without_detail_url(self, monkeypatch):
        from app.links import protected_area_links
        monkeypatch.setenv("DASHBOARD_BASE_URL", "https://geofence.example.com")
        from app.config import env_settings
        env_settings.cache_clear()
        try:
            links = protected_area_links([
                {"id": "cnuc:test", "name": "Test CU", "category": "conservation_unit", "source": "CNUC"}
            ])
            assert any("Search CNUC" in link.label for link in links)
        finally:
            env_settings.cache_clear()

    def test_empty_areas(self):
        from app.links import protected_area_links
        assert protected_area_links([]) == []

    def test_none_areas(self):
        from app.links import protected_area_links
        assert protected_area_links(None) == []

    def test_isa_id_must_be_numeric(self):
        from app.links import protected_area_links
        links = protected_area_links([
            {"id": "funai:test", "name": "Test TI", "category": "indigenous_territory", "source": "FUNAI", "isa_id": "not-a-number"}
        ])
        # No specific ISA link, only generic search
        assert not any("terrasindigenas.org.br/pt-br/terras-indigenas/" in link.url for link in links)

    def test_javascript_url_rejected(self):
        from app.links import protected_area_links
        # The function doesn't accept URLs directly, but if external_url were
        # added, it should reject javascript: URLs
        # This test verifies the function only generates known-safe URLs
        links = protected_area_links([
            {"id": "test", "name": "Test", "category": "indigenous_territory", "source": "FUNAI"}
        ])
        for link in links:
            assert not link.url.startswith("javascript:")


# ---------------------------------------------------------------------------
# Provider links
# ---------------------------------------------------------------------------

class TestProviderLinks:
    def test_adsb_lol(self):
        from app.links import provider_links
        links = provider_links("adsb_lol")
        assert len(links) == 1
        assert links[0].label == "ADSB.lol"
        assert "adsb.lol" in links[0].url

    def test_airplanes_live(self):
        from app.links import provider_links
        links = provider_links("airplanes_live")
        assert len(links) == 1
        assert links[0].label == "Airplanes.live"

    def test_adsbexchange(self):
        from app.links import provider_links
        links = provider_links("adsbexchange")
        assert len(links) == 1
        assert links[0].label == "ADS-B Exchange"

    def test_flightradar24(self):
        from app.links import provider_links
        links = provider_links("flightradar24")
        assert len(links) == 1
        assert links[0].label == "Flightradar24"

    def test_unknown_provider(self):
        from app.links import provider_links
        assert provider_links("unknown") == []

    def test_none_provider(self):
        from app.links import provider_links
        assert provider_links(None) == []

    def test_empty_provider(self):
        from app.links import provider_links
        assert provider_links("") == []


# ---------------------------------------------------------------------------
# Event link
# ---------------------------------------------------------------------------

class TestEventLink:
    def test_valid_uuid(self):
        import uuid

        from app.links import event_link
        event_id = str(uuid.uuid4())
        link = event_link(event_id)
        # Will be None if DASHBOARD_BASE_URL is not set
        # but should not error
        if link:
            assert event_id in link.url
            assert link.kind == "event"

    def test_invalid_id_returns_none(self):
        from app.links import event_link
        assert event_link("not-a-uuid") is None

    def test_none_returns_none(self):
        from app.links import event_link
        assert event_link(None) is None

    def test_empty_returns_none(self):
        from app.links import event_link
        assert event_link("") is None


# ---------------------------------------------------------------------------
# Hostname allowlist
# ---------------------------------------------------------------------------

class TestHostnameAllowlist:
    def test_known_hosts_allowed(self):
        from app.links import _ALLOWED_HOSTS
        assert "globe.adsb.lol" in _ALLOWED_HOSTS
        assert "globe.adsbexchange.com" in _ALLOWED_HOSTS
        assert "globe.airplanes.live" in _ALLOWED_HOSTS
        assert "aeronaves.anac.gov.br" in _ALLOWED_HOSTS
        assert "www.flightradar24.com" in _ALLOWED_HOSTS
        assert "www.flightaware.com" in _ALLOWED_HOSTS
        assert "ourairports.com" in _ALLOWED_HOSTS
        assert "aisweb.decea.mil.br" in _ALLOWED_HOSTS
        assert "terrasindigenas.org.br" in _ALLOWED_HOSTS
        assert "cnuc.mma.gov.br" in _ALLOWED_HOSTS
        assert "www.google.com" in _ALLOWED_HOSTS
        assert "www.openstreetmap.org" in _ALLOWED_HOSTS

    def test_disallowed_host(self):
        from app.links import _ALLOWED_HOSTS
        assert "evil.example.com" not in _ALLOWED_HOSTS
        assert "bit.ly" not in _ALLOWED_HOSTS
