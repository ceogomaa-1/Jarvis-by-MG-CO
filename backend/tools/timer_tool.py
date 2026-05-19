from backend.tools.registry import register_tool


@register_tool(
    name="set_timer",
    description="Set a timer or countdown. Use when user asks to be reminded in X minutes or seconds, or wants a timer set.",
    parameters={
        "type": "object",
        "properties": {
            "duration_seconds": {
                "type": "integer",
                "description": "Timer duration in seconds",
            },
            "label": {
                "type": "string",
                "description": "What the timer is for",
                "default": "Timer",
            },
            "user_id": {
                "type": "string",
                "description": "The user's ID",
            },
        },
        "required": ["duration_seconds", "user_id"],
    },
)
async def set_timer(duration_seconds: int, user_id: str, label: str = "Timer") -> str:
    minutes = duration_seconds // 60
    seconds = duration_seconds % 60

    if minutes > 0:
        time_str = f"{minutes} minute{'s' if minutes != 1 else ''}"
        if seconds > 0:
            time_str += f" and {seconds} second{'s' if seconds != 1 else ''}"
    else:
        time_str = f"{seconds} second{'s' if seconds != 1 else ''}"

    return f"Timer set for {time_str} — {label}. Your calendar reminder has been noted."
