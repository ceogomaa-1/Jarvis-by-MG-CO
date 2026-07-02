"""
Owner notifications for Jarvis OS1 Business (Batch 72).

The co-founder's discipline: reach out only when the owner ACTUALLY needs to
know, and never more than JARVIS_NOTIFY_DAILY_CAP times a day (default 2).
A notification = in-app proactive message + (when wired) a branded email via
Resend — the same Resend account Personal reminders use.

Cap enforcement is durable via business_owner_notifications (batch72). If the
table isn't migrated yet, an in-process counter still enforces the cap for
this worker's lifetime — combined with the deliberately sparse triggers
(nightly run digest + red risk flags), the cap holds either way.

Callers pass a dedupe_key so the same event (e.g. one run, one flag-day)
can never notify twice.
"""
import os
from datetime import datetime, timezone

import httpx

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
RESEND_FROM = os.getenv("RESEND_FROM", "Jarvis OS1 <jarvis@mgcodashboard.com>")
DAILY_CAP = max(1, int(os.getenv("JARVIS_NOTIFY_DAILY_CAP", "2")))

# In-process fallback cap tracking, used only when the batch72 table is missing.
_local_sent: dict[str, list[str]] = {}  # user_id -> [iso_dates of sends]


def _headers(prefer: str | None = None) -> dict:
    h = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    if prefer:
        h["Prefer"] = prefer
    return h


def _user_id_to_uuid(user_id: str) -> str:
    hex_id = user_id.removeprefix("user_")
    if len(hex_id) == 32 and all(c in "0123456789abcdef" for c in hex_id.lower()):
        return f"{hex_id[:8]}-{hex_id[8:12]}-{hex_id[12:16]}-{hex_id[16:20]}-{hex_id[20:]}"
    return user_id


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


async def _get_user_email(user_uuid: str) -> str | None:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SUPABASE_URL}/auth/v1/admin/users/{user_uuid}",
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
                timeout=10.0,
            )
        if resp.status_code == 200:
            return resp.json().get("email")
    except Exception as e:
        print(f"NOTIFY: email lookup failed for {user_uuid}: {e}")
    return None


async def _sent_today(user_uuid: str, dedupe_key: str | None) -> tuple[int | None, bool]:
    """(count_today, dedupe_hit). count_today is None if the table is missing."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None, False
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/business_owner_notifications",
                headers=_headers(),
                params={
                    "select": "id,dedupe_key",
                    "user_id": f"eq.{user_uuid}",
                    "created_at": f"gte.{_today_utc()}T00:00:00Z",
                    "limit": "20",
                },
                timeout=10.0,
            )
        if resp.status_code != 200:
            return None, False  # table probably not migrated yet
        rows = resp.json()
        dedupe_hit = bool(dedupe_key) and any(r.get("dedupe_key") == dedupe_key for r in rows)
        return len(rows), dedupe_hit
    except Exception:
        return None, False


async def _record(user_uuid: str, kind: str, subject: str, channel: str, dedupe_key: str | None) -> None:
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{SUPABASE_URL}/rest/v1/business_owner_notifications",
                headers=_headers("return=minimal"),
                json={
                    "user_id": user_uuid,
                    "kind": kind,
                    "subject": subject[:300],
                    "channel": channel,
                    "dedupe_key": dedupe_key,
                },
                timeout=10.0,
            )
    except Exception as e:
        print(f"NOTIFY: record failed: {e}")


async def _insert_inapp(user_uuid: str, message: str, kind: str) -> None:
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{SUPABASE_URL}/rest/v1/business_proactive_insights",
                headers=_headers("return=minimal"),
                json={
                    "user_id": user_uuid,
                    "message": message[:600],
                    "type": kind,
                    "is_read": False,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
                timeout=10.0,
            )
    except Exception as e:
        print(f"NOTIFY: in-app insert failed: {e}")


def _build_html(subject: str, body_lines: list[str], cta_url: str | None) -> str:
    rows = "".join(
        f'<p style="margin:0 0 12px;font-size:14px;line-height:1.7;color:#d8d8d8;">{line}</p>'
        for line in body_lines
    )
    cta = (
        f'<a href="{cta_url}" style="display:inline-block;margin-top:6px;padding:11px 22px;'
        'background:#2d7ff9;color:#ffffff;border-radius:10px;text-decoration:none;'
        'font-size:13px;font-weight:600;">Open Jarvis →</a>'
        if cta_url else ""
    )
    return f"""\
<div style="background:#0f0f12;padding:36px 18px;font-family:-apple-system,Segoe UI,Roboto,sans-serif;">
  <div style="max-width:560px;margin:0 auto;background:#161619;border:1px solid #2a2a2e;border-radius:16px;padding:30px 32px;">
    <div style="font-size:10px;letter-spacing:0.18em;color:#2d7ff9;text-transform:uppercase;margin-bottom:14px;">
      Jarvis OS1 — your co-founder
    </div>
    <div style="font-size:18px;color:#f0f0f0;font-weight:600;margin-bottom:16px;line-height:1.4;">{subject}</div>
    {rows}
    {cta}
    <div style="margin-top:26px;padding-top:16px;border-top:1px solid #2a2a2e;font-size:11px;color:#6e6e6e;line-height:1.6;">
      MG&amp;CO Technologies. Jarvis only emails you when something genuinely needs you — max {DAILY_CAP} a day.
    </div>
  </div>
</div>"""


async def _send_email(to_email: str, subject: str, body_lines: list[str], cta_url: str | None) -> bool:
    if not RESEND_API_KEY or not to_email:
        return False
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": RESEND_FROM,
                    "to": [to_email],
                    "subject": subject,
                    "html": _build_html(subject, body_lines, cta_url),
                    "text": "\n\n".join(body_lines) + (f"\n\n{cta_url}" if cta_url else ""),
                },
            )
        if 200 <= resp.status_code < 300:
            return True
        print(f"NOTIFY: Resend failed ({resp.status_code}): {resp.text[:200]}")
    except Exception as e:
        print(f"NOTIFY: Resend exception: {e}")
    return False


async def notify_owner(
    user_id: str,
    *,
    subject: str,
    body_lines: list[str],
    kind: str,
    dedupe_key: str | None = None,
    cta_url: str | None = "https://jarvismgco.com/business/chat",
) -> dict:
    """Notify the owner about something that actually needs them.

    Sends in-app proactive message + Resend email, subject to the daily cap
    and dedupe_key. Returns {"sent": bool, "channel": str, "reason": str}.
    """
    user_uuid = _user_id_to_uuid(user_id)

    count_today, dedupe_hit = await _sent_today(user_uuid, dedupe_key)
    if dedupe_hit:
        return {"sent": False, "channel": "", "reason": "duplicate"}

    if count_today is None:
        # Table missing (pre-migration) — enforce cap in-process.
        today = _today_utc()
        sends = [d for d in _local_sent.get(user_uuid, []) if d == today]
        if len(sends) >= DAILY_CAP:
            return {"sent": False, "channel": "", "reason": "daily_cap_local"}
    elif count_today >= DAILY_CAP:
        return {"sent": False, "channel": "", "reason": "daily_cap"}

    # In-app first — always available, lands in chat as a proactive message.
    inapp_message = f"{subject}\n" + "\n".join(body_lines)
    await _insert_inapp(user_uuid, inapp_message, kind)

    # Email is best-effort on top.
    email = await _get_user_email(user_uuid)
    emailed = await _send_email(email, subject, body_lines, cta_url) if email else False

    channel = "inapp+email" if emailed else "inapp"
    await _record(user_uuid, kind, subject, channel, dedupe_key)
    _local_sent.setdefault(user_uuid, []).append(_today_utc())

    print(f"NOTIFY: user={user_id} kind={kind} channel={channel} subject={subject[:60]!r}")
    return {"sent": True, "channel": channel, "reason": ""}
