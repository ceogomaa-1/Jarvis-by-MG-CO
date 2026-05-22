import os
from datetime import datetime, timedelta

import httpx
import pytz

from backend.tools.registry import register_tool

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID") or os.getenv("GOOGLE_AUTH_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET") or os.getenv("GOOGLE_AUTH_SECRET", "")


async def get_access_token(refresh_token: str) -> str:
    """Exchange refresh token for access token. Returns "" on failure."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=10.0,
        )
    if resp.status_code != 200:
        print(f"GCAL: Token refresh FAILED — status={resp.status_code} body={resp.text[:400]}")
        return ""
    data = resp.json()
    token = data.get("access_token", "")
    if not token:
        print(f"GCAL: Token refresh returned 200 but no access_token — body={resp.text[:400]}")
    return token


async def get_user_refresh_token(user_id: str) -> str:
    """Retrieve stored Google refresh token for this user from Supabase."""
    supabase_url = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if not supabase_url or not supabase_key:
        return ""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{supabase_url}/rest/v1/user_google_tokens",
            headers={
                "apikey": supabase_key,
                "Authorization": f"Bearer {supabase_key}",
            },
            params={"user_id": f"eq.{user_id}", "limit": 1},
        )
    rows = resp.json() if resp.status_code == 200 else []
    return rows[0].get("refresh_token", "") if rows else ""


@register_tool(
    name="get_calendar_events",
    description="Get upcoming calendar events for the user. Use when asked about schedule, what's coming up, or upcoming meetings.",
    parameters={
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "The user's ID",
            },
            "max_results": {
                "type": "integer",
                "description": "Max number of events to return",
                "default": 5,
            },
        },
        "required": ["user_id"],
    },
)
async def get_calendar_events(user_id: str, max_results: int = 5) -> str:
    refresh_token = await get_user_refresh_token(user_id)
    if not refresh_token:
        return "No Google Calendar connected. User needs to connect their Google account."

    access_token = await get_access_token(refresh_token)
    if not access_token:
        return "Google Calendar auth expired. Please reconnect your Google account."

    eastern = pytz.timezone("America/Toronto")
    now = datetime.now(eastern).isoformat()

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://www.googleapis.com/calendar/v3/calendars/primary/events",
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "timeMin": now,
                "maxResults": max_results,
                "singleEvents": True,
                "orderBy": "startTime",
            },
            timeout=10.0,
        )

    if resp.status_code == 401:
        return "Google Calendar access expired. Please reconnect your Google account."
    if resp.status_code != 200:
        print(f"GCAL: Events fetch failed ({resp.status_code})")
        return "Could not fetch calendar right now."

    events = resp.json().get("items", [])
    if not events:
        return "No upcoming events found."

    lines = []
    for e in events:
        title = e.get("summary", "Untitled")
        start = e.get("start", {})
        time = start.get("dateTime", start.get("date", ""))
        lines.append(f"- {title}: {time}")

    return "Upcoming events:\n" + "\n".join(lines)


@register_tool(
    name="create_calendar_event",
    description="Create a calendar event or reminder. Use when user asks to schedule something, set a reminder, or block time.",
    parameters={
        "type": "object",
        "properties": {
            "user_id": {"type": "string"},
            "title": {
                "type": "string",
                "description": "Event title",
            },
            "start_time": {
                "type": "string",
                "description": "Start time in ISO format e.g. 2026-05-18T20:00:00",
            },
            "end_time": {
                "type": "string",
                "description": "End time in ISO format. If not specified, 1 hour after start.",
            },
            "description": {
                "type": "string",
                "description": "Event description or notes",
                "default": "",
            },
        },
        "required": ["user_id", "title", "start_time"],
    },
)
async def create_calendar_event(
    user_id: str,
    title: str,
    start_time: str,
    end_time: str = "",
    description: str = "",
) -> str:
    refresh_token = await get_user_refresh_token(user_id)
    if not refresh_token:
        return "No Google Calendar connected. Ask the user to connect their Google account at /auth/google."

    access_token = await get_access_token(refresh_token)
    if not access_token:
        return "Google Calendar auth expired. Please reconnect your Google account."

    eastern = pytz.timezone("America/Toronto")
    try:
        start_dt = datetime.fromisoformat(start_time)
        if start_dt.tzinfo is None:
            start_dt = eastern.localize(start_dt)
        start_time = start_dt.isoformat()

        if end_time:
            end_dt = datetime.fromisoformat(end_time)
            if end_dt.tzinfo is None:
                end_dt = eastern.localize(end_dt)
            end_time = end_dt.isoformat()
        else:
            end_time = (start_dt + timedelta(hours=1)).isoformat()
    except Exception:
        pass

    event = {
        "summary": title,
        "description": description,
        "start": {"dateTime": start_time, "timeZone": "America/Toronto"},
        "end": {"dateTime": end_time, "timeZone": "America/Toronto"},
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://www.googleapis.com/calendar/v3/calendars/primary/events",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json=event,
        )

    if resp.status_code in (200, 201):
        return f"Done. '{title}' is on the calendar."
    if resp.status_code == 401:
        return "Google Calendar access expired. Please reconnect your Google account."
    print(f"GCAL: Create event failed ({resp.status_code}): {resp.text[:200]}")
    return "Could not create the event. Try again in a moment."
