import asyncio
import html as html_mod
import logging
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import parseaddr

import httpx

from .database import email_count_today
from .i18n import t, translate_classification, translate_event_type, translate_weekday
from .links import (
    aircraft_hex_links,
    aircraft_type_links,
    airport_links,
    callsign_links,
    event_link,
    flight_number_links,
    position_links,
    protected_area_links,
    provider_links,
    registration_links,
)
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


def _format_time(iso_string: str, timezone_offset: int = -3, lang: str = "pt") -> str:
    """Format ISO time string to human-readable format with timezone."""
    try:
        dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
        tz = timezone(timedelta(hours=timezone_offset))
        dt_local = dt.astimezone(tz)

        # weekday(): Monday=0..Sunday=6; translate_weekday expects Sunday=0
        day_index = (dt_local.weekday() + 1) % 7
        day_name = translate_weekday(day_index, lang)
        day = dt_local.day
        month = dt_local.month
        year = dt_local.year
        time_str = dt_local.strftime("%H:%M")
        separator = t("time_at", lang)

        return f"{day_name} {day:02d}/{month:02d}/{year}{separator}{time_str}"
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


def _link_list_text(links: list, lang: str = "pt") -> str:
    """Format a list of InvestigationLinks as 'label · label' text."""
    return " · ".join(f"{link.label}: {link.url}" for link in links) if links else ""


def _link_list_html(links: list) -> str:
    """Format a list of InvestigationLinks as HTML 'label · label'."""
    parts = []
    for link in links:
        parts.append(
            f'<a href="{html_mod.escape(link.url)}" '
            f'style="color:#174c3c;text-decoration:underline" '
            f'rel="noopener noreferrer">{html_mod.escape(link.label)}</a>'
        )
    return " · ".join(parts) if parts else ""


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

    # Build links via centralized builder
    evt_link = event_link(event.get("id", ""))
    hex_links = aircraft_hex_links(event.get("aircraft_hex"), event.get("provider"), event.get("occurred_at"))
    cs_links = callsign_links(event.get("callsign"))
    fn_links = flight_number_links(event.get("flight_number"))
    reg_links = registration_links(event.get("registration"))
    pos_links = position_links(event.get("latitude"), event.get("longitude"))
    provider_lks = provider_links(event.get("provider"))

    # Airport links
    origin_links = airport_links(
        icao=details.get("origin_icao"),
        iata=details.get("origin_iata"),
        ourairports_ident=details.get("origin_ident"),
    )
    dest_links = airport_links(
        icao=details.get("destination_icao"),
        iata=details.get("destination_iata"),
        ourairports_ident=details.get("destination_ident"),
    )

    # Protected area links
    area_dicts = []
    area_ids = event.get("area_ids", [])
    area_names = event.get("area_names", [])
    for i, name in enumerate(area_names):
        area_dicts.append({"id": area_ids[i] if i < len(area_ids) else "", "name": name, "category": "", "source": ""})

    # Build external tracking disclaimer
    ext_note = t("email_external_tracking_note", lang) if t("email_external_tracking_note", lang) != "email_external_tracking_note" else (
        "External tracking services may not currently have a position or record for every aircraft."
    )

    lines = [
        t("email_title", lang),
        "",
        t("email_event", lang) + ": " + translate_event_type(event["event_type"], lang),
        t("email_aircraft", lang) + ": " + event["aircraft_hex"].upper(),
    ]

    if evt_link:
        lines.append(t("email_open_event", lang) + ": " + evt_link.url)
        lines.append("")

    lines.append(t("email_callsign", lang) + ": " + callsign)
    if cs_links:
        lines.append("  " + _link_list_text(cs_links, lang))

    if event.get("flight_number"):
        lines.append(t("email_flight_number", lang) + ": " + event["flight_number"])
        if fn_links:
            lines.append("  " + _link_list_text(fn_links, lang))

    lines.append(t("email_registration", lang) + ": " + registration)
    if reg_links:
        lines.append("  " + _link_list_text(reg_links, lang))

    lines.append(t("email_aircraft_type", lang) + ": " + aircraft_type)
    at_links = aircraft_type_links(event.get("aircraft_type"))
    if at_links:
        lines.append("  " + _link_list_text(at_links, lang))

    lines.append(t("email_protected_areas", lang) + ": " + areas)
    if area_dicts:
        area_links = protected_area_links(area_dicts)
        if area_links:
            lines.append("  " + _link_list_text(area_links, lang))

    lines.append(t("email_time", lang) + ": " + _format_time(event["occurred_at"], tz_offset, lang))

    lat_val = event.get("latitude")
    lng_val = event.get("longitude")
    if lat_val is not None and lng_val is not None:
        lat_f = float(lat_val)
        lng_f = float(lng_val)
        lines.append(t("email_last_position", lang) + f": {lat_f:.6f}, {lng_f:.6f}")
        if pos_links:
            lines.append("  " + _link_list_text(pos_links, lang))

    lines.append(t("email_altitude", lang) + ": " + (
        f"{altitude} ft MSL" if altitude is not None else t("email_unavailable", lang)
    ))
    lines.append(t("email_ground_speed", lang) + ": " + (
        f"{speed} kt" if speed is not None else t("email_unavailable", lang)
    ))
    lines.append(t("email_provider", lang) + ": " + event["provider"])
    if provider_lks:
        lines.append("  " + _link_list_text(provider_lks, lang))

    lines.append(t("email_source_type", lang) + ": " + (details.get("source_type") or t("email_unavailable", lang)))
    lines.append(t("email_origin", lang) + ": " + (details.get("origin") or t("email_unavailable", lang)))
    if origin_links:
        lines.append("  " + _link_list_text(origin_links, lang))

    lines.append(t("email_destination", lang) + ": " + (details.get("destination") or t("email_unavailable", lang)))
    if dest_links:
        lines.append("  " + _link_list_text(dest_links, lang))

    lines.append(t("email_reason", lang) + ": " + event["reason"])
    lines.append(t("email_classification", lang) + ": " + classification)

    if hex_links:
        lines.append("")
        lines.append(t("email_tracking_services", lang) + ":")
        for link in hex_links:
            lines.append(f"  {link.label}: {link.url}")

    lines.append("")
    lines.append(ext_note)
    lines.append("")
    lines.append(t("email_disclaimer", lang))

    return "\n".join(lines) + "\n"


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
    classification = translate_classification(event.get("airline_classification", ""), lang)

    # Build links via centralized builder
    evt_link = event_link(event.get("id", ""))
    hex_links = aircraft_hex_links(event.get("aircraft_hex"), event.get("provider"), event.get("occurred_at"))
    cs_links = callsign_links(event.get("callsign"))
    fn_links = flight_number_links(event.get("flight_number"))
    reg_links = registration_links(event.get("registration"))
    pos_links = position_links(event.get("latitude"), event.get("longitude"))
    provider_lks = provider_links(event.get("provider"))

    # Airport links
    origin_links = airport_links(
        icao=details.get("origin_icao"),
        iata=details.get("origin_iata"),
        ourairports_ident=details.get("origin_ident"),
    )
    dest_links = airport_links(
        icao=details.get("destination_icao"),
        iata=details.get("destination_iata"),
        ourairports_ident=details.get("destination_ident"),
    )

    # Protected area links
    area_dicts = []
    area_ids = event.get("area_ids", [])
    area_names_list = event.get("area_names", [])
    for i, name in enumerate(area_names_list):
        area_dicts.append({"id": area_ids[i] if i < len(area_ids) else "", "name": name, "category": "", "source": ""})
    area_links_list = protected_area_links(area_dicts)

    hex_code = event["aircraft_hex"].upper()

    # Aircraft type — plain text with optional ICAO reference link
    at_links = aircraft_type_links(event.get("aircraft_type"))
    if aircraft_type and at_links:
        aircraft_type_display = (
            f'<a href="{html_mod.escape(at_links[0].url)}" '
            f'style="color:#174c3c;text-decoration:underline" rel="noopener noreferrer">'
            f'{html_mod.escape(aircraft_type)}</a>'
        )
    elif aircraft_type:
        aircraft_type_display = html_mod.escape(aircraft_type)
    else:
        aircraft_type_display = t("email_unavailable", lang)

    # Registration display with links
    registration_display = html_mod.escape(registration) if registration else t("email_unavailable", lang)
    if reg_links:
        reg_parts = []
        for link in reg_links:
            reg_parts.append(
                f'<a href="{html_mod.escape(link.url)}" style="color:#174c3c;text-decoration:underline" '
                f'rel="noopener noreferrer">{html_mod.escape(link.label)}</a>'
            )
        registration_display = f'{html_mod.escape(registration)} — {" · ".join(reg_parts)}'

    # Callsign display with links
    callsign_display = html_mod.escape(callsign)
    if cs_links:
        callsign_display = f'{html_mod.escape(callsign)} — {_link_list_html(cs_links)}'

    # Flight number display
    flight_number_display = ""
    if event.get("flight_number"):
        fn_text = html_mod.escape(event["flight_number"])
        fn_html = _link_list_html(fn_links) if fn_links else ""
        flight_number_display = (
            f'<tr><td style="padding:8px 0;color:#746a70">{t("email_flight_number", lang)}</td>'
            f'<td style="padding:8px 0">{fn_text}{" — " + fn_html if fn_html else ""}</td></tr>'
        )

    # Protected areas display
    areas_display = html_mod.escape(areas) if areas else t("email_unavailable", lang)
    if area_links_list:
        area_parts = []
        for link in area_links_list:
            area_parts.append(
                f'<a href="{html_mod.escape(link.url)}" style="color:#174c3c;text-decoration:underline" '
                f'rel="noopener noreferrer">{html_mod.escape(link.label)}</a>'
            )
        areas_display = f'{html_mod.escape(areas)} — {" · ".join(area_parts)}'

    # Position display
    lat_val = event.get("latitude")
    lng_val = event.get("longitude")
    if lat_val is not None and lng_val is not None:
        lat_f = float(lat_val)
        lng_f = float(lng_val)
        pos_text = f'{lat_f:.6f}, {lng_f:.6f}'
        pos_html = _link_list_html(pos_links) if pos_links else ""
        position_display = f'{html_mod.escape(pos_text)}{" — " + pos_html if pos_html else ""}'
    else:
        position_display = t("email_unavailable", lang)

    # Airport displays
    origin_display = html_mod.escape(details.get("origin") or "") or t("email_unavailable", lang)
    if origin_links:
        origin_display = f'{html_mod.escape(details.get("origin", ""))} — {_link_list_html(origin_links)}'

    destination_display = html_mod.escape(details.get("destination") or "") or t("email_unavailable", lang)
    if dest_links:
        destination_display = f'{html_mod.escape(details.get("destination", ""))} — {_link_list_html(dest_links)}'

    # Provider display
    provider = event.get("provider", "")
    provider_display = html_mod.escape(provider) if provider else t("email_unavailable", lang)
    if provider_lks:
        provider_display = f'{html_mod.escape(provider)} — {_link_list_html(provider_lks)}'

    # External tracking note
    ext_note = (
        t("email_external_tracking_note", lang)
        if t("email_external_tracking_note", lang) != "email_external_tracking_note"
        else "External tracking services may not currently have a position or record for every aircraft."
    )

    # Primary event CTA
    event_cta = ""
    if evt_link:
        event_cta = f'''
<div style="margin:20px 0;text-align:center">
<a href="{html_mod.escape(evt_link.url)}" style="display:inline-block;padding:14px 32px;background:#174c3c;color:white;border-radius:8px;text-decoration:none;font-size:16px;font-weight:bold" rel="noopener noreferrer">{html_mod.escape(evt_link.label)}</a>
</div>'''

    # Tracking services section
    tracking_section = ""
    if hex_links:
        tracking_links = _link_list_html(hex_links)
        tracking_section = f'''
<tr><td style="padding:8px 0;color:#746a70">{t("email_tracking_services", lang)}</td><td style="padding:8px 0">{tracking_links}</td></tr>'''

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;max-width:720px;margin:auto;padding:20px;background:#f4f0e9">
<div style="background:white;border-radius:12px;padding:24px;box-shadow:0 4px 12px rgba(0,0,0,0.08)">
<h2 style="color:#6b2847;margin-top:0">{t("email_title", lang)}</h2>
{event_cta}
<table style="width:100%;border-collapse:collapse;font-size:14px">
<tr><td style="padding:8px 0;color:#746a70;width:140px">{t("email_event", lang)}</td><td style="padding:8px 0"><strong>{translate_event_type(event["event_type"], lang)}</strong></td></tr>
<tr><td style="padding:8px 0;color:#746a70">{t("email_aircraft", lang)}</td><td style="padding:8px 0"><strong>{html_mod.escape(hex_code)}</strong></td></tr>
<tr><td style="padding:8px 0;color:#746a70">{t("email_callsign", lang)}</td><td style="padding:8px 0">{callsign_display}</td></tr>
{flight_number_display}
<tr><td style="padding:8px 0;color:#746a70">{t("email_registration", lang)}</td><td style="padding:8px 0">{registration_display}</td></tr>
<tr><td style="padding:8px 0;color:#746a70">{t("email_aircraft_type", lang)}</td><td style="padding:8px 0">{aircraft_type_display}</td></tr>
<tr><td style="padding:8px 0;color:#746a70">{t("email_protected_areas", lang)}</td><td style="padding:8px 0">{areas_display}</td></tr>
<tr><td style="padding:8px 0;color:#746a70">{t("email_time", lang)}</td><td style="padding:8px 0">{_format_time(event["occurred_at"], tz_offset, lang)}</td></tr>
<tr><td style="padding:8px 0;color:#746a70">{t("email_last_position", lang)}</td><td style="padding:8px 0">{position_display}</td></tr>
<tr><td style="padding:8px 0;color:#746a70">{t("email_altitude", lang)}</td><td style="padding:8px 0">{altitude if altitude is not None else t("email_unavailable", lang)} ft MSL</td></tr>
<tr><td style="padding:8px 0;color:#746a70">{t("email_ground_speed", lang)}</td><td style="padding:8px 0">{speed if speed is not None else t("email_unavailable", lang)} kt</td></tr>
<tr><td style="padding:8px 0;color:#746a70">{t("email_provider", lang)}</td><td style="padding:8px 0">{provider_display}</td></tr>
<tr><td style="padding:8px 0;color:#746a70">{t("email_source_type", lang)}</td><td style="padding:8px 0">{html_mod.escape(details.get("source_type") or t("email_unavailable", lang))}</td></tr>
<tr><td style="padding:8px 0;color:#746a70">{t("email_origin", lang)}</td><td style="padding:8px 0">{origin_display}</td></tr>
<tr><td style="padding:8px 0;color:#746a70">{t("email_destination", lang)}</td><td style="padding:8px 0">{destination_display}</td></tr>
<tr><td style="padding:8px 0;color:#746a70">{t("email_reason", lang)}</td><td style="padding:8px 0">{html_mod.escape(event["reason"])}</td></tr>
<tr><td style="padding:8px 0;color:#746a70">{t("email_classification", lang)}</td><td style="padding:8px 0">{html_mod.escape(classification)}</td></tr>
{tracking_section}
</table>
<div style="margin-top:16px;padding:12px;background:#f4f0e9;border-radius:8px;font-size:12px;color:#746a70">
{html_mod.escape(ext_note)}
</div>
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


def _smtp_send(event: dict, sender: str, recipients: list[str], lang: str = "pt") -> None:
    host = str(get_setting("smtp_host"))
    port = int(get_setting("smtp_port"))
    username = str(get_setting("smtp_username"))
    password = str(get_setting("smtp_password"))
    if not host or not username or not password:
        raise RuntimeError(t("err_smtp_missing", lang))
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
    lang = str(get_setting("language") or "pt")
    if email_count_today() >= int(get_setting("max_emails_per_day")):
        return "suppressed", t("err_daily_cap", lang)
    recipients = list(get_setting("alert_recipients"))
    if not recipients:
        return "failed", t("err_no_recipients", lang)
    provider = str(get_setting("email_provider")).lower()
    sender = str(get_setting("email_from"))
    if not _valid_sender(sender):
        return "failed", t("err_invalid_sender", lang)

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
            return "failed", t("err_resend_key_missing", lang)
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
            await asyncio.to_thread(_smtp_send, event, sender, recipients, lang)
            return "sent", None
        except Exception as exc:
            logger.warning("SMTP delivery failed for %s: %s", event["id"], exc)
            return "failed", str(exc)

    return "failed", f"{t('err_unsupported_email_provider', lang)}: {provider}"
