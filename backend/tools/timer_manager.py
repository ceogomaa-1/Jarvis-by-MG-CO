import os
from datetime import datetime, timezone
from typing import Optional

import httpx

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

_HEADERS = lambda: {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}


async def start_timer(
    user_id: str,
    label: str = "Timer",
    duration_seconds: Optional[int] = None,
) -> dict:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return {"success": False, "error": "No database"}

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{SUPABASE_URL}/rest/v1/jarvis_timers",
            headers=_HEADERS(),
            json={
                "user_id": user_id,
                "label": label,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "duration_seconds": duration_seconds,
                "status": "running",
            },
            timeout=10.0,
        )

    if resp.status_code in (200, 201):
        if duration_seconds:
            minutes = duration_seconds // 60
            seconds = duration_seconds % 60
            time_str = f"{minutes}m {seconds}s" if minutes else f"{seconds}s"
            return {"success": True, "message": f"Timer started: {label} — {time_str}"}
        return {"success": True, "message": f"Stopwatch started: {label}. I'll track how long until you come back."}
    return {"success": False, "error": "Failed to start timer"}


async def check_timer(user_id: str, label: Optional[str] = None) -> dict:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return {"success": False, "error": "No database"}

    params = {
        "user_id": f"eq.{user_id}",
        "status": "eq.running",
        "order": "started_at.desc",
        "limit": 1,
    }
    if label:
        params["label"] = f"ilike.*{label}*"

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/jarvis_timers",
            headers=_HEADERS(),
            params=params,
            timeout=10.0,
        )

    timers = resp.json() if resp.status_code == 200 else []
    if not timers:
        return {"success": False, "error": "No active timer found"}

    timer = timers[0]
    started_at = datetime.fromisoformat(timer["started_at"].replace("Z", "+00:00"))
    elapsed = int((datetime.now(timezone.utc) - started_at).total_seconds())

    def _fmt(secs: int) -> str:
        h, rem = divmod(abs(secs), 3600)
        m, s = divmod(rem, 60)
        if h:
            return f"{h}h {m}m {s}s"
        return f"{m}m {s}s" if m else f"{s}s"

    duration = timer.get("duration_seconds")
    if duration:
        remaining = duration - elapsed
        if remaining <= 0:
            return {
                "success": True,
                "elapsed": _fmt(elapsed),
                "message": f"Timer '{timer['label']}' finished! It ran for {_fmt(elapsed)}.",
                "status": "expired",
            }
        return {
            "success": True,
            "elapsed": _fmt(elapsed),
            "remaining": _fmt(remaining),
            "message": f"Timer '{timer['label']}': {_fmt(remaining)} remaining (started {_fmt(elapsed)} ago)",
        }

    return {
        "success": True,
        "elapsed": _fmt(elapsed),
        "message": f"'{timer['label']}' has been running for {_fmt(elapsed)}.",
    }


async def stop_timer(user_id: str, label: Optional[str] = None) -> dict:
    check = await check_timer(user_id, label)
    if not check.get("success"):
        return check

    elapsed = check.get("elapsed", "unknown")

    async with httpx.AsyncClient() as client:
        await client.patch(
            f"{SUPABASE_URL}/rest/v1/jarvis_timers",
            headers=_HEADERS(),
            params={"user_id": f"eq.{user_id}", "status": "eq.running"},
            json={"status": "stopped"},
            timeout=10.0,
        )

    return {
        "success": True,
        "elapsed": elapsed,
        "message": f"Stopped. '{label or 'Timer'}' ran for {elapsed}.",
    }
