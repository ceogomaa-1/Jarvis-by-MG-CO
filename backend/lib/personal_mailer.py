"""
Batch 50.1 — Resend email channel for Jarvis Notes reminders, branded as Jarvis OS1.

Configure via env vars:
  RESEND_API_KEY  (required — from Resend dashboard)
  RESEND_FROM     (default: "Jarvis OS1 <jarvis@mgcodashboard.com>" — must be on a
                   verified Resend sending domain; display name is what the user sees)
  APP_URL         (default: "https://jarvis-by-mg-co.vercel.app" — used for the
                   "Open Jarvis" CTA and the hosted logo image)

If RESEND_API_KEY isn't set, send_reminder_email() is a no-op that returns False.
send_reminder_email() returns True only on a confirmed 2xx response from Resend.
"""

import os
from datetime import datetime, timezone

import httpx

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
RESEND_FROM = os.getenv("RESEND_FROM", "Jarvis OS1 <jarvis@mgcodashboard.com>")
APP_URL = os.getenv("APP_URL", "https://jarvis-by-mg-co.vercel.app")
LOGO_URL = f"{APP_URL}/logo-os1-mono.png"

_ACCENT = "#ff9072"
_BG = "#0a0a0a"
_INK = "#f3ead9"
_SERIF = "Georgia, 'Times New Roman', serif"
_SANS = "-apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"


def is_configured() -> bool:
    return bool(RESEND_API_KEY)


def _format_12h(dt: datetime) -> str:
    hour = dt.hour % 12 or 12
    return f"{hour}:{dt.strftime('%M %p')}"


def _relative_time(iso_str: str | None) -> str | None:
    """'Saved 3 hours ago' style label."""
    if not iso_str:
        return None
    try:
        then = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        if then.tzinfo is None:
            then = then.replace(tzinfo=timezone.utc)
    except ValueError:
        return None

    seconds = int((datetime.now(timezone.utc) - then).total_seconds())
    if seconds < 60:
        return "Saved just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"Saved {minutes} minute{'s' if minutes != 1 else ''} ago"
    hours = minutes // 60
    if hours < 24:
        return f"Saved {hours} hour{'s' if hours != 1 else ''} ago"
    days = hours // 24
    return f"Saved {days} day{'s' if days != 1 else ''} ago"


def _due_label(remind_at: str | None, tz_name: str = "UTC") -> str | None:
    """'Due now' / 'Due at 5:40 PM' style label, in the user's local timezone."""
    if not remind_at:
        return None
    try:
        due = datetime.fromisoformat(remind_at.replace("Z", "+00:00"))
        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
    except ValueError:
        return None

    if due <= datetime.now(timezone.utc):
        return "Due now"

    try:
        import pytz
        local = due.astimezone(pytz.timezone(tz_name))
    except Exception:
        local = due
    return f"Due at {_format_12h(local)}"


def _build_html(note_text: str, meta_parts: list[str]) -> str:
    meta_line = " &middot; ".join(meta_parts) if meta_parts else ""
    meta_row = (
        f'<tr><td style="padding:0 32px;font-family:{_SANS};color:rgba(243,234,217,0.5);'
        f'font-size:12px;line-height:1.6;">{meta_line}</td></tr>'
        if meta_line else ""
    )
    return f"""<!DOCTYPE html>
<html>
  <body style="margin:0;padding:0;background-color:{_BG};">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:{_BG};padding:40px 16px;">
      <tr>
        <td align="center">
          <table role="presentation" width="100%" style="max-width:480px;background-color:{_BG};border:1px solid rgba(243,234,217,0.08);border-radius:16px;overflow:hidden;">
            <tr>
              <td align="center" style="padding:32px 32px 16px;background-color:#000000;">
                <img src="{LOGO_URL}" alt="Jarvis OS1" width="220" style="display:block;margin:0 auto;border:0;" />
              </td>
            </tr>
            <tr>
              <td align="center" style="padding:10px 32px 24px;background-color:#000000;">
                <div style="font-family:{_SANS};color:rgba(243,234,217,0.45);font-size:11px;letter-spacing:0.2em;text-transform:uppercase;">Your personal AI &mdash; by MG&amp;CO</div>
              </td>
            </tr>
            <tr>
              <td style="padding:0 32px;">
                <div style="border-top:1px solid rgba(243,234,217,0.08);"></div>
              </td>
            </tr>
            <tr>
              <td style="padding:28px 32px 16px;">
                <div style="font-family:{_SANS};color:{_ACCENT};font-size:11px;letter-spacing:0.25em;text-transform:uppercase;margin-bottom:12px;">&#9200; Reminder</div>
                <div style="font-family:{_SERIF};color:{_INK};font-size:19px;line-height:1.55;">{note_text}</div>
              </td>
            </tr>
            {meta_row}
            <tr>
              <td align="center" style="padding:28px 32px 32px;">
                <a href="{APP_URL}" style="display:inline-block;background-color:{_ACCENT};color:#1a0e08;text-decoration:none;font-family:{_SANS};font-size:12px;font-weight:600;letter-spacing:0.2em;text-transform:uppercase;padding:14px 36px;border-radius:8px;">Open Jarvis</a>
              </td>
            </tr>
            <tr>
              <td style="padding:0 32px;">
                <div style="border-top:1px solid rgba(243,234,217,0.08);"></div>
              </td>
            </tr>
            <tr>
              <td align="center" style="padding:20px 32px 28px;">
                <div style="font-family:{_SANS};color:rgba(243,234,217,0.35);font-size:10px;letter-spacing:0.03em;line-height:1.7;">MG&amp;CO Technologies &middot; You're receiving this because you set a reminder in Jarvis OS1.</div>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""


def _build_text(note_text: str, meta_parts: list[str]) -> str:
    lines = [
        "JARVIS OS1",
        "Your personal AI -- by MG&CO",
        "",
        f"Reminder: {note_text}",
    ]
    if meta_parts:
        lines.append(" / ".join(meta_parts))
    lines += [
        "",
        f"Open Jarvis: {APP_URL}",
        "",
        "--",
        "MG&CO Technologies. You're receiving this because you set a reminder in Jarvis OS1.",
    ]
    return "\n".join(lines)


async def send_reminder_email(
    to_email: str,
    note_text: str,
    remind_at: str | None = None,
    created_at: str | None = None,
    tz_name: str = "UTC",
) -> bool:
    """Send a branded Jarvis OS1 reminder email via Resend.

    Returns True only on a confirmed 2xx response from Resend — callers use this
    to decide whether the "email" channel can be marked in `channels_sent`.
    """
    if not is_configured() or not to_email:
        return False

    meta_parts = [p for p in (_relative_time(created_at), _due_label(remind_at, tz_name)) if p]

    short_note = note_text if len(note_text) <= 60 else note_text[:57] + "..."
    subject = f"⏰ Reminder from Jarvis OS1 — {short_note}"

    html = _build_html(note_text, meta_parts)
    text = _build_text(note_text, meta_parts)

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
                    "html": html,
                    "text": text,
                },
            )
        if 200 <= resp.status_code < 300:
            return True
        print(f"MAILER: Resend send failed ({resp.status_code}): {resp.text[:200]}")
        return False
    except Exception as e:
        print(f"MAILER: failed to send reminder email to {to_email}: {e}")
        return False
