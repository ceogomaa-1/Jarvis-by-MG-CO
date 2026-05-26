from datetime import datetime
import pytz
from backend.tools.registry import register_tool


@register_tool(
    name="get_datetime",
    description="Returns the current time. NOTE: you already have current time in your system prompt — only call this if you need a fresh re-check for a long-running operation.",
    parameters={
        "type": "object",
        "properties": {
            "timezone": {
                "type": "string",
                "description": "Timezone name e.g. America/Toronto",
                "default": "America/Toronto",
            }
        },
        "required": [],
    },
)
async def get_datetime(timezone: str = "America/Toronto") -> str:
    tz = pytz.timezone(timezone)
    now = datetime.now(tz)
    return now.strftime("%A, %B %d, %Y at %I:%M %p %Z")
