from datetime import datetime
import pytz
from backend.tools.registry import register_tool
from backend.utils.user_context import get_user_timezone


@register_tool(
    name="get_datetime",
    description="Returns the current time in the user's own local timezone. NOTE: you already have current time in your system prompt — only call this if you need a fresh re-check for a long-running operation.",
    parameters={
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "The user's ID",
            },
            "timezone": {
                "type": "string",
                "description": "Optional IANA timezone override e.g. America/Toronto. Leave empty to use the user's own timezone.",
                "default": "",
            },
        },
        "required": ["user_id"],
    },
)
async def get_datetime(user_id: str = "", timezone: str = "") -> str:
    tz_name = timezone or (await get_user_timezone(user_id)) or "America/Toronto"
    try:
        tz = pytz.timezone(tz_name)
    except Exception:
        tz = pytz.timezone("America/Toronto")
        tz_name = "America/Toronto"
    now = datetime.now(tz)
    return now.strftime("%A, %B %d, %Y at %I:%M %p %Z") + f" ({tz_name})"
