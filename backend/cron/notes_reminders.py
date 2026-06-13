"""
Batch 50.1 — Jarvis Notes reminder dispatcher.

Runs every 5 minutes via APScheduler (backend/main.py). Scans `personal_notes`
for due, undone reminders (`remind_at <= now`) and delivers them through
whichever channels haven't fired yet, tracked per-note in `channels_sent`:

  - "inapp" — insert a row into `proactive_messages` (type=note_reminder),
              delivered next time the frontend calls /api/proactive/{user_id}
  - "push"  — Web Push (VAPID) to any rows in `push_subscriptions`
  - "email" — SMTP via backend/lib/personal_mailer.py

The "chat" channel (delivered while the user is actively chatting) is handled
separately by backend/routes/proactive_routes.py::_check_due_reminders, which
the frontend polls every 5 minutes.

Each channel is attempted at most once per note — if a channel isn't
configured (no SMTP / VAPID env vars, no push subscriptions), it's still
recorded as attempted so the cron doesn't retry every 5 minutes forever.
Snoozing a note resets `channels_sent` to `[]`.
"""

import json
import os
from datetime import datetime, timezone

import httpx

from backend.agent import _NOTES_TABLE, _SUPABASE_KEY, _SUPABASE_URL, _notes_headers
from backend.lib.personal_mailer import send_reminder_email

try:
    from pywebpush import webpush, WebPushException
except ImportError:
    webpush = None
    WebPushException = Exception

VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "")
VAPID_SUBJECT = os.getenv("VAPID_SUBJECT", "")

_DISPATCH_CHANNELS = ("inapp", "push", "email")


async def _fetch_due_notes() -> list[dict]:
    """All undone notes across all users whose remind_at has passed."""
    if not _SUPABASE_URL or not _SUPABASE_KEY:
        return []
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{_SUPABASE_URL}/rest/v1/{_NOTES_TABLE}",
                headers=_notes_headers(),
                params={
                    "done": "eq.false",
                    "remind_at": f"lte.{now_iso}",
                    "order": "remind_at.asc",
                },
                timeout=10.0,
            )
        if resp.status_code != 200:
            print(f"NOTES CRON: fetch failed ({resp.status_code}): {resp.text[:200]}")
            return []
        return resp.json()
    except Exception as e:
        print(f"NOTES CRON: fetch error: {e}")
        return []


def _user_id_to_uuid(user_id: str) -> str | None:
    hex_part = user_id.removeprefix("user_")
    if len(hex_part) == 32 and all(c in "0123456789abcdefABCDEF" for c in hex_part):
        return f"{hex_part[0:8]}-{hex_part[8:12]}-{hex_part[12:16]}-{hex_part[16:20]}-{hex_part[20:32]}"
    return None


async def _get_user_email(user_id: str) -> str | None:
    uuid_str = _user_id_to_uuid(user_id)
    if not uuid_str:
        return None
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{_SUPABASE_URL}/auth/v1/admin/users/{uuid_str}",
                headers={"apikey": _SUPABASE_KEY, "Authorization": f"Bearer {_SUPABASE_KEY}"},
                timeout=10.0,
            )
        if resp.status_code != 200:
            return None
        return resp.json().get("email")
    except Exception as e:
        print(f"NOTES CRON: failed to look up email for {user_id}: {e}")
        return None


async def _send_inapp(user_id: str, note: dict) -> None:
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{_SUPABASE_URL}/rest/v1/proactive_messages",
                headers=_notes_headers("return=minimal"),
                json={
                    "user_id": user_id,
                    "message": f"Reminder: {note['note']}",
                    "type": "note_reminder",
                    "read": False,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
                timeout=10.0,
            )
    except Exception as e:
        print(f"NOTES CRON: in-app insert failed for {user_id}: {e}")


async def _fetch_push_subscriptions(user_id: str) -> list[dict]:
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{_SUPABASE_URL}/rest/v1/push_subscriptions",
                headers=_notes_headers(),
                params={"user_id": f"eq.{user_id}"},
                timeout=10.0,
            )
        return resp.json() if resp.status_code == 200 else []
    except Exception:
        return []


async def _send_push(user_id: str, note: dict) -> None:
    if not webpush or not (VAPID_PRIVATE_KEY and VAPID_SUBJECT):
        return
    subs = await _fetch_push_subscriptions(user_id)
    for sub in subs:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub["endpoint"],
                    "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]},
                },
                data=json.dumps({"title": "Jarvis reminder", "body": note["note"]}),
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims={"sub": VAPID_SUBJECT},
            )
        except WebPushException as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            print(f"NOTES CRON: push failed for {user_id}: {e}")
            if status == 410:
                async with httpx.AsyncClient() as client:
                    await client.delete(
                        f"{_SUPABASE_URL}/rest/v1/push_subscriptions",
                        headers=_notes_headers("return=minimal"),
                        params={"id": f"eq.{sub['id']}"},
                        timeout=10.0,
                    )
        except Exception as e:
            print(f"NOTES CRON: push error for {user_id}: {e}")


async def _send_email(user_id: str, note: dict) -> None:
    email = await _get_user_email(user_id)
    if not email:
        return
    await send_reminder_email(email, note["note"], note.get("remind_at"))


async def _mark_channels_sent(note_id: str, channels: list[str]) -> None:
    try:
        async with httpx.AsyncClient() as client:
            await client.patch(
                f"{_SUPABASE_URL}/rest/v1/{_NOTES_TABLE}",
                headers=_notes_headers("return=minimal"),
                params={"id": f"eq.{note_id}"},
                json={"channels_sent": channels},
                timeout=10.0,
            )
    except Exception as e:
        print(f"NOTES CRON: failed to update channels_sent for {note_id}: {e}")


async def run_notes_reminders():
    """Dispatch due reminders across the in-app, push, and email channels."""
    notes = await _fetch_due_notes()
    if not notes:
        return

    for note in notes:
        channels_sent = note.get("channels_sent") or []
        pending = [c for c in _DISPATCH_CHANNELS if c not in channels_sent]
        if not pending:
            continue

        user_id = note["user_id"]
        if "inapp" in pending:
            await _send_inapp(user_id, note)
        if "push" in pending:
            await _send_push(user_id, note)
        if "email" in pending:
            await _send_email(user_id, note)

        await _mark_channels_sent(note["id"], channels_sent + pending)
        print(f"NOTES CRON: dispatched reminder for note {note['id']} ({user_id}) via {pending}")
