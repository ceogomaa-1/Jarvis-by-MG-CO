import asyncio
import json
import logging
import traceback
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import StreamingResponse
from backend.models.schemas import ChatRequest, ChatResponse
from backend.llm import jarvis_think
from backend.memory import get_relevant_memories, save_interaction
from backend.user_model import get_user_model, summarize_user_for_prompt, update_user_model, get_onboarding_prompt
from backend.agent import ANTHROPIC_TOOLS as AVAILABLE_TOOLS
from backend.triggers import analyze_conversation_for_insight
from backend.conversation import get_conversation_history, save_conversation_turn
from backend.utils.user_context import format_user_time_context
from backend.lib.sessions import format_session_context
from backend.routes.documents import search_user_documents

router = APIRouter()
logger = logging.getLogger(__name__)

_INTERACTION_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "last_interaction"
_FALLBACK_LLM_ERROR = "Hit a snag on my end. Try that again?"
_FALLBACK_EMPTY    = "Caught me thinking. Say that again?"
_error_buffer: deque = deque(maxlen=20)


def _log_fallback(fallback_type: str, user_msg: str, exc: Exception | None = None) -> str:
    ts = datetime.now(timezone.utc).isoformat()
    exc_summary = f"{type(exc).__name__}: {exc}" if exc else ""
    debug_str = f"{fallback_type}: {exc_summary}" if exc_summary else fallback_type
    entry = {
        "timestamp": ts,
        "user_msg": user_msg[:200],
        "fallback_type": fallback_type,
        "traceback": traceback.format_exc() if exc else None,
        "debug": debug_str,
    }
    _error_buffer.append(entry)
    if exc:
        logger.exception(f"{fallback_type} user_msg={user_msg[:200]!r}")
    else:
        logger.error(f"{fallback_type} user_msg={user_msg[:200]!r}")
    return debug_str

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
    # Gather context + history snapshot BEFORE saving user message to avoid duplication
    (
        (memory_context, user_model_context, skills_summary),
        time_ctx, session_ctx, doc_ctx, history,
    ) = await asyncio.gather(
        _get_context(request.user_id, request.message),
        format_user_time_context(request.user_id),
        format_session_context(request.user_id),
        search_user_documents(request.user_id, request.message),
        get_conversation_history(request.user_id, limit=20),
    )
    live_context = f"{time_ctx}\n{session_ctx}"
    if doc_ctx:
        memory_context += f"\n\n--- RELEVANT DOCUMENT CONTENT ---\n{doc_ctx}\n--- END ---"
    if skills_summary:
        user_model_context = f"{user_model_context}\n\n{skills_summary}" if user_model_context else skills_summary

    # Persist user message BEFORE the LLM call so it survives any failure
    await save_conversation_turn(request.user_id, "user", request.message)

    user_model = await get_user_model(request.user_id)
    system_override = None
    if not user_model.get("onboarding_complete", False):
        system_override = await get_onboarding_prompt(request.user_id)

    tone = detect_emotional_tone(request.message)
    tone_context = TONE_INSTRUCTIONS.get(tone, "")

    # Build user content — multimodal when image attached
    if request.image_base64:
        raw_b64 = request.image_base64.split(",")[1] if "," in request.image_base64 else request.image_base64
        user_content = [
            {"type": "image", "source": {"type": "base64", "media_type": request.image_type or "image/png", "data": raw_b64}},
            {"type": "text", "text": request.message or "What do you see in this image?"},
        ]
    else:
        user_content = request.message

    tools = AVAILABLE_TOOLS if not system_override else None

    # Call LLM — catch failures and return a graceful fallback so user message isn't orphaned
    debug_str = None
    try:
        response_text = await jarvis_think(
            user_message=user_content,
            conversation_history=history,
            memory_context=memory_context,
            user_model_context=user_model_context,
            system_override=system_override,
            available_tools=tools,
            tone_context=tone_context,
            user_id=request.user_id,
            live_context=live_context,
        )
    except Exception as e:
        debug_str = _log_fallback("LLM_EXCEPTION", request.message, exc=e)
        response_text = _FALLBACK_LLM_ERROR

    # Handle empty / soft-refusal responses
    if not response_text or not response_text.strip():
        debug_str = _log_fallback("EMPTY_RESPONSE", request.message)
        response_text = _FALLBACK_EMPTY

    _record_interaction(request.user_id)
    logger.info(f"CHAT: post-response tasks for user {request.user_id}")
    await asyncio.gather(
        save_interaction(request.user_id, request.message, response_text),
        update_user_model(request.user_id, request.message, response_text),
        save_conversation_turn(request.user_id, "assistant", response_text),
    )
    background_tasks.add_task(
        analyze_conversation_for_insight, request.user_id, request.message, response_text
    )
    return ChatResponse(response=response_text, user_id=request.user_id, _debug=debug_str)


# ─── Streaming endpoint ───────────────────────────────────────────────────────

@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    # Gather context + history snapshot BEFORE saving user message
    (
        (memory_context, user_model_context, skills_summary),
        time_ctx, session_ctx, doc_ctx, history,
    ) = await asyncio.gather(
        _get_context(request.user_id, request.message),
        format_user_time_context(request.user_id),
        format_session_context(request.user_id),
        search_user_documents(request.user_id, request.message),
        get_conversation_history(request.user_id, limit=20),
    )
    live_context = f"{time_ctx}\n{session_ctx}"
    if doc_ctx:
        memory_context += f"\n\n--- RELEVANT DOCUMENT CONTENT ---\n{doc_ctx}\n--- END ---"
    if skills_summary:
        user_model_context = f"{user_model_context}\n\n{skills_summary}" if user_model_context else skills_summary

    # Persist user message BEFORE streaming starts
    await save_conversation_turn(request.user_id, "user", request.message)

    user_model = await get_user_model(request.user_id)
    system_override = None
    if not user_model.get("onboarding_complete", False):
        system_override = await get_onboarding_prompt(request.user_id)

    tone = detect_emotional_tone(request.message)
    tone_context = TONE_INSTRUCTIONS.get(tone, "")

    # Build user content — multimodal when image attached
    if request.image_base64:
        raw_b64 = request.image_base64.split(",")[1] if "," in request.image_base64 else request.image_base64
        user_content = [
            {"type": "image", "source": {"type": "base64", "media_type": request.image_type or "image/png", "data": raw_b64}},
            {"type": "text", "text": request.message or "What do you see in this image?"},
        ]
    else:
        user_content = request.message

    safe_history = [
        {"role": m["role"], "content": m["content"]}
        for m in history
        if isinstance(m.get("content"), str) and m["content"].strip()
    ]
    tools = AVAILABLE_TOOLS if not system_override else None

    async def event_generator():
        response_text = _FALLBACK_LLM_ERROR
        debug_str = None
        try:
            response_text = await jarvis_think(
                user_message=user_content,
                conversation_history=safe_history,
                memory_context=memory_context,
                user_model_context=user_model_context,
                system_override=system_override,
                available_tools=tools,
                tone_context=tone_context,
                user_id=request.user_id,
                live_context=live_context,
            )
            # Handle empty / soft-refusal responses
            if not response_text or not response_text.strip():
                debug_str = _log_fallback("EMPTY_RESPONSE", request.message)
                response_text = _FALLBACK_EMPTY
        except Exception as e:
            debug_str = _log_fallback("LLM_EXCEPTION", request.message, exc=e)
            response_text = _FALLBACK_LLM_ERROR

        for char in response_text:
            yield f"data: {json.dumps(char)}\n\n"
            await asyncio.sleep(0.01)

        _record_interaction(request.user_id)
        async def _run_post_tasks():
            await asyncio.gather(
                save_interaction(request.user_id, request.message, response_text),
                update_user_model(request.user_id, request.message, response_text),
                save_conversation_turn(request.user_id, "assistant", response_text),
            )
        asyncio.create_task(_run_post_tasks())
        asyncio.create_task(
            analyze_conversation_for_insight(request.user_id, request.message, response_text)
        )
        if debug_str:
            yield f"data: [DEBUG:{debug_str}]\n\n"
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


# ─── Artifact endpoint ────────────────────────────────────────────────────────

@router.post("/chat/artifact")
async def generate_artifact(request: ChatRequest):
    import os
    import httpx

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return {"artifact": "", "error": "No API key"}

    user_prompt = (
        f'Create a complete self-contained HTML page for:\n\n'
        f'"{request.message}"\n\n'
        f'CRITICAL RULES:\n'
        f'- Output MUST be under 3000 tokens total\n'
        f'- Dark theme: background #0a0a0a, text #f3ead9, accent #c84b31\n'
        f'- Single HTML file, ALL CSS embedded in <style> tag\n'
        f'- NO external dependencies, NO CDN links\n'
        f'- Keep it concise but visually impressive\n'
        f'- The HTML MUST be complete with closing </html> tag\n'
        f'- Prioritize clean design over quantity of content\n'
        f'- Start with <!DOCTYPE html> end with </html>'
    )

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 8096,
                "system": (
                    "You are an expert HTML/CSS developer. "
                    "Output ONLY raw HTML. Start with <!DOCTYPE html> and end with </html>. "
                    "Keep total output under 3000 tokens. "
                    "No markdown, no explanation, no code fences. "
                    "Complete, valid, self-contained HTML only."
                ),
                "messages": [{"role": "user", "content": user_prompt}],
            },
            timeout=60.0,
        )

    print(f"ARTIFACT: Anthropic status {resp.status_code}")
    if resp.status_code != 200:
        print(f"ARTIFACT: Error body: {resp.text[:300]}")
        return {"artifact": "", "error": resp.text[:200]}

    data = resp.json()
    html = data.get("content", [{}])[0].get("text", "").strip()
    print(f"ARTIFACT: Got {len(html)} chars")

    # Strip any accidental markdown fences
    if "<!DOCTYPE" in html:
        html = html[html.index("<!DOCTYPE"):]
    elif "<html" in html:
        html = html[html.index("<html"):]
    if "```" in html:
        html = html.split("```")[0]

    return {"artifact": html}


# ─── Debug endpoint ───────────────────────────────────────────────────────────

@router.get("/debug/last-error")
async def debug_last_error():
    return list(_error_buffer)
