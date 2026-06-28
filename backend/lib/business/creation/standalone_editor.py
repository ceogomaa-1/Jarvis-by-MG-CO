"""Surgical editor for saved standalone website artifacts.

The model returns exact replacement operations instead of regenerating the whole page. That keeps
unrequested design/code intact, reduces output tokens, and makes every mutation auditable before
the updated HTML is persisted or redeployed.
"""
from __future__ import annotations

import os
from typing import Any

from anthropic import AsyncAnthropic

from backend.lib.business.cost import UsageAccumulator
from backend.lib.business.model_router import SONNET
from backend.lib.business.creation.website_quality import validate_standalone_html

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
_EDITOR_MODEL = os.getenv("JARVIS_WEBSITE_EDITOR_MODEL", SONNET)
_EDITOR_TIMEOUT = 240.0
_EDITOR_MAX_TOKENS = 8_000
_MAX_OPERATIONS = 12


class WebsiteEditError(RuntimeError):
    """Raised when a website edit cannot be applied and validated safely."""


_SYSTEM_PROMPT = """\
You are a precise senior front-end engineer editing an existing single-file HTML website.

Apply ONLY the requested change. Preserve every unrelated visual choice, section, interaction,
fact, link, responsive behavior, accessibility feature, and animation. Do not redesign or rewrite
anything the operator did not request.

Return exact, non-overlapping replacement operations:
- `old` must be copied byte-for-byte from CURRENT HTML and occur exactly once at application time.
- `new` is the complete replacement; use an empty string only for an explicit deletion.
- Include enough surrounding markup in `old` to make it unique, but keep each operation focused.
- Order operations so an earlier replacement never modifies a later operation's `old` text.
- Use at most 12 operations.

Never add Jarvis, MG&CO, AI, generator, builder, "powered by", chat UI, prompts, explanations,
markdown fences, TODOs, placeholders, invented claims, or fake business facts to the website.
"""

_EDIT_TOOL: dict[str, Any] = {
    "name": "edit_page",
    "description": (
        "Return a minimal set of exact replacements that surgically applies the requested website "
        "change without regenerating unrelated code."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "One short sentence describing exactly what changed.",
            },
            "operations": {
                "type": "array",
                "maxItems": _MAX_OPERATIONS,
                "items": {
                    "type": "object",
                    "properties": {
                        "old": {
                            "type": "string",
                            "description": "Exact unique text copied byte-for-byte from CURRENT HTML.",
                        },
                        "new": {
                            "type": "string",
                            "description": "Complete replacement text.",
                        },
                    },
                    "required": ["old", "new"],
                },
            },
        },
        "required": ["summary", "operations"],
    },
}


def apply_exact_operations(html: str, operations: list[dict]) -> str:
    """Apply validated exact replacements sequentially, failing closed on ambiguity."""
    if not operations:
        raise WebsiteEditError("The editor returned no website changes.")
    if len(operations) > _MAX_OPERATIONS:
        raise WebsiteEditError(f"The edit exceeded the {_MAX_OPERATIONS}-operation safety limit.")

    updated = html
    for index, operation in enumerate(operations, start=1):
        old = operation.get("old")
        new = operation.get("new")
        if not isinstance(old, str) or not old:
            raise WebsiteEditError(f"Edit operation {index} did not include valid source HTML.")
        if not isinstance(new, str):
            raise WebsiteEditError(f"Edit operation {index} did not include valid replacement HTML.")
        if old == new:
            raise WebsiteEditError(f"Edit operation {index} would not change the website.")
        occurrences = updated.count(old)
        if occurrences != 1:
            raise WebsiteEditError(
                f"Edit operation {index} was unsafe: its source matched {occurrences} locations."
            )
        updated = updated.replace(old, new, 1)

    if updated == html:
        raise WebsiteEditError("The requested edit produced no website change.")
    return updated


async def edit_standalone_page(
    html: str,
    instruction: str,
    context: dict | None = None,
) -> dict[str, str]:
    """Generate, apply, and quality-check a surgical update to one saved HTML artifact."""
    html = html or ""
    instruction = (instruction or "").strip()
    context = dict(context or {})
    if not html:
        raise WebsiteEditError("The saved website HTML is empty.")
    if not instruction:
        raise WebsiteEditError("Describe the website change you want.")
    if not ANTHROPIC_API_KEY:
        raise WebsiteEditError("Website editing is unavailable because the API key is not configured.")

    client = AsyncAnthropic(
        api_key=ANTHROPIC_API_KEY,
        timeout=_EDITOR_TIMEOUT,
        max_retries=1,
    )
    content = [
        {
            "type": "text",
            "text": "CURRENT HTML (source of truth):\n" + html,
        },
        {
            "type": "text",
            "text": (
                "SURGICAL EDIT INSTRUCTION:\n"
                + instruction
                + "\n\nReturn only the forced edit_page tool call."
            ),
        },
    ]

    async with client.messages.stream(
        model=_EDITOR_MODEL,
        max_tokens=_EDITOR_MAX_TOKENS,
        system=[{
            "type": "text",
            "text": _SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }],
        tools=[{**_EDIT_TOOL, "cache_control": {"type": "ephemeral"}}],
        tool_choice={"type": "tool", "name": "edit_page"},
        messages=[{"role": "user", "content": content}],
    ) as stream:
        message = await stream.get_final_message()

    usage = UsageAccumulator(_EDITOR_MODEL)
    usage.add_sdk_usage(getattr(message, "usage", None))
    print(f"[WEBSITE_EDIT] {usage.log_line()}")

    payload: dict[str, Any] | None = None
    for block in message.content:
        if block.type == "tool_use" and block.name == "edit_page":
            payload = dict(block.input or {})
            break
    if not payload:
        raise WebsiteEditError("The editor completed without returning safe website changes.")

    updated = apply_exact_operations(html, payload.get("operations") or [])
    original_request = str(context.get("original_request") or "Edit the existing client website")
    quality_errors = validate_standalone_html(updated, original_request, context)
    if quality_errors:
        raise WebsiteEditError(
            "The edited website failed its safety checks: " + "; ".join(quality_errors[:5])
        )

    return {
        "html": updated,
        "summary": str(payload.get("summary") or "Applied the requested website edit.").strip()[:300],
    }
