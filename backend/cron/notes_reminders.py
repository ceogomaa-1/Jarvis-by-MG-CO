"""
Batch 50.1 — Jarvis Notes reminder dispatcher.

Runs every minute via APScheduler (backend/main.py) and on-demand via
POST /api/notes/_dispatch (backend/routes/notes_routes.py), which an external
cron pinger (cron-job.org / UptimeRobot) hits every ~60s — this also keeps the
Render dyno warm so reminders don't queue up behind a cold start. Scans
`personal_notes` for due, undone reminders (`remind_at <= now`) and delivers
them through whichever channels haven't fired yet, tracked per-note in
`channels_sent`:

  - "inapp" — insert a row into `proactive_messages` (type=note_reminder),
              delivered next time the frontend calls /api/proactive/{user_id}
  - "push"  — Web Push (VAPID) to any rows in `push_subscriptions`
  - "email" — Resend, via backend/lib/personal_mailer.py

The "chat" channel (delivered while the user is actively chatting) is handled
separately by backend/routes/proactive_routes.py::_check_due_reminders, which
the frontend polls every 5 minutes.

Idempotency: a channel is only added to `channels_sent` once it has been
confirmed delivered (e.g. a 2xx from Resend, a successful push, a successful
in-app insert). Unconfigured or failing channels are left unmarked so they're
retried on the next run — except once a note's `remind_at` is more than
`_RETRY_CUTOFF_HOURS` in the past, at which point any still-pending channels
are marked as sent anyway so the cron stops retrying forever.

Recurring reminders (`remind_recurrence` in daily|weekly|monthly): once every
dispatch channel has fired, the note is re-armed — `remind_at` is advanced to
its next occurrence (timezone-correct, via the user's saved timezone) and
`channels_sent` is reset to `[]`. One-off notes (`remind_recurrence='none'`)
simply stay fired.

Snoozing a note resets `channels_sent` to `[]`.
"""

import calendar
import json
import os
from datetime import datetime, timedelta, timezone

import httpx
import pytz

from backend.agent import _NOTES_TABLE, _SUPABASE_KEY, _SUPABASE_URL, _notes_headers
from backend.lib.personal_mailer import APP_URL, send_reminder_email
from backend.utils.user_context import get_user_timezone

try:
    from pywebpush import webpush, WebPushException
except ImportError:
    webpush = None
    WebPushException = Exception

VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "")
VAPID_SUBJECT = os.getenv("VAPID_SUBJECT", "")

_DISPATCH_CHANNELS = ("inapp", "push", "email")
_RETRY_CUTOFF_HOURS = 48
_RECURRENCES = ("daily", "weekly", "monthly")


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


async def _send_inapp(user_id: str, note: dict) -> bool:
    """Insert an in-app proactive message. Returns True on confirmed insert."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
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
        return resp.status_code in (200, 201, 204)
    except Exception as e:
        print(f"NOTES CRON: in-app insert failed for {user_id}: {e}")
        return False


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


async def _delete_push_subscription(sub_id: str) -> None:
    try:
        async with httpx.AsyncClient() as client:
            await client.delete(
                f"{_SUPABASE_URL}/rest/v1/push_subscriptions",
                headers=_notes_headers("return=minimal"),
                params={"id": f"eq.{sub_id}"},
                timeout=10.0,
            )
    except Exception as e:
        print(f"NOTES CRON: failed to prune push subscription {sub_id}: {e}")


async def _send_push(user_id: str, note: dict) -> bool:
    """Web Push to all of the user's subscriptions. Returns True if at least
    one subscription was successfully delivered to."""
    if not webpush or not (VAPID_PRIVATE_KEY and VAPID_SUBJECT):
        return False
    subs = await _fetch_push_subscriptions(user_id)
    if not subs:
        return False

    sent_any = False
    for sub in subs:
        try:
            resp = webpush(
                subscription_info={
                    "endpoint": sub["endpoint"],
                    "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]},
                },
                data=json.dumps({
                    "title": "Jarvis OS1",
                    "body": f"Reminder: {note['note']}",
                    "url": APP_URL,
                }),
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims={"sub": VAPID_SUBJECT},
            )
            status = getattr(resp, "status_code", None)
            print(f"NOTES CRON: push delivered to {user_id} (sub {sub['id']}) — status {status}")
            sent_any = True
        except WebPushException as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            print(f"NOTES CRON: push failed for {user_id} (sub {sub['id']}) — status {status}: {e}")
            if status in (404, 410):
                await _delete_push_subscription(sub["id"])
        except Exception as e:
            print(f"NOTES CRON: push error for {user_id}: {e}")

    return sent_any


async def _send_email(user_id: str, note: dict, tz_name: str) -> bool:
    """Send the Resend reminder email. Returns True only on a confirmed send."""
    email = await _get_user_email(user_id)
    if not email:
        return False
    return await send_reminder_email(
        email,
        note["note"],
        remind_at=note.get("remind_at"),
        created_at=note.get("created_at"),
        tz_name=tz_name,
    )


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


async def _rearm_note(note_id: str, next_remind_at: str) -> None:
    """Advance a recurring note to its next occurrence and reset channels_sent."""
    try:
        async with httpx.AsyncClient() as client:
            await client.patch(
                f"{_SUPABASE_URL}/rest/v1/{_NOTES_TABLE}",
                headers=_notes_headers("return=minimal"),
                params={"id": f"eq.{note_id}"},
                json={"remind_at": next_remind_at, "channels_sent": []},
                timeout=10.0,
            )
    except Exception as e:
        print(f"NOTES CRON: failed to re-arm note {note_id}: {e}")


def _hours_overdue(note: dict) -> float:
    remind_at = note.get("remind_at")
    if not remind_at:
        return 0.0
    try:
        due = datetime.fromisoformat(remind_at.replace("Z", "+00:00"))
        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
    except ValueError:
        return 0.0
    return (datetime.now(timezone.utc) - due).total_seconds() / 3600.0


def _add_months(dt: datetime, months: int) -> datetime:
    total_month = dt.month - 1 + months
    year = dt.year + total_month // 12
    month = total_month % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def _advance(local_naive: datetime, recurrence: str) -> datetime:
    if recurrence == "daily":
        return local_naive + timedelta(days=1)
    if recurrence == "weekly":
        return local_naive + timedelta(weeks=1)
    if recurrence == "monthly":
        return _add_months(local_naive, 1)
    raise ValueError(f"Unknown recurrence: {recurrence!r}")


def _next_occurrence(remind_at_iso: str, recurrence: str, tz_name: str) -> str | None:
    """Compute the next remind_at for a recurring note, in the user's local
    timezone, returned as a UTC ISO string."""
    if recurrence not in _RECURRENCES:
        return None
    try:
        due = datetime.fromisoformat(remind_at_iso.replace("Z", "+00:00"))
        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
    except ValueError:
        return None

    try:
        tz = pytz.timezone(tz_name)
    except Exception:
        tz = pytz.utc

    local_naive = due.astimezone(tz).replace(tzinfo=None)
    now_local_naive = datetime.now(timezone.utc).astimezone(tz).replace(tzinfo=None)

    next_naive = _advance(local_naive, recurrence)
    while next_naive <= now_local_naive:
        next_naive = _advance(next_naive, recurrence)

    return tz.localize(next_naive).astimezone(timezone.utc).isoformat()


async def run_notes_reminders():
    """Dispatch due reminders across the in-app, push, and email channels."""
    notes = await _fetch_due_notes()
    if not notes:
        return

    for note in notes:
        channels_sent = list(note.get("channels_sent") or [])
        pending = [c for c in _DISPATCH_CHANNELS if c not in channels_sent]
        if not pending:
            continue

        user_id = note["user_id"]
        tz_name = await get_user_timezone(user_id)
        newly_sent = []

        if "inapp" in pending and await _send_inapp(user_id, note):
            newly_sent.append("inapp")
        if "push" in pending and await _send_push(user_id, note):
            newly_sent.append("push")
        if "email" in pending and await _send_email(user_id, note, tz_name):
            newly_sent.append("email")

        still_pending = [c for c in pending if c not in newly_sent]
        if still_pending and _hours_overdue(note) >= _RETRY_CUTOFF_HOURS:
            print(
                f"NOTES CRON: note {note['id']} channels {still_pending} exceeded "
                f"{_RETRY_CUTOFF_HOURS}h retry cutoff — marking as sent without delivery"
            )
            newly_sent = newly_sent + still_pending

        if not newly_sent:
            continue

        updated_channels = channels_sent + newly_sent
        recurrence = note.get("remind_recurrence") or "none"
        all_dispatched = all(c in updated_channels for c in _DISPATCH_CHANNELS)

        if all_dispatched and recurrence in _RECURRENCES and note.get("remind_at"):
            next_remind_at = _next_occurrence(note["remind_at"], recurrence, tz_name)
            if next_remind_at:
                await _rearm_note(note["id"], next_remind_at)
                print(f"NOTES CRON: note {note['id']} re-armed for {next_remind_at} ({recurrence})")
            else:
                await _mark_channels_sent(note["id"], updated_channels)
        else:
            await _mark_channels_sent(note["id"], updated_channels)

        print(f"NOTES CRON: dispatched reminder for note {note['id']} ({user_id}) via {newly_sent}")
