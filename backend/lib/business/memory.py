"""
Compounding memory extraction for Business Jarvis.

After each chat exchange, Haiku extracts key facts/preferences from the conversation
and stores them as discrete memories in business_user_memories.
These are injected into every future system prompt.
"""
import asyncio
import json
import os

import httpx

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


def _user_id_to_uuid(user_id: str) -> str:
    hex_id = user_id.removeprefix("user_")
    if len(hex_id) == 32 and all(c in "0123456789abcdef" for c in hex_id.lower()):
        return f"{hex_id[:8]}-{hex_id[8:12]}-{hex_id[12:16]}-{hex_id[16:20]}-{hex_id[20:]}"
    return user_id


def _store_memory_if_new(sb, user_uuid: str, memory_text: str, conversation_id: str) -> None:
    """Synchronous helper — run via asyncio.to_thread."""
    try:
        existing = (
            sb.table("business_user_memories")
            .select("id")
            .eq("user_id", user_uuid)
            .eq("memory", memory_text)
            .execute()
        )
        if not existing.data:
            sb.table("business_user_memories").insert({
                "user_id": user_uuid,
                "memory": memory_text,
                "source_conversation_id": conversation_id,
                "category": "general",
            }).execute()
    except Exception as e:
        print(f"store_memory error: {e}")


async def extract_and_store_memories(
    user_id: str,
    conversation_id: str,
    user_message: str,
    assistant_response: str,
    sb,
) -> None:
    """
    Use Haiku to extract key facts from the exchange and store as discrete memories.
    Called as a background task after each chat exchange — never blocks the response stream.
    """
    if not ANTHROPIC_API_KEY or not sb or not user_id:
        return

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
                    "max_tokens": 500,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=30.0,
            )

        if resp.status_code != 200:
            return

        raw = resp.json().get("content", [{}])[0].get("text", "").strip()
        memories = json.loads(raw)
        if not isinstance(memories, list):
            return

        for memory_text in memories:
            if not isinstance(memory_text, str) or len(memory_text) < 10:
                continue
            await asyncio.to_thread(_store_memory_if_new, sb, user_uuid, memory_text, conversation_id)

    except (json.JSONDecodeError, KeyError):
        pass
    except Exception as e:
        print(f"extract_and_store_memories error: {e}")
