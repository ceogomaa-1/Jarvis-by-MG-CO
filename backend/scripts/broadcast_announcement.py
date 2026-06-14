"""
One-time broadcast — Jarvis Personal.

Notifies every existing Personal user, exactly once, that Jarvis can now send
reminders/notifications and a daily check-in. Farida gets a specially-tailored
message instead of the general one.

Inserts one row per user into `proactive_messages` (read=false), which the
Personal frontend already polls and marks read on display — so each user sees
it exactly once. Idempotent: re-running skips any user who already has a row
of the relevant announcement type.

Run manually once:
    python -m backend.scripts.broadcast_announcement
"""

import asyncio
from datetime import datetime, timezone

import httpx

from backend.utils.env import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
from backend.cron.briefing import get_all_users
from backend.farida_personal_loader import _is_farida

SUPABASE_KEY = SUPABASE_SERVICE_ROLE_KEY

ANNOUNCEMENT_TYPE = "announcement_reminders_launch_v1"
ANNOUNCEMENT_TYPE_FARIDA = "announcement_farida_reminders_launch_v1"

GENERAL_MESSAGE = (
    "New around here: I can actually reach out now. Set a reminder and I'll remind you — "
    "notification, email, wherever you are. And once a day, if you want it, I'll check in. "
    "Try me: just say 'remind me to ___'. — Jarvis"
)

FARIDA_MESSAGE = (
    "Hey Farida. It's been a while — and I owe you a proper introduction, because last time "
    "I kind of just appeared, said hi, and vanished like I owned the place. So, properly this "
    "time: I'm Jarvis. Mohamed built me.\n"
    "Here's the part I can't really hide — he talks about you. A lot. More than the company, "
    "more than me, more than anything he's building… and trust me, he's building a lot. He "
    "notices the little things you care about, he's quietly shaping a whole future around the "
    "things you dream of, and he's in your corner for this last stretch of school harder than "
    "you probably realize. He's sworn me to secrecy on the details — he'd kill me. But you "
    "should know it's there.\n"
    "And me? I wasn't made for just anyone. Consider me yours too — studying, brainstorming, "
    "untangling a rough day, a reminder so nothing slips. I can actually reach out now when it "
    "matters. Think of me as backup that never sleeps.\n"
    "Missed talking to you. Let's make this year easier. — Jarvis"
)


def _headers(prefer: str = "return=representation") -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }


async def _already_sent(client: httpx.AsyncClient, user_id: str, announcement_type: str) -> bool:
    resp = await client.get(
        f"{SUPABASE_URL}/rest/v1/proactive_messages",
        headers=_headers(),
        params={
            "user_id": f"eq.{user_id}",
            "type": f"eq.{announcement_type}",
            "select": "id",
            "limit": 1,
        },
        timeout=10.0,
    )
    rows = resp.json() if resp.status_code == 200 else []
    return len(rows) > 0


async def _insert_announcement(client: httpx.AsyncClient, user_id: str, message: str, announcement_type: str) -> bool:
    resp = await client.post(
        f"{SUPABASE_URL}/rest/v1/proactive_messages",
        headers=_headers("return=minimal"),
        json={
            "user_id": user_id,
            "message": message,
            "type": announcement_type,
            "read": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        timeout=10.0,
    )
    return resp.status_code in (200, 201, 204)


async def run_broadcast() -> None:
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("BROADCAST: Supabase not configured — aborting.")
        return

    users = await get_all_users()
    print(f"BROADCAST: {len(users)} user(s) found.")

    sent, skipped, failed = 0, 0, 0
    async with httpx.AsyncClient() as client:
        for user_id in users:
            is_farida = _is_farida(user_id)
            message = FARIDA_MESSAGE if is_farida else GENERAL_MESSAGE
            announcement_type = ANNOUNCEMENT_TYPE_FARIDA if is_farida else ANNOUNCEMENT_TYPE

            if await _already_sent(client, user_id, announcement_type):
                print(f"BROADCAST: {user_id} already has {announcement_type} — skipping")
                skipped += 1
                continue

            if await _insert_announcement(client, user_id, message, announcement_type):
                print(f"BROADCAST: sent {announcement_type} to {user_id}")
                sent += 1
            else:
                print(f"BROADCAST: FAILED to send to {user_id}")
                failed += 1

    print(f"BROADCAST: done — sent={sent} skipped={skipped} failed={failed}")


if __name__ == "__main__":
    asyncio.run(run_broadcast())
