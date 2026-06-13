"""
Batch 50.1 — SMTP email channel for Jarvis Notes reminders.

Configure via env vars (none set by default — see Batch 50 verification report):
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM

If unconfigured, send_reminder_email() is a no-op that returns False.
"""

import asyncio
import os
import smtplib
from email.mime.text import MIMEText

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SMTP_FROM = os.getenv("SMTP_FROM", "")


def is_configured() -> bool:
    return bool(SMTP_HOST and SMTP_USER and SMTP_PASS and SMTP_FROM)


def _send_sync(to_email: str, note_text: str, remind_at: str | None) -> bool:
    try:
        body = f"Reminder from Jarvis:\n\n{note_text}"
        if remind_at:
            body += f"\n\nScheduled for: {remind_at}"
        msg = MIMEText(body, "plain")
        msg["Subject"] = "Jarvis reminder"
        msg["From"] = SMTP_FROM
        msg["To"] = to_email

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"MAILER: failed to send reminder email to {to_email}: {e}")
        return False


async def send_reminder_email(to_email: str, note_text: str, remind_at: str | None = None) -> bool:
    """Send a note-reminder email. No-op (returns False) if SMTP isn't configured."""
    if not is_configured() or not to_email:
        return False
    return await asyncio.to_thread(_send_sync, to_email, note_text, remind_at)
