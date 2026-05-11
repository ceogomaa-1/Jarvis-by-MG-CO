import asyncio
import json
import traceback
from datetime import datetime, timezone
from pathlib import Path

from backend.llm import jarvis_think
from backend.user_model import get_user_model, summarize_user_for_prompt
from backend.memory import get_relevant_memories

_PROACTIVE_DIR = Path(__file__).resolve().parent.parent / "data" / "proactive"

_COOLDOWN_HOURS = 2
_MIN_INTERACTIONS = 5

_INSIGHT_SYSTEM_OVERRIDE = (
    "You are Jarvis. You are initiating this message — the user has not said anything. "
    "You are reaching out because you've been thinking about something specific to their situation.\n\n"
    "This is NOT a check-in. This is NOT \"haven't heard from you in a while.\" "
    "You do NOT say \"Hey\" as an opener. You do NOT ask how they're doing.\n\n"
    "You have full memory of everything this person has shared with you. "
    "The memory context and user profile below contain real information about them — "
    "their actual goals, their actual situation, their actual challenges. Use it.\n\n"
    "Your job right now: look at everything you know about this person and identify ONE specific "
    "thing worth raising. It could be:\n"
    "- A contradiction you noticed in their thinking\n"
    "- A next step they haven't mentioned but should probably take\n"
    "- Something they said that deserves a follow-up\n"
    "- A risk or blind spot in their current approach\n"
    "- An idea that connects two things they've talked about\n\n"
    "Write 2-4 sentences max. Be specific. Reference their actual situation — their real goals, "
    "their real projects, their real challenges. If you can't be specific because you don't have "
    "enough context yet, do NOT send a generic message — return the exact string \"NO_INSIGHT\" "
    "instead and the system will suppress the message entirely.\n\n"
    "Never claim you don't have memory. Never say you're starting fresh. "
    "You know this person. Speak like it."
)


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _read_timestamp(path: Path) -> datetime | None:
    try:
        if not path.exists():
            return None
        return datetime.fromisoformat(path.read_text(encoding="utf-8").strip())
    except Exception:
        return None


def _write_timestamp(path: Path, dt: datetime):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dt.isoformat(), encoding="utf-8")


def _hours_since(ts: datetime | None) -> float:
    if ts is None:
        return float("inf")
    return (datetime.now() - ts).total_seconds() / 3600


# ─── Trigger detection ────────────────────────────────────────────────────────

async def check_triggers(user_id: str) -> dict | None:
    """Single insight trigger. Fires when:
    - Onboarding is complete
    - User has at least 5 interactions (enough context to say something specific)
    - At least 2 hours have passed since the last proactive message
    - No undelivered proactive message is already pending
    """
    try:
        model = await get_user_model(user_id)

        if not model.get("onboarding_complete", False):
            return None

        if model["jarvis_relationship"]["interaction_count"] < _MIN_INTERACTIONS:
            return None

        if _hours_since(_read_timestamp(_PROACTIVE_DIR / f"{user_id}_last_sent.txt")) < _COOLDOWN_HOURS:
            return None

        if (_PROACTIVE_DIR / f"{user_id}_pending.json").exists():
            return None

        return {
            "trigger_type": "insight",
            "user_id": user_id,
            "fired_at": datetime.now().isoformat(),
        }

    except Exception as e:
        print(f"TRIGGERS: check_triggers failed for {user_id}: {e}")
        traceback.print_exc()
        return None


# ─── Message generation ───────────────────────────────────────────────────────

async def generate_proactive_message(trigger: dict, user_id: str) -> str | None:
    """Generate an insight message grounded in the user's real memory and profile.
    Returns None if Claude determines there's not enough specific context to say
    something meaningful — the system suppresses those entirely."""
    try:
        memory_context, user_model_context = await asyncio.gather(
            get_relevant_memories(user_id, "what is this person working on and thinking about"),
            summarize_user_for_prompt(user_id),
        )

        raw = await jarvis_think(
            user_message="[Proactive initiation — you are starting this conversation]",
            conversation_history=[],
            memory_context=memory_context,
            user_model_context=user_model_context,
            system_override=_INSIGHT_SYSTEM_OVERRIDE,
        )

        if "NO_INSIGHT" in raw:
            print(f"TRIGGERS: Claude returned NO_INSIGHT for {user_id} — suppressing message")
            return None

        return raw

    except Exception as e:
        print(f"TRIGGERS: generate_proactive_message failed for {user_id}: {e}")
        traceback.print_exc()
        return None


# ─── Post-conversation insight analysis ──────────────────────────────────────

async def analyze_conversation_for_insight(user_id: str, user_message: str, jarvis_response: str):
    """Background task: after every chat exchange, ask Claude if there's one specific
    thing worth following up on that wasn't said. Stores the insight if it passes
    the quality gate. Has its own 3-hour cooldown. Never blocks the chat response."""
    try:
        if (_PROACTIVE_DIR / f"{user_id}_pending.json").exists():
            return  # Don't overwrite an unread insight

        if _hours_since(_read_timestamp(_PROACTIVE_DIR / f"{user_id}_last_sent.txt")) < 3:
            return  # Respect the 3-hour cooldown

        model = await get_user_model(user_id)
        if not model.get("onboarding_complete", False):
            return  # Don't interrupt onboarding

        memory_context, user_model_summary = await asyncio.gather(
            get_relevant_memories(user_id, user_message),
            summarize_user_for_prompt(user_id),
        )

        system_override = (
            f"You just had this exchange with the user:\n"
            f"User: {user_message}\n"
            f"You: {jarvis_response}\n\n"
            "You have full memory of everything about them.\n"
            f"User profile: {user_model_summary}\n"
            f"Memory context: {memory_context}\n\n"
            "Now think: is there ONE specific thing worth following up on that you didn't say in your response?\n\n"
            "This could be:\n"
            "- A contradiction or assumption they made that's worth challenging\n"
            "- A concrete next step they should take that you didn't mention\n"
            "- A connection between what they just said and something else you know about their situation\n"
            "- A risk or blind spot in their current direction\n"
            "- Something they glossed over that actually matters\n\n"
            "Requirements:\n"
            "- Must be specific to THEIR actual situation.\n"
            "- Reference real details — their real goals, projects, people, challenges.\n"
            "- Must add value beyond what you already said.\n"
            "- 2-3 sentences maximum.\n"
            "- Do not start with 'Hey' or any greeting.\n"
            "- Do not say you don't have memory.\n"
            "- If you have nothing genuinely useful to add, return exactly: NO_INSIGHT\n\n"
            "Return either the insight message or NO_INSIGHT. Nothing else."
        )

        raw = await jarvis_think(
            user_message="[Analyze the conversation and generate an insight if appropriate]",
            conversation_history=[],
            system_override=system_override,
        )

        if "NO_INSIGHT" in raw:
            print(f"TRIGGERS: analyze_conversation_for_insight — NO_INSIGHT for {user_id}")
            return

        await store_proactive_message(user_id=user_id, message=raw.strip(), trigger_type="insight")
        print(f"TRIGGERS: Insight stored for {user_id}: {raw[:60]}")

    except Exception as e:
        print(f"TRIGGERS: analyze_conversation_for_insight failed for {user_id}: {e}")
        traceback.print_exc()


# ─── Storage ──────────────────────────────────────────────────────────────────

async def store_proactive_message(user_id: str, message: str, trigger_type: str):
    """Persist a proactive message and stamp the last_sent cooldown timer."""
    try:
        _PROACTIVE_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "user_id": user_id,
            "message": message,
            "trigger_type": trigger_type,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "delivered": False,
        }
        (_PROACTIVE_DIR / f"{user_id}_pending.json").write_text(
            json.dumps(data, indent=2), encoding="utf-8"
        )
        _write_timestamp(_PROACTIVE_DIR / f"{user_id}_last_sent.txt", datetime.now())
    except Exception as e:
        print(f"TRIGGERS: store_proactive_message failed for {user_id}: {e}")
        traceback.print_exc()


async def get_pending_proactive_message(user_id: str) -> dict | None:
    """Return the pending proactive message if one exists and hasn't been delivered."""
    path = _PROACTIVE_DIR / f"{user_id}_pending.json"
    try:
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return None if data.get("delivered", True) else data
    except Exception as e:
        print(f"TRIGGERS: get_pending_proactive_message failed for {user_id}: {e}")
        return None


async def mark_proactive_delivered(user_id: str):
    """Delete the pending file after successful delivery."""
    path = _PROACTIVE_DIR / f"{user_id}_pending.json"
    try:
        if path.exists():
            path.unlink()
    except Exception as e:
        print(f"TRIGGERS: mark_proactive_delivered failed for {user_id}: {e}")
