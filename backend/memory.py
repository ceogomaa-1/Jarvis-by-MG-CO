import asyncio
import logging
import traceback
from mem0 import MemoryClient
try:
    from mem0.exceptions import RateLimitError
except ImportError:
    RateLimitError = None  # mem0 version doesn't expose this exception class
from backend.utils.env import MEM0_API_KEY

logger = logging.getLogger(__name__)

print(f"MEMORY: Initializing MemoryClient (cloud mode). API key present: {bool(MEM0_API_KEY)}")
_client = MemoryClient(api_key=MEM0_API_KEY)
print("MEMORY: MemoryClient initialized successfully.")


async def save_interaction(user_id: str, user_message: str, jarvis_response: str) -> bool:
    """Save a conversation exchange to Mem0. Mem0 automatically extracts facts,
    preferences, and patterns and stores them as searchable memories for this user."""
    messages = [
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": jarvis_response},
    ]
    print(f"MEMORY: Attempting to save interaction for user {user_id}")
    print(f"MEMORY: Messages being sent to Mem0: {messages}")
    try:
        result = await asyncio.to_thread(_client.add, messages, user_id=user_id)
        print(f"MEMORY: client.add() result: {result}")
        return True
    except Exception as e:
        print(f"MEMORY: ERROR — save_interaction failed for user {user_id}: {e}")
        traceback.print_exc()
        return False


async def get_relevant_memories(user_id: str, current_message: str) -> str:
    """Search Mem0 for memories relevant to the current message and return them
    as a formatted string ready to inject into jarvis_think() as memory_context."""
    try:
        results = await asyncio.to_thread(
            _client.search, current_message, filters={"user_id": user_id}, limit=10
        )
        # Mem0 may return a list or a dict with a "results" key depending on version
        if isinstance(results, dict):
            results = results.get("results", [])
        if not results:
            return ""
        lines = [f"- {r['memory']}" for r in results if r.get("memory")]
        return "\n".join(lines)
    except Exception as e:
        if RateLimitError and isinstance(e, RateLimitError):
            print(f"MEMORY: rate limited (Mem0 quota exceeded, resets June 1) — skipping for user {user_id}")
            return ""
        print(f"MEMORY: ERROR — get_relevant_memories failed for user {user_id}: {e}")
        traceback.print_exc()
        return ""


async def extract_emotional_context(
    user_id: str,
    user_message: str,
    assistant_response: str,
) -> dict:
    """Extract emotional signals from a conversation exchange."""
    import json
    from backend.llm import jarvis_think

    prompt = (
        f'Analyze this conversation exchange for emotional signals.\n\n'
        f'User said: "{user_message}"\n'
        f'Jarvis responded: "{assistant_response}"\n\n'
        f'Extract ONLY if clearly present:\n'
        f'- emotion: what emotion the user showed (excited/stressed/tired/happy/frustrated/proud/worried/none)\n'
        f'- intensity: low/medium/high\n'
        f'- about: what topic triggered this emotion (one phrase)\n'
        f'- note: one sentence capturing the emotional moment\n\n'
        f'Return ONLY valid JSON like:\n'
        f'{{"emotion": "excited", "intensity": "high", "about": "YC application", "note": "User was fired up about pitching Jarvis to YC"}}\n\n'
        f'If no clear emotion, return: {{"emotion": "none"}}'
    )

    try:
        raw = await jarvis_think(
            user_message=prompt,
            conversation_history=[],
            system_override="Extract emotional signals. Return only valid JSON. No markdown.",
        )
        raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        return json.loads(raw)
    except Exception:
        return {"emotion": "none"}


# Expose the underlying client for direct adds (emotional memories)
memory_client = _client


async def get_all_memories(user_id: str) -> list:
    """Return every memory Mem0 has stored for this user. Used by the debug endpoint."""
    try:
        results = await asyncio.to_thread(_client.get_all, filters={"user_id": user_id})
        if isinstance(results, dict):
            results = results.get("results", [])
        return results or []
    except Exception as e:
        print(f"MEMORY: ERROR — get_all_memories failed for user {user_id}: {e}")
        traceback.print_exc()
        return []
