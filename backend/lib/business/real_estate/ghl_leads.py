"""TOOL 1 — GoHighLevel stale-lead scanner + note logger."""
import asyncio
from datetime import datetime, timedelta, timezone

from backend.lib.business.connectors.base import ConnectorResult
from backend.lib.business.connectors.registry import get_connector_for_user
from backend.lib.business.model_router import HAIKU
from backend.lib.business.real_estate.llm import call_claude, parse_json_response

GHL_NOT_CONNECTED = (
    "GoHighLevel isn't connected yet — open Connections and add your "
    "Private Integration token + Location ID."
)

_CLASSIFY_SYSTEM = (
    "You are a CRM assistant for a real estate agent. Decide whether a stale "
    "contact needs a follow-up and draft one if so. Be concise and concrete."
)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        v = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _contact_name(c: dict) -> str:
    name = (c.get("contactName") or "").strip()
    if name:
        return name
    full = f"{c.get('firstName', '')} {c.get('lastName', '')}".strip()
    return full or "(no name)"


async def _classify_contact(last_note: str) -> dict:
    if not last_note.strip():
        return {
            "needs_followup": True,
            "reason": "No notes on file — status is unclear, worth a check-in.",
            "suggested_followup": "Hi! Just checking in to see where you're at with your search/sale — happy to help with next steps whenever you're ready.",
        }

    prompt = (
        f'A real estate CRM contact\'s most recent note says:\n"""{last_note}"""\n\n'
        "Return JSON only:\n"
        '{"needs_followup": true/false, "reason": "1 sentence on why this matters", '
        '"suggested_followup": "1-2 sentence follow-up draft, or empty string if not needed"}'
    )
    try:
        raw = await call_claude(system=_CLASSIFY_SYSTEM, prompt=prompt, model=HAIKU, max_tokens=250)
        parsed = parse_json_response(raw)
        if parsed:
            return parsed
    except Exception as e:
        print(f"GHL_LEADS: classification error: {e}")
    return {"needs_followup": True, "reason": "Could not auto-classify — review manually.", "suggested_followup": ""}


async def scan_stale_leads(user_id: str, days_stale: int = 14, limit: int = 25) -> ConnectorResult:
    ghl = await get_connector_for_user(user_id, "gohighlevel")
    if not ghl:
        return ConnectorResult(ok=False, error=GHL_NOT_CONNECTED)

    all_contacts: list[dict] = []
    cursor_id = None
    for _ in range(3):  # up to 300 contacts
        result = await ghl.list_contacts_v2(limit=100, start_after_id=cursor_id)
        if not result.ok:
            return result
        page = (result.data or {}).get("contacts", [])
        all_contacts.extend(page)
        meta = (result.data or {}).get("meta", {})
        cursor_id = meta.get("startAfterId")
        if not cursor_id or not page:
            break

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days_stale)

    stale: list[tuple[dict, datetime]] = []
    for c in all_contacts:
        last_dt = _parse_dt(c.get("dateUpdated") or c.get("dateAdded"))
        if last_dt and last_dt < cutoff:
            stale.append((c, last_dt))

    stale.sort(key=lambda pair: pair[1])  # oldest contact first
    stale = stale[:limit]

    sem = asyncio.Semaphore(6)

    async def _process(contact: dict, last_dt: datetime) -> dict:
        async with sem:
            last_note_text = ""
            notes_result = await ghl.get_contact_notes(contact["id"])
            if notes_result.ok:
                notes = (notes_result.data or {}).get("notes", [])
                if notes:
                    notes_sorted = sorted(notes, key=lambda n: n.get("dateAdded", ""), reverse=True)
                    last_note_text = notes_sorted[0].get("body", "")

            classification = await _classify_contact(last_note_text)

            return {
                "contact_id": contact.get("id"),
                "name": _contact_name(contact),
                "phone": contact.get("phone"),
                "email": contact.get("email"),
                "days_since_contact": (now - last_dt).days,
                "last_note": last_note_text,
                "needs_followup": bool(classification.get("needs_followup", True)),
                "reason": classification.get("reason", ""),
                "suggested_followup": classification.get("suggested_followup", ""),
            }

    ranked = await asyncio.gather(*[_process(c, dt) for c, dt in stale])
    ranked = sorted(ranked, key=lambda r: not r["needs_followup"])  # needs_followup first

    return ConnectorResult(
        ok=True,
        data={
            "stale_leads": ranked,
            "scanned_contacts": len(all_contacts),
            "stale_count": len(ranked),
            "days_stale": days_stale,
        },
    )


async def add_note(user_id: str, contact_id: str, note: str) -> ConnectorResult:
    if not contact_id or not note:
        return ConnectorResult(ok=False, error="contact_id and note are both required.")
    ghl = await get_connector_for_user(user_id, "gohighlevel")
    if not ghl:
        return ConnectorResult(ok=False, error=GHL_NOT_CONNECTED)
    return await ghl.add_note(contact_id, note)
