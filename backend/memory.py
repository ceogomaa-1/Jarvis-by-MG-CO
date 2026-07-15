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
# Mem0's MemoryClient.__init__ makes a live HTTP call to api.mem0.ai to validate the
# key. A missing/invalid key OR any Mem0-side outage at boot must NOT take down the
# whole app (Personal + Business). Degrade gracefully: _client stays None and every
# memory function below early-returns its safe default.
try:
    _client = MemoryClient(api_key=MEM0_API_KEY)
    print("MEMORY: MemoryClient initialized successfully.")
except Exception as _e:
    _client = None
    print(f"MEMORY: WARNING — MemoryClient init failed ({_e}). Memory features are "
          f"degraded for this process, but the app will still boot and serve requests.")


async def save_interaction(user_id: str, user_message: str, jarvis_response: str) -> bool:
    """Save a conversation exchange to Mem0. Mem0 automatically extracts facts,
    preferences, and patterns and stores them as searchable memories for this user."""
    messages = [
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": jarvis_response},
    ]
    if _client is None:
        return False
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


# Returned in place of "" when the Mem0 lookup itself failed (rate limit, error) —
# distinct from "" which means the lookup succeeded and found nothing relevant.
# Lets the model say "memory lookup is having an issue" instead of implying it
# has no memories of this user at all.
MEMORY_LOOKUP_FAILED_NOTE = (
    "(memory lookup temporarily unavailable — this does not mean there's nothing "
    "to know about the user, just that it couldn't be retrieved right now)"
)


async def get_relevant_memories(user_id: str, current_message: str) -> str:
    """Search Mem0 for memories relevant to the current message and return them
    as a formatted string ready to inject into jarvis_think() as memory_context."""
    if _client is None:
        return ""
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
            return MEMORY_LOOKUP_FAILED_NOTE
        print(f"MEMORY: ERROR — get_relevant_memories failed for user {user_id}: {e}")
        traceback.print_exc()
        return MEMORY_LOOKUP_FAILED_NOTE


async def extract_emotional_context(
    user_id: str,
    user_message: str,
    assistant_response: str,
) -> dict:
    """Extract emotional signals from a conversation exchange."""
    import json
    from backend.llm import extract_structured_json

    prompt = (
        f'Analyze this conversation exchange for emotional signals.\n\n'
        f'User said: "{user_message}"\n'
        f'Rue responded: "{assistant_response}"\n\n'
        f'Extract ONLY if clearly present:\n'
        f'- emotion: what emotion the user showed (excited/stressed/tired/happy/frustrated/proud/worried/none)\n'
        f'- intensity: low/medium/high\n'
        f'- about: what topic triggered this emotion (one phrase)\n'
        f'- note: one sentence capturing the emotional moment\n\n'
        f'Return ONLY valid JSON like:\n'
        f'{{"emotion": "excited", "intensity": "high", "about": "YC application", "note": "User was fired up about pitching Rue to YC"}}\n\n'
        f'If no clear emotion, return: {{"emotion": "none"}}'
    )

    try:
        raw = await extract_structured_json(
            prompt=prompt,
            system="Extract emotional signals. Return only valid JSON. No markdown.",
            where="personal_emotion_extraction",
        )
        raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        return json.loads(raw)
    except Exception:
        return {"emotion": "none"}


async def extract_and_save_feedback_memory(
    user_id: str,
    user_message: str,
    assistant_response: str,
    feedback_was_requested: bool,
) -> None:
    """
    Detect and store Rue-specific feedback memories.

    Two things it does:
    1. If feedback was requested this turn, saves a 'feedback_requested: <date>' memory
       so should_ask_for_feedback() won't ask again for 7 days.
    2. If the user's message contains explicit feedback about Rue, saves the
       user's wording directly with a 'jarvis_feedback:' tag.
    """
    from datetime import date as _date

    today = _date.today().isoformat()

    if feedback_was_requested:
        try:
            await asyncio.to_thread(
                _client.add,
                [{"role": "assistant", "content": f"feedback_requested: {today}"}],
                user_id=user_id,
            )
            print(f"MEMORY: saved feedback_requested tag for {user_id}")
        except Exception as e:
            print(f"MEMORY: ERROR saving feedback_requested tag: {e}")

    # Only capture explicit feedback about Rue. The old keyword set included
    # generic words such as "you", "help", and "feel like", which launched a
    # second Sonnet call on ordinary emotional conversations.
    import re
    feedback_pattern = re.compile(
        r"(?:\b(?:rue|jarvis|you(?:'re| are)?)\b.{0,60}\b(?:helpful|unhelpful|"
        r"too formal|too verbose|too long|too short|annoying|amazing|better if|"
        r"wish you|prefer when|love how|like how|hate how|need you to)\b)|"
        r"(?:\b(?:feedback|better if|wish you|prefer when)\b.{0,60}\b(?:rue|jarvis|you)\b)",
        re.IGNORECASE | re.DOTALL,
    )
    if not feedback_pattern.search(user_message):
        return

    # Preserve the user's own wording directly. Mem0 can index this fact without
    # paying another model to paraphrase it (and without risking a false rewrite).
    try:
        fact = "jarvis_feedback: " + re.sub(r"\s+", " ", user_message).strip()[:700]
        await asyncio.to_thread(
            _client.add,
            [{"role": "user", "content": fact}],
            user_id=user_id,
        )
        print(f"MEMORY: saved explicit Rue feedback for {user_id}")
    except Exception as e:
        print(f"MEMORY: ERROR in extract_and_save_feedback_memory: {e}")


# Expose the underlying client for direct adds (emotional memories)
memory_client = _client


async def get_all_memories(user_id: str) -> list:
    """Return every memory Mem0 has stored for this user. Used by the debug endpoint."""
    if _client is None:
        return []
    try:
        results = await asyncio.to_thread(_client.get_all, filters={"user_id": user_id})
        if isinstance(results, dict):
            results = results.get("results", [])
        return results or []
    except Exception as e:
        print(f"MEMORY: ERROR — get_all_memories failed for user {user_id}: {e}")
        traceback.print_exc()
        return []
