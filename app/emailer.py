import asyncio
import html as html_mod
import logging
import smtplib
import urllib.parse
from datetime import datetime, timezone, timedelta
from email.message import EmailMessage
from email.utils import parseaddr

import httpx

from .config import env_settings
from .database import email_count_today
from .i18n import t, get_aircraft_type_url, translate_event_type, translate_classification
from .settings_store import get_setting

logger = logging.getLogger(__name__)

# Timezone offsets
TIMEZONE_OFFSETS = {
    "UTC": 0,
    "America/Sao_Paulo": -3,
    "America/Manaus": -4,
    "America/Belem": -3,
    "America/Rio_Branco": -5,
    "America/Noronha": -2,
}


def _get_registration_url(registration: str | None) -> str | None:
    """Get a URL for aircraft registration lookup."""
    if not registration:
        return None
    reg = registration.upper().replace("-", "")
    # For Brazilian registrations (PT-XXX), link to ANAC SIGA
    if reg.startswith("PT"):
        return "https://www.gov.br/anac/pt-br/assuntos/registro-aeronaves"
    # For other registrations, link to FlightRadar24
    return f"https://www.flightradar24.com/data/aircraft/{reg.lower()}"


def _format_time(iso_string: str, timezone_offset: int = -3) -> str:
    """Format ISO time string to human-readable format with timezone."""
    try:
        dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
        # Apply timezone offset
        tz = timezone(timedelta(hours=timezone_offset))
        dt_local = dt.astimezone(tz)

        # Portuguese day names
        day_names = ["Domingo", "Segunda-feira", "Terça-feira", "Quarta-feira",
                     "Quinta-feira", "Sexta-feira", "Sábado"]

        day_name = day_names[dt_local.weekday()]
        day = dt_local.day
        month = dt_local.month
        year = dt_local.year
        time_str = dt_local.strftime("%H:%M")

        return f"{day_name} {day:02d}/{month:02d}/{year} às {time_str}"
    except (ValueError, TypeError):
        return iso_string


def _get_timezone_offset() -> int:
    """Get configured timezone offset."""
    tz_name = str(get_setting("timezone") or "America/Sao_Paulo")
    return TIMEZONE_OFFSETS.get(tz_name, -3)


def _subject(event: dict) -> str:
    lang = str(get_setting("language") or "pt")
    label = translate_event_type(event["event_type"], lang)
    return f"{label} — {event['aircraft_hex'].upper()}"


def _plain(event: dict) -> str:
    lang = str(get_setting("language") or "pt")
    tz_offset = _get_timezone_offset()
    areas = ", ".join(event["area_names"])
    details = event.get("details") or {}

    aircraft_type = event.get("aircraft_type") or t("email_unavailable", lang)
    callsign = event.get("callsign") or t("email_unavailable", lang)
    registration = event.get("registration") or t("email_unavailable", lang)
    altitude = event.get("altitude_ft")
    speed = event.get("ground_speed_kt")

    classification = translate_classification(event.get("airline_classification", ""), lang)

    return f"""{t("email_title", lang)}

{t("email_event", lang)}: {translate_event_type(event["event_type"], lang)}
{t("email_aircraft", lang)}: {event["aircraft_hex"].upper()}
{t("email_callsign", lang)}: {callsign}
{t("email_registration", lang)}: {registration}
{t("email_aircraft_type", lang)}: {aircraft_type}
{t("email_protected_areas", lang)}: {areas}
{t("email_time", lang)}: {_format_time(event["occurred_at"], tz_offset)}
{t("email_last_position", lang)}: {event.get("latitude")}, {event.get("longitude")}
{t("email_altitude", lang)}: {altitude if altitude is not None else t("email_unavailable", lang)} ft MSL
{t("email_ground_speed", lang)}: {speed if speed is not None else t("email_unavailable", lang)} kt
{t("email_provider", lang)}: {event["provider"]}
{t("email_source_type", lang)}: {details.get("source_type") or t("email_unavailable", lang)}
{t("email_origin", lang)}: {details.get("origin") or t("email_unavailable", lang)}
{t("email_destination", lang)}: {details.get("destination") or t("email_unavailable", lang)}
{t("email_reason", lang)}: {event["reason"]}
{t("email_classification", lang)}: {classification}

{t("email_disclaimer", lang)}
"""


def _html(event: dict) -> str:
    lang = str(get_setting("language") or "pt")
    tz_offset = _get_timezone_offset()
    areas = ", ".join(event["area_names"])
    details = event.get("details") or {}

    aircraft_type = event.get("aircraft_type")
    callsign = event.get("callsign") or t("email_unavailable", lang)
    registration = event.get("registration") or t("email_unavailable", lang)
    altitude = event.get("altitude_ft")
    speed = event.get("ground_speed_kt")

    # Build clickable aircraft type link
    aircraft_type_display = aircraft_type or t("email_unavailable", lang)
    if aircraft_type:
        aircraft_type_url = get_aircraft_type_url(urllib.parse.quote(str(aircraft_type)))
        aircraft_type_display = f'<a href="{aircraft_type_url}" style="color:#174c3c;text-decoration:underline">{html_mod.escape(aircraft_type)}</a>'

    # Build hex code link
    hex_code = event["aircraft_hex"].upper()
    hex_url = f"https://www.flightradar24.com/data/aircraft/{event['aircraft_hex'].lower()}"

    # Build registration link
    reg_url = _get_registration_url(registration)
    registration_display = html_mod.escape(registration) if registration else t("email_unavailable", lang)
    if reg_url:
        registration_display = f'<a href="{reg_url}" style="color:#174c3c;text-decoration:underline">{html_mod.escape(registration)}</a>'

    classification = translate_classification(event.get("airline_classification", ""), lang)

    # Build callsign link
    callsign_display = html_mod.escape(callsign)
    if event.get("callsign"):
        callsign_url = f"https://www.flightradar24.com/data/callsigns/{event['callsign'].lower()}"
        callsign_display = f'<a href="{callsign_url}" style="color:#174c3c;text-decoration:underline">{html_mod.escape(callsign)}</a>'

    # Build origin/destination links
    origin = details.get("origin") or ""
    destination = details.get("destination") or ""
    origin_display = html_mod.escape(origin) if origin else t("email_unavailable", lang)
    destination_display = html_mod.escape(destination) if destination else t("email_unavailable", lang)
    if origin:
        origin_url = f"https://www.google.com/maps/search/{html_mod.escape(origin)}+airport"
        origin_display = f'<a href="{origin_url}" style="color:#174c3c;text-decoration:underline">{html_mod.escape(origin)}</a>'
    if destination:
        destination_url = f"https://www.google.com/maps/search/{html_mod.escape(destination)}+airport"
        destination_display = f'<a href="{destination_url}" style="color:#174c3c;text-decoration:underline">{html_mod.escape(destination)}</a>'

    # Build provider link
    provider = event.get("provider", "")
    provider_urls = {
        "adsb_lol": "https://adsb.lol",
        "airplanes_live": "https://airplanes.live",
        "adsbexchange": "https://www.adsbexchange.com",
        "flightradar24": "https://www.flightradar24.com",
    }
    provider_display = html_mod.escape(provider) if provider else t("email_unavailable", lang)
    if provider in provider_urls:
        provider_display = f'<a href="{provider_urls[provider]}" style="color:#174c3c;text-decoration:underline">{html_mod.escape(provider)}</a>'

    # Build protected areas link to ISA
    areas_display = html_mod.escape(areas) if areas else t("email_unavailable", lang)
    if areas:
        areas_display = f'<a href="https://www.socioambiental.org/" style="color:#174c3c;text-decoration:underline">{html_mod.escape(areas)}</a>'

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;max-width:720px;margin:auto;padding:20px;background:#f4f0e9">
<div style="background:white;border-radius:12px;padding:24px;box-shadow:0 4px 12px rgba(0,0,0,0.08)">
<h2 style="color:#6b2847;margin-top:0">{t("email_title", lang)}</h2>
<table style="width:100%;border-collapse:collapse;font-size:14px">
<tr><td style="padding:8px 0;color:#746a70;width:140px">{t("email_event", lang)}</td><td style="padding:8px 0"><strong>{translate_event_type(event["event_type"], lang)}</strong></td></tr>
<tr><td style="padding:8px 0;color:#746a70">{t("email_aircraft", lang)}</td><td style="padding:8px 0"><strong><a href="{hex_url}" style="color:#174c3c;text-decoration:underline">{hex_code}</a></strong></td></tr>
<tr><td style="padding:8px 0;color:#746a70">{t("email_callsign", lang)}</td><td style="padding:8px 0">{callsign_display}</td></tr>
<tr><td style="padding:8px 0;color:#746a70">{t("email_registration", lang)}</td><td style="padding:8px 0">{registration_display}</td></tr>
<tr><td style="padding:8px 0;color:#746a70">{t("email_aircraft_type", lang)}</td><td style="padding:8px 0">{aircraft_type_display}</td></tr>
<tr><td style="padding:8px 0;color:#746a70">{t("email_protected_areas", lang)}</td><td style="padding:8px 0">{areas_display}</td></tr>
<tr><td style="padding:8px 0;color:#746a70">{t("email_time", lang)}</td><td style="padding:8px 0">{_format_time(event["occurred_at"], tz_offset)}</td></tr>
<tr><td style="padding:8px 0;color:#746a70">{t("email_last_position", lang)}</td><td style="padding:8px 0"><a href="https://www.google.com/maps?q={urllib.parse.quote(str(event.get("latitude", "")))},{urllib.parse.quote(str(event.get("longitude", "")))}" style="color:#174c3c;text-decoration:underline">{html_mod.escape(str(event.get("latitude", "")))}, {html_mod.escape(str(event.get("longitude", "")))}</a></td></tr>
<tr><td style="padding:8px 0;color:#746a70">{t("email_altitude", lang)}</td><td style="padding:8px 0">{altitude if altitude is not None else t("email_unavailable", lang)} ft MSL</td></tr>
<tr><td style="padding:8px 0;color:#746a70">{t("email_ground_speed", lang)}</td><td style="padding:8px 0">{speed if speed is not None else t("email_unavailable", lang)} kt</td></tr>
<tr><td style="padding:8px 0;color:#746a70">{t("email_provider", lang)}</td><td style="padding:8px 0">{provider_display}</td></tr>
<tr><td style="padding:8px 0;color:#746a70">{t("email_source_type", lang)}</td><td style="padding:8px 0">{html_mod.escape(details.get("source_type") or t("email_unavailable", lang))}</td></tr>
<tr><td style="padding:8px 0;color:#746a70">{t("email_origin", lang)}</td><td style="padding:8px 0">{origin_display}</td></tr>
<tr><td style="padding:8px 0;color:#746a70">{t("email_destination", lang)}</td><td style="padding:8px 0">{destination_display}</td></tr>
<tr><td style="padding:8px 0;color:#746a70">{t("email_reason", lang)}</td><td style="padding:8px 0">{html_mod.escape(event["reason"])}</td></tr>
<tr><td style="padding:8px 0;color:#746a70">{t("email_classification", lang)}</td><td style="padding:8px 0">{html_mod.escape(classification)}</td></tr>
</table>
<div style="margin-top:20px;padding:16px;background:#f4f0e9;border-radius:8px;font-size:12px;color:#746a70">
{t("email_disclaimer", lang)}
</div>
<div style="margin-top:16px;font-size:11px;color:#746a70;text-align:center">
{t("email_footer", lang)}
</div>
</div>
</body>
</html>"""


def _valid_sender(value: str) -> bool:
    _, address = parseaddr(value)
    return bool(address and "@" in address and "." in address.rsplit("@", 1)[-1])


def _smtp_send(event: dict, sender: str, recipients: list[str]) -> None:
    host = str(get_setting("smtp_host"))
    port = int(get_setting("smtp_port"))
    username = str(get_setting("smtp_username"))
    password = str(get_setting("smtp_password"))
    if not host or not username or not password:
        raise RuntimeError("SMTP host, username or password is missing")
    message = EmailMessage()
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message["Subject"] = _subject(event)
    message["Message-ID"] = f"<{event['id']}@flight-geofence.local>"
    message.set_content(_plain(event))
    message.add_alternative(_html(event), subtype="html")
    with smtplib.SMTP(host, port, timeout=30) as server:
        if bool(get_setting("smtp_starttls")):
            server.starttls()
        server.login(username, password)
        server.send_message(message)


async def send_event_email(event: dict) -> tuple[str, str | None]:
    if email_count_today() >= int(get_setting("max_emails_per_day")):
        return "suppressed", "Daily email cap reached"
    recipients = list(get_setting("alert_recipients"))
    if not recipients:
        return "failed", "No alert recipients configured"
    provider = str(get_setting("email_provider")).lower()
    sender = str(get_setting("email_from"))
    if not _valid_sender(sender):
        return "failed", "EMAIL_FROM is not a valid sender address"

    if provider == "console":
        logger.info(
            "EMAIL PREVIEW to=%s subject=%s\n%s",
            ",".join(recipients),
            _subject(event),
            _plain(event),
        )
        return "previewed", None

    if provider == "resend":
        key = get_setting("resend_api_key")
        if not key:
            return "failed", "Resend API key is missing"
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    "https://api.resend.com/emails",
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                        "Idempotency-Key": event["id"],
                    },
                    json={
                        "from": sender,
                        "to": recipients,
                        "subject": _subject(event),
                        "text": _plain(event),
                        "html": _html(event),
                    },
                )
                response.raise_for_status()
            return "sent", None
        except Exception as exc:
            logger.warning("Resend delivery failed for %s: %s", event["id"], exc)
            return "failed", str(exc)

    if provider == "smtp":
        try:
            await asyncio.to_thread(_smtp_send, event, sender, recipients)
            return "sent", None
        except Exception as exc:
            logger.warning("SMTP delivery failed for %s: %s", event["id"], exc)
            return "failed", str(exc)

    return "failed", f"Unsupported email provider: {provider}"
