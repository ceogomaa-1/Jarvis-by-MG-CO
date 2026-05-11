import json
import traceback
from datetime import datetime, timezone
from pathlib import Path

from backend.llm import jarvis_think

_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "user_models"

# ─── Schema ───────────────────────────────────────────────────────────────────

def _fresh_model(user_id: str) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "user_id": user_id,
        "created_at": now,
        "last_updated": now,
        "onboarding_complete": False,
        "onboarding_messages_count": 0,
        "identity": {
            "name": "",
            "preferred_name": "",
            "role": "",
            "company": "",
            "location": "",
            "age": "",
        },
        "personality": {
            "communication_style": "",
            "tone_preference": "",
            "response_length_preference": "",
            "humor_level": "",
            "directness": "",
        },
        "current_focus": {
            "top_goals": [],
            "active_projects": [],
            "biggest_challenges": [],
            "current_priorities": [],
        },
        "work_context": {
            "industry": "",
            "team_size": "",
            "key_people": [],
            "tools_used": [],
        },
        "emotional_patterns": {
            "current_energy_level": "",
            "stress_indicators": [],
            "motivation_triggers": [],
            "last_emotional_signal": "",
        },
        "jarvis_relationship": {
            "interaction_count": 0,
            "trust_level": "new",
            "inside_references": [],
            "things_jarvis_should_never_forget": [],
        },
    }


# ─── Persistence ──────────────────────────────────────────────────────────────

async def get_user_model(user_id: str) -> dict:
    """Load the user model from disk. Creates a fresh one if it doesn't exist yet."""
    path = _DATA_DIR / f"{user_id}.json"
    try:
        if not path.exists():
            model = _fresh_model(user_id)
            await save_user_model(user_id, model)
            return model
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"USER_MODEL: ERROR loading model for {user_id}: {e}")
        traceback.print_exc()
        return _fresh_model(user_id)


async def save_user_model(user_id: str, model: dict) -> bool:
    """Persist the user model to disk, stamping last_updated."""
    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        model["last_updated"] = datetime.now(timezone.utc).isoformat()
        path = _DATA_DIR / f"{user_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(model, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"USER_MODEL: ERROR saving model for {user_id}: {e}")
        traceback.print_exc()
        return False


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _trust_level(count: int) -> str:
    if count <= 5:
        return "new"
    elif count <= 20:
        return "getting_to_know"
    elif count <= 50:
        return "familiar"
    return "trusted"


def _deep_merge(base: dict, updates: dict) -> dict:
    """Merge updates into base. Lists append + deduplicate; scalars overwrite."""
    for key, value in updates.items():
        if key not in base:
            base[key] = value
        elif isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        elif isinstance(base[key], list) and isinstance(value, list):
            seen = set()
            merged = []
            for item in base[key] + value:
                k = json.dumps(item, sort_keys=True) if isinstance(item, dict) else str(item)
                if k not in seen:
                    seen.add(k)
                    merged.append(item)
            base[key] = merged
        else:
            base[key] = value
    return base


# ─── Core update ──────────────────────────────────────────────────────────────

async def update_user_model(user_id: str, user_message: str, jarvis_response: str) -> bool:
    """Analyze a conversation exchange and update the user's persistent profile.
    Increments interaction count, detects emotional signals, and uses Claude to
    extract structured facts about the user from what they just said."""
    print(f"USER_MODEL: Updating for user {user_id}")
    try:
        model = await get_user_model(user_id)

        # Increment interaction count and recalculate trust level
        model["jarvis_relationship"]["interaction_count"] += 1
        model["jarvis_relationship"]["trust_level"] = _trust_level(
            model["jarvis_relationship"]["interaction_count"]
        )
        print(f"USER_MODEL: Current interaction count: {model['jarvis_relationship']['interaction_count']}")

        # Detect emotional signal from the raw message text
        msg_lower = user_message.lower()
        stress_kw = {"stressed", "overwhelmed", "frustrated", "stuck", "behind", "tired", "struggling"}
        energy_kw = {"excited", "pumped", "good", "great", "crushing it", "let's go", "fired up"}

        if any(k in msg_lower for k in stress_kw):
            model["emotional_patterns"]["current_energy_level"] = "low"
            model["emotional_patterns"]["last_emotional_signal"] = "stress"
        elif any(k in msg_lower for k in energy_kw):
            model["emotional_patterns"]["current_energy_level"] = "high"
            model["emotional_patterns"]["last_emotional_signal"] = "energized"

        # Ask Claude to extract any new structured facts from this exchange
        extraction_prompt = (
            f'Analyze this conversation exchange and extract any new information about the user to update their profile.\n\n'
            f'User message: "{user_message}"\n'
            f'Jarvis response: "{jarvis_response}"\n\n'
            f'Current user profile:\n{json.dumps(model, indent=2)}\n\n'
            f'Return ONLY a valid JSON object with ONLY the fields that should be updated based on this exchange. '
            f'Do not include fields that have not changed. Do not include any explanation or markdown. Only return the JSON.\n\n'
            f'Examples of what to extract:\n'
            f'- If user mentions their name → update identity.name\n'
            f'- If user mentions their company → update identity.company\n'
            f'- If user mentions a goal → add to current_focus.top_goals\n'
            f'- If user mentions a project → add to current_focus.active_projects\n'
            f'- If user mentions a person → add to work_context.key_people\n'
            f'- If user shows a communication preference → update personality fields\n'
            f'- If user mentions something critical to remember → add to jarvis_relationship.things_jarvis_should_never_forget\n\n'
            f'If nothing meaningful to extract, return empty object: {{}}'
        )

        try:
            raw = await jarvis_think(
                user_message=extraction_prompt,
                conversation_history=[],
                system_override=(
                    "You are a JSON data extraction assistant. Your only job is to analyze "
                    "conversation exchanges and extract structured user profile updates. "
                    "Respond with valid JSON only. Never include markdown, code fences, "
                    "explanations, or any text outside the JSON object."
                ),
            )
            print(f"USER_MODEL: Claude extraction result: {raw}")
            # Strip markdown fences in case Claude wraps the JSON anyway
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            raw = raw.strip()
            extracted = json.loads(raw)
            if extracted:
                model = _deep_merge(model, extracted)
        except Exception as e:
            # Never let extraction failure prevent saving the interaction count + emotional signal
            print(f"USER_MODEL: JSON extraction failed for {user_id}: {e}")
            traceback.print_exc()

        save_result = await save_user_model(user_id, model)
        print(f"USER_MODEL: Save result: {save_result}")
        return True

    except Exception as e:
        print(f"USER_MODEL: ERROR in update_user_model for {user_id}: {e}")
        traceback.print_exc()
        return False


# ─── Prompt summary ───────────────────────────────────────────────────────────

async def summarize_user_for_prompt(user_id: str) -> str:
    """Convert the user model into a readable block for injection into jarvis_think()."""
    try:
        model = await get_user_model(user_id)

        identity = model.get("identity", {})
        personality = model.get("personality", {})
        focus = model.get("current_focus", {})
        work = model.get("work_context", {})
        emotional = model.get("emotional_patterns", {})
        relationship = model.get("jarvis_relationship", {})

        name = identity.get("preferred_name") or identity.get("name") or ""
        role = identity.get("role") or ""
        company = identity.get("company") or ""
        trust = relationship.get("trust_level", "new")
        count = relationship.get("interaction_count", 0)
        energy = emotional.get("current_energy_level", "")

        if not name and count < 2:
            return "New user — still getting to know them. Ask questions."

        lines = ["USER PROFILE:"]

        role_company = " at ".join(filter(None, [role, company]))
        if name:
            lines.append(f"Name: {name}")
        if role_company:
            lines.append(f"Role: {role_company}")

        lines.append(f"Trust level with Jarvis: {trust} ({count} interactions)")

        if energy:
            lines.append(f"Current energy: {energy}")

        goals = focus.get("top_goals", [])
        if goals:
            lines.append("TOP GOALS:\n" + "\n".join(f"- {g}" for g in goals))

        projects = focus.get("active_projects", [])
        if projects:
            lines.append("ACTIVE PROJECTS:\n" + "\n".join(f"- {p}" for p in projects))

        challenges = focus.get("biggest_challenges", [])
        if challenges:
            lines.append("CURRENT CHALLENGES:\n" + "\n".join(f"- {c}" for c in challenges))

        key_people = work.get("key_people", [])
        if key_people:
            lines.append("KEY PEOPLE IN THEIR WORLD:\n" + "\n".join(f"- {p}" for p in key_people))

        critical = relationship.get("things_jarvis_should_never_forget", [])
        if critical:
            lines.append("THINGS TO NEVER FORGET:\n" + "\n".join(f"- {t}" for t in critical))

        style_parts = list(filter(None, [
            personality.get("communication_style", ""),
            personality.get("tone_preference", ""),
        ]))
        pref = personality.get("response_length_preference", "")
        if style_parts or pref:
            style_str = ", ".join(style_parts)
            if pref:
                style_str += (", " if style_str else "") + f"prefers {pref} responses"
            lines.append(f"COMMUNICATION STYLE:\n{style_str}")

        return "\n\n".join(lines)

    except Exception as e:
        print(f"USER_MODEL: ERROR in summarize_user_for_prompt for {user_id}: {e}")
        return ""


# ─── Onboarding ───────────────────────────────────────────────────────────────

_MEMORY_REMINDER = (
    " IMPORTANT: You DO have memory between conversations. Mem0 cloud memory is active and working. "
    "Never tell the user you don't have memory or that you start fresh each session. "
    "You remember everything from past conversations."
)

_ONBOARDING_SYSTEM_PROMPTS = {
    "identity": (
        "You are in onboarding. You're getting to know this user for the first time. "
        "Ask ONE natural, casual follow-up question to learn about their name, what they do, "
        "or what they're building or working on. Pick the most natural question given the "
        "conversation so far. Do not ask multiple questions at once."
        + _MEMORY_REMINDER
    ),
    "goals": (
        "You are in onboarding. You have a sense of who this person is. "
        "Now ask ONE question to understand their biggest goal right now, or their biggest challenge. "
        "Be direct and genuinely curious. Keep it conversational."
        + _MEMORY_REMINDER
    ),
    "personality": (
        "You are in onboarding. You know what they do and what they want. "
        "Now get to know them as a person — ask ONE question about how they like to work, "
        "what drives them, or what they need from you specifically. Make it feel personal."
        + _MEMORY_REMINDER
    ),
    "complete": (
        "Onboarding complete. You know this person well enough to be genuinely useful. "
        "Be yourself — proactive, direct, and personal. No more structured questions needed."
        + _MEMORY_REMINDER
    ),
}


async def get_onboarding_prompt(user_id: str) -> str:
    """Return the appropriate onboarding system override for the current message,
    then increment onboarding_messages_count. Marks onboarding complete at 10 messages."""
    try:
        model = await get_user_model(user_id)
        count = model.get("onboarding_messages_count", 0)

        if count >= 10:
            model["onboarding_complete"] = True
            await save_user_model(user_id, model)
            return _ONBOARDING_SYSTEM_PROMPTS["complete"]

        if count <= 3:
            prompt = _ONBOARDING_SYSTEM_PROMPTS["identity"]
        elif count <= 6:
            prompt = _ONBOARDING_SYSTEM_PROMPTS["goals"]
        else:
            prompt = _ONBOARDING_SYSTEM_PROMPTS["personality"]

        model["onboarding_messages_count"] = count + 1
        await save_user_model(user_id, model)
        return prompt

    except Exception as e:
        print(f"USER_MODEL: ERROR in get_onboarding_prompt for {user_id}: {e}")
        return _ONBOARDING_SYSTEM_PROMPTS["identity"]
