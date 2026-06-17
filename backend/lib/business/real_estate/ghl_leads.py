"""TOOL 1 — GoHighLevel stale-lead scanner + note logger.

Account-aware: a user may connect up to 3 GoHighLevel accounts (each with its
own account_label). scan_stale_leads defaults to "all" — scanning every
connected account and tagging each result set with its account_label /
display_name — but a caller can pass a specific account_label to scope to one
account. add_note always targets one account (defaults to "default", which is
the only account most users will ever have).
"""
import asyncio
from datetime import datetime, timedelta, timezone

from backend.lib.business.connectors.base import ConnectorResult
from backend.lib.business.connectors.registry import get_connector_for_user, list_user_connections_for_type
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


async def _scan_account(ghl, days_stale: int, limit: int) -> ConnectorResult:
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


async def scan_stale_leads(user_id: str, days_stale: int = 14, limit: int = 25, account_label: str = "all") -> ConnectorResult:
    accounts = await list_user_connections_for_type(user_id, "gohighlevel")
    active_accounts = [a for a in accounts if a.get("status") == "active"]
    if not active_accounts:
        return ConnectorResult(ok=False, error=GHL_NOT_CONNECTED)

    if account_label != "all":
        active_accounts = [a for a in active_accounts if a["account_label"] == account_label]
        if not active_accounts:
            return ConnectorResult(
                ok=False,
                error=f"No active GoHighLevel account with label '{account_label}'. "
                f"Connected labels: {', '.join(a['account_label'] for a in accounts) or '(none)'}.",
            )

    results: list[dict] = []
    for acct in active_accounts:
        ghl = await get_connector_for_user(user_id, "gohighlevel", acct["account_label"])
        if not ghl:
            continue
        result = await _scan_account(ghl, days_stale, limit)
        entry = {
            "account_label": acct["account_label"],
            "account_display_name": acct.get("display_name") or acct["account_label"],
        }
        if result.ok:
            entry.update(result.data or {})
        else:
            entry["error"] = result.error
        results.append(entry)

    if len(results) == 1:
        return ConnectorResult(ok=True, data=results[0])

    return ConnectorResult(ok=True, data={"accounts": results})


def _has_future_task(tasks: list[dict], now: datetime) -> bool:
    """True if the contact has at least one OPEN task scheduled for the future —
    i.e. an incomplete task whose dueDate is now or later. Completed tasks and
    overdue/undated tasks do not count as a 'future task'."""
    for t in tasks or []:
        if t.get("completed"):
            continue
        due = _parse_dt(t.get("dueDate") or t.get("due_date"))
        if due and due >= now:
            return True
    return False


async def export_contacts_without_future_tasks(
    user_id: str, account_label: str = "default", max_contacts: int = 300
) -> ConnectorResult:
    """Find every CRM contact with NO open/future task and export them as a clean CSV.

    Live verification required: this depends on the connected GoHighLevel account's
    contacts + tasks. The filtering core (_has_future_task) is unit-tested.
    """
    from backend.lib.business.csv_export import export_csv_document

    ghl = await get_connector_for_user(user_id, "gohighlevel", account_label)
    if not ghl:
        accounts = await list_user_connections_for_type(user_id, "gohighlevel")
        if not accounts:
            return ConnectorResult(ok=False, error=GHL_NOT_CONNECTED)
        # Fall back to the first active account if the default label wasn't found.
        active = [a for a in accounts if a.get("status") == "active"]
        if not active:
            return ConnectorResult(ok=False, error=GHL_NOT_CONNECTED)
        ghl = await get_connector_for_user(user_id, "gohighlevel", active[0]["account_label"])
        if not ghl:
            return ConnectorResult(ok=False, error=GHL_NOT_CONNECTED)

    # Page through contacts (capped to keep the per-contact task lookups bounded).
    all_contacts: list[dict] = []
    cursor_id = None
    for _ in range(max(1, max_contacts // 100)):
        result = await ghl.list_contacts_v2(limit=100, start_after_id=cursor_id)
        if not result.ok:
            return result
        page = (result.data or {}).get("contacts", [])
        all_contacts.extend(page)
        cursor_id = ((result.data or {}).get("meta", {}) or {}).get("startAfterId")
        if not cursor_id or not page:
            break

    now = datetime.now(timezone.utc)
    sem = asyncio.Semaphore(6)

    async def _check(contact: dict) -> dict | None:
        async with sem:
            tasks_result = await ghl.get_contact_tasks(contact["id"])
            tasks = (tasks_result.data or {}).get("tasks", []) if tasks_result.ok else []
            if _has_future_task(tasks, now):
                return None
            return {
                "name": _contact_name(contact),
                "phone": contact.get("phone") or "",
                "email": contact.get("email") or "",
                "last_activity": contact.get("dateUpdated") or contact.get("dateAdded") or "",
                "contact_id": contact.get("id") or "",
            }

    checked = await asyncio.gather(*[_check(c) for c in all_contacts])
    no_task_contacts = [c for c in checked if c]

    doc, count = export_csv_document(
        no_task_contacts,
        filename="contacts-no-future-task.csv",
        columns=["name", "phone", "email", "last_activity", "contact_id"],
    )
    return ConnectorResult(
        ok=True,
        data={
            "download_url": doc["download_url"],
            "filename": doc["filename"],
            "scanned_contacts": len(all_contacts),
            "no_future_task_count": count,
            "preview": no_task_contacts[:10],
        },
    )


async def add_note(user_id: str, contact_id: str, note: str, account_label: str = "default") -> ConnectorResult:
    if not contact_id or not note:
        return ConnectorResult(ok=False, error="contact_id and note are both required.")
    ghl = await get_connector_for_user(user_id, "gohighlevel", account_label)
    if not ghl:
        accounts = await list_user_connections_for_type(user_id, "gohighlevel")
        if not accounts:
            return ConnectorResult(ok=False, error=GHL_NOT_CONNECTED)
        return ConnectorResult(
            ok=False,
            error=f"No active GoHighLevel account with label '{account_label}'. "
            f"Connected labels: {', '.join(a['account_label'] for a in accounts)}.",
        )
    return await ghl.add_note(contact_id, note)
