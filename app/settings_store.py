import base64
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from .config import env_settings
from .database import delete_db_setting, get_db_setting, set_db_setting


EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PROVIDER_CHOICES = ("adsb_lol", "airplanes_live", "adsbexchange", "flightradar24")


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
    "email_provider": SettingDef(
        "EMAIL_PROVIDER", "console", choices=("console", "resend", "smtp")
    ),
    "email_from": SettingDef("EMAIL_FROM", "Flight Monitor <onboarding@resend.dev>"),
    "resend_api_key": SettingDef("RESEND_API_KEY", "", secret=True),
    "flightradar24_api_key": SettingDef("FLIGHTRADAR24_API_KEY", "", secret=True),
    "adsbexchange_api_key": SettingDef("ADSBEXCHANGE_API_KEY", "", secret=True),
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
                raise ValueError("Value must be true or false")
            value = normalized in {"true", "1", "yes", "on"}
    else:
        value = str(raw).strip()

    if definition.choices and value not in definition.choices:
        raise ValueError(f"Value must be one of: {', '.join(definition.choices)}")
    if definition.item_choices:
        unknown = sorted(set(value) - set(definition.item_choices))
        if unknown:
            raise ValueError(f"Unsupported list values: {', '.join(unknown)}")
        value = list(dict.fromkeys(value))
    if definition.minimum is not None and value < definition.minimum:
        raise ValueError(f"Value must be at least {definition.minimum:g}")
    if definition.maximum is not None and value > definition.maximum:
        raise ValueError(f"Value must be at most {definition.maximum:g}")
    if definition.kind == "email_list":
        invalid = [address for address in value if not EMAIL_RE.match(address)]
        if invalid:
            raise ValueError(f"Invalid email address(es): {', '.join(invalid)}")
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
        raise ValueError(f"{key} is controlled by environment variable {definition.env}")
    parsed = _parse(value, definition)
    token = _fernet().encrypt(json.dumps(parsed).encode("utf-8")).decode("ascii")
    set_db_setting(key, token)


def clear_setting(key: str) -> None:
    definition = SETTING_DEFS[key]
    if _env_raw(definition) is not None:
        raise ValueError(f"{key} is controlled by environment variable {definition.env}")
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
