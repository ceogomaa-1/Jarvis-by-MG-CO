"""Per-user response-feedback training (Personal Rue).

Every thumbs-up/down a user gives on one of Rue's replies is stored inside
THEIR user model (user_models.model_data.response_feedback) and distilled into
a short list of durable style lessons injected into every future system prompt
for that user only. One user's feedback never affects another user's Rue.

Zero-migration by design: everything rides inside the existing user_models
JSONB blob, so this works on prod the moment it deploys.
"""

import json
import traceback
from datetime import datetime, timezone

from backend.user_model import get_user_model, save_user_model

MAX_LOG = 30        # raw feedback events kept per user (audit + distillation context)
MAX_LESSONS = 10    # distilled lessons injected into the prompt
_VALID_RATINGS = {"up", "down"}

_DISTILL_SYSTEM = (
    "You are a preference-distillation assistant. You maintain a short list of "
    "durable lessons about how ONE specific user wants their AI companion to "
    "respond, learned from their thumbs-up/thumbs-down ratings. Respond with "
    "valid JSON only. Never include markdown, code fences, explanations, or "
    "any text outside the JSON object."
)


def _distill_prompt(lessons: list, entry: dict) -> str:
    return (
        "A user just rated one of the AI's replies. Update the lesson list.\n\n"
        f"RATING: {'👍 they liked it' if entry['rating'] == 'up' else '👎 they did not like it'}\n"
        + (f"THEIR COMMENT: \"{entry['comment']}\"\n" if entry.get("comment") else "")
        + (f"WHAT THEY HAD ASKED: \"{entry.get('prompt', '')}\"\n" if entry.get("prompt") else "")
        + f"THE RATED REPLY (excerpt):\n\"{entry['response']}\"\n\n"
        f"CURRENT LESSONS:\n{json.dumps(lessons, ensure_ascii=False)}\n\n"
        "Rules:\n"
        f"- Return at most {MAX_LESSONS} lessons, each ONE short imperative sentence "
        "about HOW to respond to this user (tone, length, format, depth, what to "
        "include or avoid).\n"
        "- Generalize: extract the durable preference behind the rating, not a "
        "one-off fact about this message's topic.\n"
        "- A thumbs-up means: do more of what this reply did. A thumbs-down means: "
        "avoid what this reply did (use the comment as the reason when given).\n"
        "- Merge near-duplicates, drop lessons contradicted by newer feedback, keep "
        "the list tight and non-redundant.\n"
        "- If this rating teaches nothing new, return the current list unchanged.\n\n"
        'Return ONLY: {"lessons": ["...", "..."]}'
    )


async def _distill(lessons: list, entry: dict) -> list:
    """Ask the LLM to fold one feedback event into the lesson list.
    Any failure returns the existing lessons unchanged — feedback is still logged."""
    from backend.llm import jarvis_think  # local import: avoid circulars at module load
    try:
        raw = await jarvis_think(
            user_message=_distill_prompt(lessons, entry),
            conversation_history=[],
            system_override=_DISTILL_SYSTEM,
        )
        raw = (raw or "").strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        parsed = json.loads(raw.strip())
        new_lessons = parsed.get("lessons")
        if isinstance(new_lessons, list):
            cleaned = [str(l).strip() for l in new_lessons if str(l).strip()]
            if cleaned or entry["rating"] == "up":
                return cleaned[:MAX_LESSONS]
    except Exception as e:
        print(f"FEEDBACK_TRAINER: distillation failed: {e}")
        traceback.print_exc()
    return lessons


async def record_feedback(
    user_id: str,
    rating: str,
    message_text: str,
    user_prompt: str = "",
    comment: str = "",
) -> dict:
    """Store one feedback event in this user's model and refresh their lessons."""
    if rating not in _VALID_RATINGS:
        return {"ok": False, "reason": "invalid_rating"}
    if not (message_text or "").strip():
        return {"ok": False, "reason": "empty_message"}

    model, lookup_failed = await get_user_model(user_id)
    if lookup_failed:
        # Never write over a possibly-existing real profile with a fresh one.
        return {"ok": False, "reason": "profile_unavailable"}

    fb = model.setdefault("response_feedback", {"log": [], "lessons": []})
    fb.setdefault("log", [])
    fb.setdefault("lessons", [])

    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "rating": rating,
        "response": message_text.strip()[:600],
        "prompt": (user_prompt or "").strip()[:300],
        "comment": (comment or "").strip()[:500],
    }
    fb["log"] = (fb["log"] + [entry])[-MAX_LOG:]
    fb["lessons"] = (await _distill(fb["lessons"], entry))[:MAX_LESSONS]

    saved = await save_user_model(user_id, model)
    print(
        f"FEEDBACK_TRAINER: user={user_id} rating={rating} comment={'yes' if entry['comment'] else 'no'} "
        f"lessons={len(fb['lessons'])} saved={saved}"
    )
    return {"ok": saved, "lessons_count": len(fb["lessons"])}
