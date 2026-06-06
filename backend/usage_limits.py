"""
Daily message usage limits for Jarvis Business Chat.
- 15 messages/day per user (configurable via DAILY_MESSAGE_LIMIT)
- Resets at midnight Toronto time (ET)
- Admin accounts bypass limits entirely
"""

import os
from datetime import datetime, date, timedelta

import pytz

DAILY_MESSAGE_LIMIT = 15
TORONTO_TZ = pytz.timezone("America/Toronto")

# Mo's account — always unlimited
ADMIN_USER_IDS: set[str] = {
    "user_3363afdc9bca4b88893cf535c62a6687",
    *[uid.strip() for uid in os.getenv("ADMIN_USER_IDS", "").split(",") if uid.strip()],
}


def get_toronto_today() -> date:
    return datetime.now(TORONTO_TZ).date()


def get_reset_display() -> str:
    now = datetime.now(TORONTO_TZ)
    next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    diff = next_midnight - now
    hours = int(diff.total_seconds() // 3600)
    minutes = int((diff.total_seconds() % 3600) // 60)
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def get_usage(user_id: str, sb) -> dict:
    if user_id in ADMIN_USER_IDS:
        return {"used": 0, "limit": -1, "remaining": -1, "is_admin": True, "resets_in": ""}

    today = get_toronto_today()
    try:
        result = sb.table("business_daily_usage") \
            .select("message_count") \
            .eq("user_id", user_id) \
            .eq("usage_date", today.isoformat()) \
            .execute()
        used = result.data[0]["message_count"] if result.data else 0
    except Exception:
        used = 0

    remaining = max(0, DAILY_MESSAGE_LIMIT - used)
    return {
        "used": used,
        "limit": DAILY_MESSAGE_LIMIT,
        "remaining": remaining,
        "is_admin": False,
        "resets_in": get_reset_display(),
    }


def check_limit(user_id: str, sb) -> tuple[bool, dict]:
    usage = get_usage(user_id, sb)
    return (usage["is_admin"] or usage["remaining"] > 0), usage


def increment_usage(user_id: str, sb) -> dict:
    if user_id in ADMIN_USER_IDS:
        return get_usage(user_id, sb)

    today = get_toronto_today()
    try:
        result = sb.table("business_daily_usage") \
            .select("id, message_count") \
            .eq("user_id", user_id) \
            .eq("usage_date", today.isoformat()) \
            .execute()

        if result.data:
            row = result.data[0]
            sb.table("business_daily_usage") \
                .update({
                    "message_count": row["message_count"] + 1,
                    "updated_at": datetime.now(TORONTO_TZ).isoformat(),
                }) \
                .eq("id", row["id"]) \
                .execute()
        else:
            sb.table("business_daily_usage") \
                .insert({"user_id": user_id, "usage_date": today.isoformat(), "message_count": 1}) \
                .execute()
    except Exception as e:
        print(f"[USAGE] increment error for {user_id}: {e}")

    return get_usage(user_id, sb)
