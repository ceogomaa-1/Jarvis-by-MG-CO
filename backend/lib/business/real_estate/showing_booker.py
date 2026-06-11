"""TOOL 3 — Showing Booker. Creates a Google Calendar event and, if GoHighLevel
is connected and a matching contact exists, logs a note back to the CRM."""
from datetime import datetime, timedelta

from backend.lib.business.connectors.base import ConnectorResult
from backend.lib.business.connectors.registry import get_connector_for_user

GOOGLE_NOT_CONNECTED = "Google Calendar isn't connected yet — open Connections and connect Google to book showings."


async def book_showing(
    user_id: str,
    property_address: str,
    client_name: str,
    showing_datetime: str,
    duration_min: int = 45,
    notes: str = "",
    contact_id: str | None = None,
) -> ConnectorResult:
    if not property_address or not client_name or not showing_datetime:
        return ConnectorResult(ok=False, error="property_address, client_name, and datetime are all required.")

    google = await get_connector_for_user(user_id, "google")
    if not google:
        return ConnectorResult(ok=False, error=GOOGLE_NOT_CONNECTED)

    try:
        start_dt = datetime.fromisoformat(showing_datetime)
    except ValueError:
        return ConnectorResult(ok=False, error=f"Couldn't parse '{showing_datetime}' — use ISO format like 2026-06-15T14:00:00.")

    end_dt = start_dt + timedelta(minutes=duration_min or 45)

    event_body = {
        "summary": f"Showing — {property_address} w/ {client_name}",
        "location": property_address,
        "description": notes or f"Property showing with {client_name}.",
        "start": {"dateTime": start_dt.isoformat(), "timeZone": "America/Toronto"},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": "America/Toronto"},
    }

    cal_result = await google.create_calendar_event(event_body)
    if not cal_result.ok:
        return cal_result

    ghl_note_status = None
    ghl = await get_connector_for_user(user_id, "gohighlevel")
    if ghl:
        target_contact_id = contact_id
        if not target_contact_id:
            search = await ghl.search_contacts_v2(client_name)
            if search.ok:
                found = (search.data or {}).get("contacts", [])
                if found:
                    target_contact_id = found[0].get("id")
        if target_contact_id:
            note_text = f"Showing booked {start_dt.strftime('%b %d, %Y at %I:%M %p')} @ {property_address}"
            note_result = await ghl.add_note(target_contact_id, note_text)
            ghl_note_status = "logged" if note_result.ok else f"failed: {note_result.error}"

    return ConnectorResult(
        ok=True,
        data={
            "event_id": cal_result.data.get("event_id"),
            "calendar_link": cal_result.data.get("link"),
            "property_address": property_address,
            "client_name": client_name,
            "start": event_body["start"],
            "end": event_body["end"],
            "ghl_note": ghl_note_status,
        },
    )
