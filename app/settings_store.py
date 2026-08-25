import base64
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from .config import env_settings
from .database import delete_db_setting, get_db_setting, set_db_setting
from .i18n import t


EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PROVIDER_CHOICES = ("adsb_lol", "airplanes_live", "adsbexchange", "flightradar24")


def _lang() -> str:
    return str(get_setting("language") or "pt")


@dataclass(frozen=True)
class SettingDef:
    env: str
    default: Any
    kind: str = "string"
    secret: bool = False
    choices: tuple[str, ...] = ()
    item_choices: tuple[str, ...] = ()
    minimum: float | None = None
    maximum: float | None = None


SETTING_DEFS: dict[str, SettingDef] = {
    "language": SettingDef("LANGUAGE", "en", choices=("en", "pt")),
    "timezone": SettingDef(
        "TIMEZONE", "America/Sao_Paulo",
        choices=("UTC", "America/Sao_Paulo", "America/Manaus", "America/Belem", "America/Rio_Branco", "America/Noronha")
    ),
    "operating_phase": SettingDef(
        "OPERATING_PHASE", "shadow", choices=("shadow", "review", "live")
    ),
    "flight_providers": SettingDef(
        "FLIGHT_PROVIDERS", ["adsb_lol"], kind="list", item_choices=PROVIDER_CHOICES
    ),
    "alert_recipients": SettingDef(
        "ALERT_RECIPIENTS", ["luandro@gmail.com"], kind="email_list"
    ),
    "dashboard_base_url": SettingDef("DASHBOARD_BASE_URL", ""),
    "email_provider": SettingDef(
        "EMAIL_PROVIDER", "console", choices=("console", "resend", "smtp")
    ),
    "email_from": SettingDef("EMAIL_FROM", "Flight Monitor <onboarding@resend.dev>"),
    "resend_api_key": SettingDef("RESEND_API_KEY", "", secret=True),
    "flightradar24_api_key": SettingDef("FLIGHTRADAR24_API_KEY", "", secret=True),
    "adsbexchange_api_key": SettingDef("ADSBEXCHANGE_API_KEY", "", secret=True),
    "fr24_enabled": SettingDef("FR24_ENABLED", False, kind="bool"),
    "fr24_plan": SettingDef("FR24_PLAN", "explorer", choices=("explorer",)),
    "fr24_plan_monthly_credits": SettingDef(
        "FR24_PLAN_MONTHLY_CREDITS", 30000, kind="int", minimum=1, maximum=10000000
    ),
    "fr24_monthly_operating_budget": SettingDef(
        "FR24_MONTHLY_OPERATING_BUDGET", 28000, kind="int", minimum=1, maximum=10000000
    ),
    "fr24_promotional_credits": SettingDef(
        "FR24_PROMOTIONAL_CREDITS", 0, kind="int", minimum=0, maximum=10000000
    ),
    "fr24_budget_policy": SettingDef(
        "FR24_BUDGET_POLICY",
        "pause_fr24",
        choices=("warn_only", "pause_fr24", "continue_until_provider_rejects"),
    ),
    "fr24_poll_interval_seconds": SettingDef(
        # Minimum matches the documented design cadence (FLIGHTRADAR_API.md sec. 7).
        # Below 300s, two clusters exceed the Explorer allocation from empty polls
        # alone, before a single aircraft is ever returned.
        "FR24_POLL_INTERVAL_SECONDS", 300, kind="int", minimum=300, maximum=86400
    ),
    "fr24_inter_cluster_delay_seconds": SettingDef(
        "FR24_INTER_CLUSTER_DELAY_SECONDS", 2, kind="int", minimum=0, maximum=60
    ),
    "fr24_response_limit": SettingDef(
        # Maximum matches the Explorer plan's documented hard cap (FLIGHTRADAR_API.md
        # sec. 2/9). A higher value here would misestimate credits and corrupt
        # possibly_truncated detection once the provider clamps or rejects it.
        "FR24_RESPONSE_LIMIT", 20, kind="int", minimum=1, maximum=20
    ),
    "fr24_summary_variant": SettingDef(
        "FR24_SUMMARY_VARIANT", "full", choices=("full", "light")
    ),
    "fr24_default_categories": SettingDef(
        "FR24_DEFAULT_CATEGORIES",
        ["T", "H", "N"],
        kind="list",
        item_choices=("P", "C", "M", "J", "T", "H", "B", "G", "D", "V", "O", "N"),
        minimum=1,
    ),
    "fr24_default_min_altitude_ft": SettingDef(
        "FR24_DEFAULT_MIN_ALTITUDE_FT", -2000.0, kind="float", minimum=-2000, maximum=60000
    ),
    "fr24_default_max_altitude_ft": SettingDef(
        "FR24_DEFAULT_MAX_ALTITUDE_FT", 10000.0, kind="float", minimum=-2000, maximum=60000
    ),
    "fr24_cluster_buffer_km": SettingDef(
        "FR24_CLUSTER_BUFFER_KM", 15.0, kind="float", minimum=1, maximum=100
    ),
    "fr24_fetch_summary_on_entry": SettingDef(
        "FR24_FETCH_SUMMARY_ON_ENTRY", True, kind="bool"
    ),
    "fr24_usage_sync_enabled": SettingDef("FR24_USAGE_SYNC_ENABLED", True, kind="bool"),
    # Defaults off: FLIGHTRADAR_API.md sec. 17's 30-day deletion requirement
    # has a written-agreement exception, and this deployment's operator has
    # confirmed governmental authority to retain FR24 data indefinitely.
    # Deletion never happens silently -- an operator must explicitly opt in.
    "fr24_auto_delete_enabled": SettingDef("FR24_AUTO_DELETE_ENABLED", False, kind="bool"),
    "smtp_host": SettingDef("SMTP_HOST", "smtp.gmail.com"),
    "smtp_port": SettingDef("SMTP_PORT", 587, kind="int", minimum=1, maximum=65535),
    "smtp_username": SettingDef("SMTP_USERNAME", ""),
    "smtp_password": SettingDef("SMTP_PASSWORD", "", secret=True),
    "smtp_starttls": SettingDef("SMTP_STARTTLS", True, kind="bool"),
    "poll_interval_seconds": SettingDef(
        "POLL_INTERVAL_SECONDS", 300, kind="int", minimum=30, maximum=86400
    ),
    "min_inside_observations_for_stop": SettingDef(
        "MIN_INSIDE_OBSERVATIONS_FOR_STOP", 3, kind="int", minimum=2, maximum=100
    ),
    "stop_min_duration_seconds": SettingDef(
        "STOP_MIN_DURATION_SECONDS", 120, kind="int", minimum=30, maximum=86400
    ),
    "stationary_radius_meters": SettingDef(
        "STATIONARY_RADIUS_METERS", 500.0, kind="float", minimum=25, maximum=10000
    ),
    "stop_max_speed_kt": SettingDef(
        "STOP_MAX_SPEED_KT", 20.0, kind="float", minimum=0, maximum=150
    ),
    "min_inside_observations_for_disappearance": SettingDef(
        "MIN_INSIDE_OBSERVATIONS_FOR_DISAPPEARANCE",
        2,
        kind="int",
        minimum=2,
        maximum=100,
    ),
    "disappear_after_successful_polls": SettingDef(
        "DISAPPEAR_AFTER_SUCCESSFUL_POLLS", 3, kind="int", minimum=1, maximum=100
    ),
    "disappear_max_altitude_ft": SettingDef(
        "DISAPPEAR_MAX_ALTITUDE_FT", 6000.0, kind="float", minimum=0, maximum=60000
    ),
    "outside_confirmation_observations": SettingDef(
        "OUTSIDE_CONFIRMATION_OBSERVATIONS", 2, kind="int", minimum=1, maximum=10
    ),
    "max_emails_per_day": SettingDef(
        "MAX_EMAILS_PER_DAY", 50, kind="int", minimum=1, maximum=10000
    ),
}


def _fernet() -> Fernet:
    digest = hashlib.sha256(env_settings().app_secret_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _split_list(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return list(dict.fromkeys(str(x).strip() for x in raw if str(x).strip()))
    try:
        parsed = json.loads(str(raw))
        if isinstance(parsed, list):
            return list(dict.fromkeys(str(x).strip() for x in parsed if str(x).strip()))
    except (TypeError, ValueError, json.JSONDecodeError):
        pass
    return list(dict.fromkeys(x.strip() for x in str(raw).split(",") if x.strip()))


def _parse(raw: Any, definition: SettingDef) -> Any:
    if raw is None:
        return definition.default
    if definition.kind in {"list", "email_list"}:
        value = _split_list(raw)
    elif definition.kind == "int":
        value = int(raw)
    elif definition.kind == "float":
        value = float(raw)
    elif definition.kind == "bool":
        if isinstance(raw, bool):
            value = raw
        else:
            normalized = str(raw).strip().lower()
            if normalized not in {"true", "false", "1", "0", "yes", "no", "on", "off"}:
                raise ValueError(t("err_value_bool", _lang()))
            value = normalized in {"true", "1", "yes", "on"}
    else:
        value = str(raw).strip()

    if definition.choices and value not in definition.choices:
        raise ValueError(t("err_value_one_of", _lang()).replace("{choices}", ", ".join(definition.choices)))
    if definition.item_choices:
        unknown = sorted(set(value) - set(definition.item_choices))
        if unknown:
            raise ValueError(t("err_unsupported_list_values", _lang()).replace("{values}", ", ".join(unknown)))
        value = list(dict.fromkeys(value))
    # For list/email_list kinds, minimum/maximum bound the item count, not the
    # list itself -- an empty list can be a valid (or a dangerous) value
    # depending on the setting, so this must be explicit rather than falling
    # through to a comparison that would raise TypeError.
    bounded = len(value) if definition.kind in {"list", "email_list"} else value
    if definition.minimum is not None and bounded < definition.minimum:
        raise ValueError(t("err_value_min", _lang()).replace("{min}", f"{definition.minimum:g}"))
    if definition.maximum is not None and bounded > definition.maximum:
        raise ValueError(t("err_value_max", _lang()).replace("{max}", f"{definition.maximum:g}"))
    if definition.kind == "email_list":
        invalid = [address for address in value if not EMAIL_RE.match(address)]
        if invalid:
            raise ValueError(t("err_invalid_email", _lang()).replace("{emails}", ", ".join(invalid)))
        value = list(dict.fromkeys(address.lower() for address in value))
    return value


def _env_raw(definition: SettingDef) -> Any | None:
    # `model_fields_set` distinguishes an explicit environment/.env value from
    # the EnvSettings class default. This prevents a nonblank class default
    # (for example SMTP_STARTTLS=true) from being incorrectly shown as locked.
    settings = env_settings()
    attribute = definition.env.lower()
    if attribute not in settings.model_fields_set:
        return None
    value = getattr(settings, attribute, None)
    if value is None:
        return None
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


def get_setting(key: str) -> Any:
    definition = SETTING_DEFS[key]
    env_raw = _env_raw(definition)
    if env_raw is not None:
        return _parse(env_raw, definition)

    encrypted = get_db_setting(key)
    if encrypted:
        try:
            raw = _fernet().decrypt(encrypted.encode("ascii")).decode("utf-8")
            return _parse(json.loads(raw), definition)
        except (InvalidToken, ValueError, TypeError, json.JSONDecodeError):
            return definition.default
    return definition.default


def setting_source(key: str) -> str:
    definition = SETTING_DEFS[key]
    if _env_raw(definition) is not None:
        return "environment"
    if get_db_setting(key):
        return "interface"
    return "default"


def set_setting(key: str, value: Any) -> None:
    definition = SETTING_DEFS[key]
    if _env_raw(definition) is not None:
        raise ValueError(t("err_controlled_by_env", _lang()).replace("{key}", key).replace("{env}", definition.env))
    parsed = _parse(value, definition)
    token = _fernet().encrypt(json.dumps(parsed).encode("utf-8")).decode("ascii")
    set_db_setting(key, token)


def clear_setting(key: str) -> None:
    definition = SETTING_DEFS[key]
    if _env_raw(definition) is not None:
        raise ValueError(t("err_controlled_by_env", _lang()).replace("{key}", key).replace("{env}", definition.env))
    delete_db_setting(key)


def public_settings() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for key, definition in SETTING_DEFS.items():
        value = get_setting(key)
        source = setting_source(key)
        result[key] = {
            "value": None if definition.secret else value,
            "configured": bool(value) if definition.secret else True,
            "source": source,
            "locked": source == "environment",
            "secret": definition.secret,
            "choices": list(definition.choices),
            "kind": definition.kind,
            "minimum": definition.minimum,
            "maximum": definition.maximum,
        }
    return result
