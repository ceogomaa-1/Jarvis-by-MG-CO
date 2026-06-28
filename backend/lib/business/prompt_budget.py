"""Shared, deterministic spend guards for Jarvis model requests.

Prompt caching makes repeated prefixes cheaper, but it does not stop an old conversation or a
large tool response from growing forever. These helpers bound that variable tail while keeping
the newest context and both ends of oversized results (where summaries/errors commonly live).
"""
from __future__ import annotations

import os


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


CHAT_HISTORY_CHAR_CAP = _env_int(
    "JARVIS_CHAT_HISTORY_CHAR_CAP", 48_000, 8_000, 200_000
)
DYNAMIC_PROMPT_CHAR_CAP = _env_int(
    "JARVIS_DYNAMIC_PROMPT_CHAR_CAP", 24_000, 4_000, 100_000
)
TOOL_RESULT_CHAR_CAP = _env_int(
    "JARVIS_TOOL_RESULT_CHAR_CAP", 24_000, 4_000, 100_000
)
MAX_HISTORY_MESSAGES = _env_int(
    "JARVIS_MAX_HISTORY_MESSAGES", 24, 4, 100
)


def clip_text(value: object, char_cap: int, marker: str = "\n…[trimmed to control context cost]…\n") -> str:
    """Return text within ``char_cap``, preserving useful content at both ends."""
    text = value if isinstance(value, str) else str(value)
    if len(text) <= char_cap:
        return text
    if char_cap <= len(marker) + 2:
        return text[:char_cap]
    room = max(char_cap - len(marker), 2)
    head = (room * 2) // 3
    tail = room - head
    return text[:head] + marker + text[-tail:]


def trim_history(
    history: list[dict] | None,
    *,
    char_cap: int = CHAT_HISTORY_CHAR_CAP,
    max_messages: int = MAX_HISTORY_MESSAGES,
) -> list[dict]:
    """Keep the newest valid chat messages inside a total character budget."""
    selected: list[dict] = []
    remaining = char_cap

    valid = [
        message
        for message in (history or [])
        if message.get("role") in ("user", "assistant")
        and isinstance(message.get("content"), str)
        and message["content"].strip()
    ][-max_messages:]

    for message in reversed(valid):
        if remaining <= 0:
            break
        content = message["content"]
        clipped = clip_text(content, min(len(content), remaining))
        selected.append({"role": message["role"], "content": clipped})
        remaining -= len(clipped)

    selected.reverse()
    return selected


def cap_dynamic_prompt(prompt: str) -> str:
    return clip_text(prompt, DYNAMIC_PROMPT_CHAR_CAP) if prompt else ""


def cap_tool_result(result: object) -> str:
    return clip_text(result, TOOL_RESULT_CHAR_CAP)


def chat_output_token_budget(model: str) -> int:
    """Bound runaway prose/tool JSON while retaining headroom for real work."""
    lowered = (model or "").lower()
    if "haiku" in lowered:
        return _env_int("JARVIS_HAIKU_MAX_TOKENS", 2_048, 512, 8_192)
    if "opus" in lowered:
        return _env_int("JARVIS_OPUS_MAX_TOKENS", 6_144, 1_024, 16_384)
    return _env_int("JARVIS_SONNET_MAX_TOKENS", 4_096, 1_024, 16_384)
