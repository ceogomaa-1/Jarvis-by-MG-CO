"""
Feature 1 — Scheduled email dispatcher (Gmail has no native schedule-send).

Runs every minute via APScheduler (backend/main.py) and on-demand via
POST /api/business/email/_dispatch, which an external cron pinger
(cron-job.org / UptimeRobot) can hit every ~60s — same pattern as
backend/cron/notes_reminders.py.

Scans business_scheduled_emails for status='pending' rows whose send_at has
passed, resolves any doc_id attachments via document_store, sends through the
user's Google connection, and marks the row 'sent' only on a real 2xx from
Gmail. If the user's Google connection is missing/inactive or an attachment
has expired from document_store, the row is marked 'failed' with the real
error — never silently dropped, never retried forever.
"""
import os
from datetime import datetime, timezone

import httpx

from backend.lib.business.connectors.registry import get_connector_for_user
from backend.lib.business.document_store import resolve_attachments

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

_TABLE = "business_scheduled_emails"


def _headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


async def _fetch_due() -> list[dict]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/{_TABLE}",
                headers=_headers(),
                params={
                    "select": "*",
                    "status": "eq.pending",
                    "send_at": f"lte.{now_iso}",
                    "order": "send_at.asc",
                    "limit": "25",
                },
                timeout=10.0,
            )
        if resp.status_code != 200:
            print(f"SCHEDULED_EMAILS: fetch failed ({resp.status_code}): {resp.text[:200]}")
            return []
        return resp.json()
    except Exception as e:
        print(f"SCHEDULED_EMAILS: fetch error: {e}")
        return []


async def _update(row_id: str, fields: dict) -> None:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return
    try:
        async with httpx.AsyncClient() as client:
            await client.patch(
                f"{SUPABASE_URL}/rest/v1/{_TABLE}",
                headers={**_headers(), "Prefer": "return=minimal"},
                params={"id": f"eq.{row_id}"},
                json=fields,
                timeout=10.0,
            )
    except Exception as e:
        print(f"SCHEDULED_EMAILS: update error for {row_id}: {e}")


async def run_scheduled_emails() -> int:
    """Send all due scheduled emails. Returns the number processed."""
    due = await _fetch_due()
    for row in due:
        row_id = row["id"]
        user_id = row["user_id"]

        attachments, attach_error = resolve_attachments(row.get("attachments") or [])
        if attach_error:
            await _update(row_id, {"status": "failed", "error": attach_error})
            continue

        google = await get_connector_for_user(user_id, "google")
        if not google:
            await _update(row_id, {"status": "failed", "error": "Google isn't connected for this user."})
            continue

        result = await google.send_email(
            to=row["to_email"],
            subject=row["subject"],
            body=row["body"],
            cc=row.get("cc") or "",
            attachments=attachments or None,
        )
        if result.ok:
            await _update(row_id, {"status": "sent", "sent_at": datetime.now(timezone.utc).isoformat()})
        else:
            await _update(row_id, {"status": "failed", "error": result.error or "Unknown send error"})

    return len(due)
