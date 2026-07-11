"""
Compounding memory extraction for Business Rue.

After each chat exchange, Haiku extracts key facts/preferences from the conversation
and stores them as discrete memories in business_user_memories.
These are injected into every future system prompt.
"""
import asyncio
import json
import os
import re

import httpx

from backend.lib.business.mind.ingest import process_new_memory

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

_EXTRACTION_PROMPT = """\
Analyze this conversation exchange and extract any NEW facts, preferences, goals, or important context \
about the user that would be useful to remember for future conversations.

USER said: {user_message}
ASSISTANT said: {assistant_response}

Return a JSON array of memory strings. Each memory should be a single clear fact or preference.
If nothing worth remembering, return an empty array [].
Examples of good memories:
- "User's business is a dental clinic called Smile Plus in Oshawa"
- "User prefers email outreach over cold calling"
- "User's revenue target is $500K this year"
- "User has 3 employees and is looking to hire a receptionist"
- "User uses Shopify for their online store"
- "User's biggest pain point is no-show appointments"

Return ONLY a valid JSON array, nothing else."""

_DURABLE_MEMORY_RE = re.compile(
    r"\b("
    r"remember|my\s+(?:name|business|company|brand|website|email|phone|address|goal|"
    r"target|budget|team|industry|client|preference)|"
    r"our\s+(?:business|company|brand|website|goal|target|budget|team|clients?)|"
    r"i\s+(?:am|own|run|work|live|prefer|like|love|hate|use|have)|"
    r"we\s+(?:are|own|run|prefer|use|have|sell|offer)|"
    r"(?:revenue|pricing|deadline|timezone|location)\s+(?:is|are)"
    r")\b",
    re.IGNORECASE,
)
_EPHEMERAL_ONLY_RE = re.compile(
    r"^\s*(hi|hello|hey|yo|thanks?|thank\s+you|ok(?:ay)?|cool|nice|perfect|great|"
    r"yes|no|yep|nope|sure|go\s+ahead|do\s+it|continue|keep\s+going|bye)[!?.\s]*$",
    re.IGNORECASE,
)


def should_extract_memories(user_message: str, assistant_response: str = "") -> bool:
    """Avoid a second model call when the exchange contains no durable user fact."""
    text = (user_message or "").strip()
    if not text or len(text) < 12 or _EPHEMERAL_ONLY_RE.match(text):
        return False
    if _DURABLE_MEMORY_RE.search(text):
        return True
    # Longer first-person disclosures can contain useful context even without a stock phrase.
    return len(text) >= 220 and bool(re.search(r"\b(i|we|my|our)\b", text, re.IGNORECASE))


def _user_id_to_uuid(user_id: str) -> str:
    hex_id = user_id.removeprefix("user_")
    if len(hex_id) == 32 and all(c in "0123456789abcdef" for c in hex_id.lower()):
        return f"{hex_id[:8]}-{hex_id[8:12]}-{hex_id[12:16]}-{hex_id[16:20]}-{hex_id[20:]}"
    return user_id


def _store_memory_if_new(sb, user_uuid: str, memory_text: str, conversation_id: str) -> str | None:
    """Synchronous helper — run via asyncio.to_thread. Returns the new memory id, or None if duplicate/failed."""
    try:
        existing = (
            sb.table("business_user_memories")
            .select("id")
            .eq("user_id", user_uuid)
            .eq("memory", memory_text)
            .execute()
        )
        if not existing.data:
            result = sb.table("business_user_memories").insert({
                "user_id": user_uuid,
                "memory": memory_text,
                "source_conversation_id": conversation_id,
                "category": "general",
            }).execute()
            print(f"MEMORY_EXTRACT: saved memory: {memory_text[:100]}")
            rows = result.data or []
            return rows[0]["id"] if rows else None
        else:
            print(f"MEMORY_EXTRACT: duplicate, skipped: {memory_text[:60]}")
            return None
    except Exception as e:
        print(f"MEMORY_EXTRACT: SAVE FAILED: {e}")
        return None


async def extract_and_store_memories(
    user_id: str,
    conversation_id: str,
    user_message: str,
    assistant_response: str,
    sb,
) -> list[dict]:
    """
    Use Haiku to extract key facts from the exchange and store as discrete memories.
    Called as a background task after each chat exchange — never blocks the response stream.
    Returns [{"id": ..., "memory": ...}] for newly-created memories (already routed
    through process_new_memory) — feeds the 'memory_born' thought-trace event.
    """
    print(f"MEMORY_EXTRACT: called for user {user_id}, conv {conversation_id}")
    if not ANTHROPIC_API_KEY or not sb or not user_id:
        print(f"MEMORY_EXTRACT: aborting — missing api_key={bool(ANTHROPIC_API_KEY)} sb={bool(sb)} user_id={bool(user_id)}")
        return []
    if not should_extract_memories(user_message, assistant_response):
        print("MEMORY_EXTRACT: skipped — no durable user fact detected")
        return []

    user_uuid = _user_id_to_uuid(user_id)
    prompt = _EXTRACTION_PROMPT.format(
        user_message=user_message[:1000],
        assistant_response=assistant_response[:1000],
    )

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 220,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=30.0,
            )

        if resp.status_code != 200:
            print(f"MEMORY_EXTRACT: Haiku API error {resp.status_code}: {resp.text[:200]}")
            return []

        raw = resp.json().get("content", [{}])[0].get("text", "").strip()
        print(f"MEMORY_EXTRACT: Haiku returned: {raw[:300]}")

        # Strip markdown code fences if Haiku wrapped the JSON
        if raw.startswith("```"):
            lines = raw.split("\n")
            # drop first line (```json or ```) and last line (```)
            inner_lines = lines[1:] if len(lines) > 1 else lines
            if inner_lines and inner_lines[-1].strip() == "```":
                inner_lines = inner_lines[:-1]
            raw = "\n".join(inner_lines).strip()

        try:
            memories = json.loads(raw)
        except json.JSONDecodeError:
            print(f"MEMORY_EXTRACT: JSON parse failed on: {raw[:300]}")
            return []

        if not isinstance(memories, list):
            print(f"MEMORY_EXTRACT: unexpected response type: {type(memories)}")
            return []

        print(f"MEMORY_EXTRACT: extracted {len(memories)} memories")
        new_memories: list[dict] = []
        for memory_text in memories:
            if not isinstance(memory_text, str) or len(memory_text) < 10:
                continue
            new_id = await asyncio.to_thread(_store_memory_if_new, sb, user_uuid, memory_text, conversation_id)
            if new_id:
                mind_category = await process_new_memory(user_id, new_id, memory_text)
                new_memories.append({"id": new_id, "memory": memory_text, "mind_category": mind_category or "general"})

        return new_memories

    except Exception as e:
        print(f"MEMORY_EXTRACT: error: {e}")
        return []
