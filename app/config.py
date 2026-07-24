from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class EnvSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        case_sensitive=False,
    )

    admin_password: str = "change-this-password"
    app_secret_key: str = "replace-with-a-long-random-secret-at-least-32-characters"
    bind_address: str = "127.0.0.1"
    app_port: int = 8080
    session_https_only: bool = False
    trusted_hosts: str = "localhost,127.0.0.1"
    allow_insecure_defaults: bool = False
    dashboard_base_url: str = ""

    operating_phase: str = ""
    flight_providers: str = ""
    alert_recipients: str = ""
    email_provider: str = ""
    email_from: str = ""
    resend_api_key: str = ""
    flightradar24_api_key: str = ""
    adsbexchange_api_key: str = ""

    database_path: str = "/data/runtime/flight_alerts.db"
    download_dir: str = "/data/downloads"
    boundary_sync_enabled: bool = True
    boundary_sync_interval_days: int = 7
    boundary_sync_check_hours: int = 6
    target_states: str = "PA,AM,AP,RR"
    neighbor_distance_km: float = 10
    auto_select_all_on_first_sync: bool = True
    auto_select_new_areas_when_all_selected: bool = True
    funai_wfs_url: str = "https://geoserver.funai.gov.br/geoserver/Funai/ows"
    funai_wfs_typename: str = "Funai:tis_poligonais"
    funai_user_agent: str = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
    )
    icmbio_wfs_url: str = "https://geoservicos.inde.gov.br/geoserver/ICMBio/ows"
    icmbio_wfs_typename: str = "ICMBio:limiteucsfederais_a"
    raisg_anps_url: str = (
        "https://geo2.socioambiental.org/raisg/rest/services/raisg/raisg_anps_N/MapServer/2/query"
    )
    mma_ckan_package_url: str = (
        "https://dados.mma.gov.br/api/3/action/package_show"
        "?id=44b6dc8a-dc82-4a84-8d95-1b0da7c85dac"
    )
    cnuc_fallback_url: str = (
        "https://dados.mma.gov.br/dataset/44b6dc8a-dc82-4a84-8d95-1b0da7c85dac/"
        "resource/b1f7a269-a0b2-4a81-9ac5-108905e74a00/download/shp_cnuc_2026_03.zip"
    )
    max_download_mb: int = 750
    max_extracted_mb: int = 2500
    max_zip_members: int = 20000
    boundary_min_territories: int = 20
    boundary_min_conservation_units: int = 5

    poll_interval_seconds: str = ""
    query_radius_nm: float = 200
    query_spacing_factor: float = 1.0
    max_query_regions: int = 250
    observation_buffer_km: float = 25
    api_request_delay_ms: int = 750
    position_max_age_seconds: int = 150
    http_timeout_seconds: int = 40
    user_agent: str = "flight-geofence-poc/0.4 contact=luandro@gmail.com"
    scheduler_initial_delay_seconds: int = 20
    state_retention_days: int = 14
    fr24_retention_days: int = 29

    min_inside_observations_for_stop: str = ""
    stop_min_duration_seconds: str = ""
    stationary_radius_meters: str = ""
    stop_max_speed_kt: str = ""
    min_inside_observations_for_disappearance: str = ""
    disappear_after_successful_polls: str = ""
    disappear_max_altitude_ft: str = ""
    outside_confirmation_observations: str = ""
    max_emails_per_day: str = ""

    smtp_host: str = ""
    smtp_port: str = ""
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_starttls: str = ""

    airline_callsign_prefixes: str = (
        "AZU,GLO,TAM,PTB,AEA,AFR,AVA,BAW,CMP,DAL,DLH,IBE,KLM,UAL"
    )
    airliner_types: str = (
        "A20N,A319,A320,A321,A332,A333,A339,B737,B738,B739,B38M,B39M,"
        "B744,B748,B752,B763,B772,B77W,B788,B789,E190,E195,E290,E295,AT72"
    )

    @field_validator("query_radius_nm")
    @classmethod
    def validate_query_radius(cls, value: float) -> float:
        if not 10 <= value <= 250:
            raise ValueError("QUERY_RADIUS_NM must be between 10 and 250")
        return value

    @field_validator("query_spacing_factor")
    @classmethod
    def validate_spacing(cls, value: float) -> float:
        if not 0.65 <= value <= 1.0:
            raise ValueError("QUERY_SPACING_FACTOR must be between 0.65 and 1.0")
        return value

    @property
    def target_state_list(self) -> list[str]:
        return [x.strip().upper() for x in self.target_states.split(",") if x.strip()]

    @property
    def trusted_host_list(self) -> list[str]:
        return [x.strip() for x in self.trusted_hosts.split(",") if x.strip()]

    @property
    def airline_prefix_set(self) -> set[str]:
        return {
            x.strip().upper()
            for x in self.airline_callsign_prefixes.split(",")
            if x.strip()
        }

    @property
    def airliner_type_set(self) -> set[str]:
        return {
            x.strip().upper()
            for x in self.airliner_types.split(",")
            if x.strip()
        }

    def validate_runtime_security(self) -> None:
        insecure_password = (
            self.admin_password == "change-this-password"
            or len(self.admin_password) < 12
        )
        insecure_secret = (
            self.app_secret_key.startswith("replace-with")
            or len(self.app_secret_key) < 32
        )
        insecure_host_config = (
            not self.trusted_host_list or "*" in self.trusted_host_list
        )
        externally_bound_without_secure_cookie = (
            self.bind_address not in {"127.0.0.1", "localhost", "::1"}
            and not self.session_https_only
        )
        if (
            insecure_password
            or insecure_secret
            or insecure_host_config
            or externally_bound_without_secure_cookie
        ) and not self.allow_insecure_defaults:
            raise RuntimeError(
                "Refusing insecure runtime settings. Use an ADMIN_PASSWORD of at least "
                "12 characters, an APP_SECRET_KEY of at least 32 characters, an explicit "
                "TRUSTED_HOSTS allowlist, and SESSION_HTTPS_ONLY=true when binding beyond "
                "localhost. ALLOW_INSECURE_DEFAULTS=true is only for isolated evaluation."
            )
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        Path(self.download_dir).mkdir(parents=True, exist_ok=True)


@lru_cache
def env_settings() -> EnvSettings:
    return EnvSettings()
