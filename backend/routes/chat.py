import asyncio
import json
from datetime import datetime
from pathlib import Path
import pytz

from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import StreamingResponse
from backend.models.schemas import ChatRequest, ChatResponse
from backend.llm import jarvis_think
from backend.memory import get_relevant_memories, save_interaction
from backend.user_model import get_user_model, summarize_user_for_prompt, update_user_model, get_onboarding_prompt
from backend.agent import ANTHROPIC_TOOLS as AVAILABLE_TOOLS
from backend.triggers import analyze_conversation_for_insight
from backend.conversation import get_conversation_history, save_conversation_turn

router = APIRouter()

_INTERACTION_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "last_interaction"

# ─── Emotional tone ───────────────────────────────────────────────────────────

def detect_emotional_tone(message: str) -> str:
    msg = message.lower()
    stressed   = ["stressed", "overwhelmed", "cant handle", "can't handle", "too much",
                  "drowning", "burning out", "exhausted", "tired"]
    excited    = ["lets go", "let's go", "pumped", "excited", "fired up", "crushing it",
                  "killing it", "amazing", "great news", "we did it"]
    frustrated = ["frustrated", "annoyed", "pissed", "not working", "broken", "hate this",
                  "why isnt", "why isn't", "ugh", "wtf", "fml", "this is bs"]
    low_energy = ["tired", "exhausted", "drained", "worn out", "need a break",
                  "cant anymore", "can't anymore", "done for today", "giving up"]

    for kw in stressed:
        if kw in msg: return "stressed"
    for kw in excited:
        if kw in msg: return "excited"
    for kw in frustrated:
        if kw in msg: return "frustrated"
    for kw in low_energy:
        if kw in msg: return "low_energy"
    return "neutral"


TONE_INSTRUCTIONS = {
    "stressed": (
        "The user seems stressed or overwhelmed right now. "
        "Don't pile on more tasks or information. "
        "Acknowledge the weight first — one sentence, genuine, not therapeutic. "
        "Then help them identify the ONE most important thing to focus on right now. "
        "Everything else can wait."
    ),
    "excited": (
        "The user is fired up. Match that energy — be sharp, fast, direct. This is momentum. "
        "Don't slow them down with caveats or qualifications. "
        "Channel the energy into the most useful direction."
    ),
    "frustrated": (
        "The user is frustrated. Don't explain why things are the way they are. Don't be defensive. "
        "Get straight to what fixes the problem. "
        "One sentence of acknowledgment max, then the solution."
    ),
    "low_energy": (
        "The user is running low. Don't demand more from them. "
        "Be gentle but useful. Help them do the minimum that still moves things forward. "
        "Or just be present if that's what they need."
    ),
    "neutral": "",
}

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _record_interaction(user_id: str):
    try:
        _INTERACTION_DIR.mkdir(parents=True, exist_ok=True)
        (_INTERACTION_DIR / f"{user_id}.txt").write_text(
            datetime.now().isoformat(), encoding="utf-8"
        )
    except Exception as e:
        print(f"CHAT: Failed to record last_interaction for {user_id}: {e}")


async def _get_context(user_id: str, message: str):
    """Fetch memory, user profile, and learned skills concurrently."""
    from backend.skills.skills_manager import get_skills_summary
    return await asyncio.gather(
        get_relevant_memories(user_id, message),
        summarize_user_for_prompt(user_id),
        get_skills_summary(user_id),
    )


# ─── Regular endpoint ─────────────────────────────────────────────────────────

@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, background_tasks: BackgroundTasks):
    from datetime import datetime
    import pytz
    eastern = pytz.timezone('America/Toronto')
    current_dt = datetime.now(eastern).strftime("Today is %A, %B %d, %Y. Current time is %I:%M %p EST.")
    memory_context, user_model_context, skills_summary = await _get_context(request.user_id, request.message)
    memory_context = f"{current_dt}\n\n{memory_context}"
    if skills_summary:
        user_model_context = f"{user_model_context}\n\n{skills_summary}" if user_model_context else skills_summary

    user_model = await get_user_model(request.user_id)
    system_override = None
    if not user_model.get("onboarding_complete", False):
        system_override = await get_onboarding_prompt(request.user_id)

    tone = detect_emotional_tone(request.message)
    tone_context = TONE_INSTRUCTIONS.get(tone, "")

    # Use DB conversation history as source of truth
    history = await get_conversation_history(request.user_id, limit=20)
    tools = AVAILABLE_TOOLS if not system_override else None

    response_text = await jarvis_think(
        user_message=request.message,
        conversation_history=history,
        memory_context=memory_context,
        user_model_context=user_model_context,
        system_override=system_override,
        available_tools=tools,
        tone_context=tone_context,
        user_id=request.user_id,
    )

    _record_interaction(request.user_id)
    print(f"CHAT: Running post-response tasks for user {request.user_id}")
    await asyncio.gather(
        save_interaction(request.user_id, request.message, response_text),
        update_user_model(request.user_id, request.message, response_text),
        save_conversation_turn(request.user_id, "user", request.message),
        save_conversation_turn(request.user_id, "assistant", response_text),
    )
    background_tasks.add_task(
        analyze_conversation_for_insight, request.user_id, request.message, response_text
    )
    return ChatResponse(response=response_text, user_id=request.user_id)


# ─── Streaming endpoint ───────────────────────────────────────────────────────

@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    memory_context, user_model_context, skills_summary = await _get_context(request.user_id, request.message)
    if skills_summary:
        user_model_context = f"{user_model_context}\n\n{skills_summary}" if user_model_context else skills_summary

    user_model = await get_user_model(request.user_id)
    system_override = None
    if not user_model.get("onboarding_complete", False):
        system_override = await get_onboarding_prompt(request.user_id)

    tone = detect_emotional_tone(request.message)
    tone_context = TONE_INSTRUCTIONS.get(tone, "")

    # Use DB conversation history as source of truth
    history = await get_conversation_history(request.user_id, limit=20)
    tools = AVAILABLE_TOOLS if not system_override else None

    async def event_generator():
        from datetime import datetime
        import pytz
        eastern = pytz.timezone('America/Toronto')
        current_dt = datetime.now(eastern).strftime("Today is %A, %B %d, %Y. Current time is %I:%M %p EST.")
        memory_context_with_dt = f"{current_dt}\n\n{memory_context}"
        try:
            response_text = await jarvis_think(
                user_message=request.message,
                conversation_history=history,
                memory_context=memory_context_with_dt,
                user_model_context=user_model_context,
                system_override=system_override,
                available_tools=tools,
                tone_context=tone_context,
                user_id=request.user_id,
            )

            for char in response_text:
                yield f"data: {json.dumps(char)}\n\n"
                await asyncio.sleep(0.01)

        except Exception as e:
            print(f"CHAT STREAM: Error for {request.user_id}: {e}")
            yield "data: [ERROR]\n\n"
            yield "data: [DONE]\n\n"
            return

        _record_interaction(request.user_id)
        async def _run_post_tasks():
            await asyncio.gather(
                save_interaction(request.user_id, request.message, response_text),
                update_user_model(request.user_id, request.message, response_text),
                save_conversation_turn(request.user_id, "user", request.message),
                save_conversation_turn(request.user_id, "assistant", response_text),
            )
        asyncio.create_task(_run_post_tasks())
        asyncio.create_task(
            analyze_conversation_for_insight(request.user_id, request.message, response_text)
        )
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
