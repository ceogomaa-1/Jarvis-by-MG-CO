import os
from datetime import datetime

import httpx
import pytz

from backend.memory import get_relevant_memories
from backend.user_model import summarize_user_for_prompt

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")


async def get_all_users() -> list[str]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/user_models",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
            },
            params={"select": "user_id"},
            timeout=10.0,
        )
    rows = resp.json() if resp.status_code == 200 else []
    return [r["user_id"] for r in rows]


async def generate_morning_briefing(user_id: str) -> str:
    from backend.llm import jarvis_think
    from backend.tools.google_calendar import get_calendar_events, get_user_refresh_token

    user_model = await summarize_user_for_prompt(user_id)
    memories = await get_relevant_memories(user_id, "goals projects priorities")

    calendar_context = ""
    try:
        refresh_token = await get_user_refresh_token(user_id)
        if refresh_token:
            events = await get_calendar_events(user_id, max_results=5)
            calendar_context = f"Today's calendar: {events}"
    except Exception:
        pass

    eastern = pytz.timezone("America/Toronto")
    today = datetime.now(eastern).strftime("%A, %B %d, %Y")

    briefing = await jarvis_think(
        user_message=f"""Generate a brief, personal morning briefing for this user.

Today: {today}
{user_model}
{f"Recent context: {memories[:300]}" if memories else ""}
{calendar_context}

Write it as Jarvis would speak — direct, warm, no fluff.
2-3 sentences max. Mention what's on their calendar if anything.
Reference something personal if relevant.
End with one sharp question or observation about their day.""",
        conversation_history=[],
        system_override="You are Jarvis. Write a morning briefing exactly as you would speak it — natural, direct, personal. No greetings like 'Good morning!'. Just start talking.",
        user_id=user_id,
    )
    return briefing


async def save_briefing(user_id: str, briefing: str):
    if not SUPABASE_URL or not SUPABASE_KEY:
        return
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{SUPABASE_URL}/rest/v1/proactive_messages",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "user_id": user_id,
                "message": briefing,
                "type": "morning_briefing",
                "read": False,
                "created_at": datetime.now(pytz.utc).isoformat(),
            },
            timeout=10.0,
        )


async def run_morning_briefings():
    print("CRON: Running morning briefings...")
    users = await get_all_users()
    for user_id in users:
        try:
            briefing = await generate_morning_briefing(user_id)
            await save_briefing(user_id, briefing)
            print(f"CRON: Briefing generated for {user_id}")
        except Exception as e:
            print(f"CRON: Failed for {user_id}: {e}")
