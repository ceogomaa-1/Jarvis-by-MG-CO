"""Thin Anthropic Messages API helper used by the Real Estate Operator Suite
for LLM passes (lead classification, document drafting, contact extraction)."""
import json
import re

import httpx

from backend.utils.env import ANTHROPIC_API_KEY

ANTHROPIC_VERSION = "2023-06-01"


async def call_claude(system: str, prompt: str, model: str, max_tokens: int = 1024) -> str:
    """Single-turn call to the Anthropic Messages API. Returns the concatenated text content."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": ANTHROPIC_VERSION,
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60.0,
        )
    resp.raise_for_status()
    blocks = resp.json().get("content", [])
    return "\n".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()


def parse_json_response(raw: str) -> dict | None:
    """Strip code fences and parse the first top-level JSON object found in `raw`."""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except (ValueError, json.JSONDecodeError):
        return None
