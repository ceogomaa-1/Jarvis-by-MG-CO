"""
Feature 1 — Scheduled email CRUD backing the google__schedule_email /
google__list_scheduled_emails / google__cancel_scheduled_email tools.

Rows live in business_scheduled_emails and are sent by
backend/cron/scheduled_emails_cron.py (APScheduler every minute +
POST /api/business/email/_dispatch external pinger).
"""
import os
from datetime import datetime

import httpx

from backend.lib.business.connectors.base import ConnectorResult
from backend.lib.business.connectors.registry import _user_id_to_uuid

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

_TABLE = "business_scheduled_emails"


def _headers(extra: dict | None = None) -> dict:
    h = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    if extra:
        h.update(extra)
    return h


async def schedule_email(
    user_id: str,
    to_email: str,
    subject: str,
    body: str,
    send_at: str,
    cc: str = "",
    attachments: list[dict] | None = None,
) -> ConnectorResult:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return ConnectorResult(ok=False, error="Database not configured.")

    try:
        parsed = datetime.fromisoformat(send_at.replace("Z", "+00:00"))
    except Exception:
        return ConnectorResult(
            ok=False,
            error=f"Invalid send_at datetime: {send_at!r}. Use ISO 8601 with a timezone offset, e.g. 2026-06-15T09:00:00-04:00.",
        )

    for att in attachments or []:
        if not att.get("doc_id"):
            return ConnectorResult(ok=False, error="Each attachment needs a doc_id.")

    payload = {
        "user_id": _user_id_to_uuid(user_id),
        "to_email": to_email,
        "cc": cc or None,
        "subject": subject,
        "body": body,
        "attachments": attachments or [],
        "send_at": parsed.isoformat(),
        "status": "pending",
    }
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{SUPABASE_URL}/rest/v1/{_TABLE}",
                headers={**_headers(), "Prefer": "return=representation"},
                json=payload,
                timeout=10.0,
            )
        if resp.status_code in (200, 201):
            data = resp.json()
            row = data[0] if isinstance(data, list) and data else data
            return ConnectorResult(ok=True, data={
                "id": row.get("id"),
                "to": to_email,
                "subject": subject,
                "send_at": row.get("send_at"),
                "status": "pending",
            })
        return ConnectorResult(ok=False, error=f"Schedule email failed ({resp.status_code}): {resp.text[:200]}")
    except Exception as e:
        return ConnectorResult(ok=False, error=f"Schedule email failed: {e}")


async def list_scheduled_emails(user_id: str, status: str | None = None) -> ConnectorResult:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return ConnectorResult(ok=False, error="Database not configured.")

    params: dict = {
        "select": "id,to_email,cc,subject,send_at,status,error,created_at,sent_at",
        "user_id": f"eq.{_user_id_to_uuid(user_id)}",
        "order": "send_at.asc",
        "limit": "50",
    }
    if status:
        params["status"] = f"eq.{status}"

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/{_TABLE}",
                headers=_headers(),
                params=params,
                timeout=10.0,
            )
        if resp.status_code == 200:
            return ConnectorResult(ok=True, data={"scheduled_emails": resp.json()})
        return ConnectorResult(ok=False, error=f"List scheduled emails failed ({resp.status_code}): {resp.text[:200]}")
    except Exception as e:
        return ConnectorResult(ok=False, error=f"List scheduled emails failed: {e}")


async def cancel_scheduled_email(user_id: str, scheduled_id: str) -> ConnectorResult:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return ConnectorResult(ok=False, error="Database not configured.")

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.patch(
                f"{SUPABASE_URL}/rest/v1/{_TABLE}",
                headers={**_headers(), "Prefer": "return=representation"},
                params={
                    "id": f"eq.{scheduled_id}",
                    "user_id": f"eq.{_user_id_to_uuid(user_id)}",
                    "status": "eq.pending",
                },
                json={"status": "cancelled"},
                timeout=10.0,
            )
        if resp.status_code == 200:
            data = resp.json()
            if not data:
                return ConnectorResult(
                    ok=False,
                    error="No pending scheduled email found with that ID (already sent, cancelled, or not yours).",
                )
            return ConnectorResult(ok=True, data={"id": scheduled_id, "status": "cancelled"})
        return ConnectorResult(ok=False, error=f"Cancel scheduled email failed ({resp.status_code}): {resp.text[:200]}")
    except Exception as e:
        return ConnectorResult(ok=False, error=f"Cancel scheduled email failed: {e}")
