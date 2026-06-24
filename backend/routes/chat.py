import asyncio
import json
import logging
import os
import re
import time
import traceback
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from supabase import create_client
from backend.models.schemas import ChatRequest, ChatResponse
from backend.llm import jarvis_think
from backend.memory import get_relevant_memories, save_interaction
from backend.user_model import get_user_model, summarize_user_for_prompt, update_user_model, get_onboarding_prompt, is_onboarding_complete
from backend.agent import ANTHROPIC_TOOLS as AVAILABLE_TOOLS
from backend.conversation import get_conversation_history, save_conversation_turn
from backend.utils.user_context import format_user_time_context
from backend.lib.sessions import format_session_context
from backend.routes.documents import search_user_documents
from backend.tools.citation_context import init_collector, add_source, get_sources
from backend.tools.url_fetch import extract_urls, fetch_url_content
from backend.usage_limits import check_limit, increment_usage, get_usage, DAILY_MESSAGE_LIMIT
from backend.farida_personal_loader import _is_farida, load_greeting as _load_farida_greeting
from backend.lib.personal.relationship_bible import is_relationship_context, build_relationship_injection

router = APIRouter()
logger = logging.getLogger(__name__)

# ─── Proactive feedback helpers ───────────────────────────────────────────────

import random

_PERSONAL_KEYWORDS = {
    "feel", "feeling", "feelings", "stressed", "stress", "worried", "worry", "happy",
    "sad", "lost", "confused", "relationship", "family", "friend", "friends", "work",
    "dream", "goal", "goals", "scared", "excited", "tired", "grateful", "proud",
    "ashamed", "lonely", "love", "hate", "miss", "future", "past", "life", "meaning",
    "purpose", "struggle", "hard day", "difficult", "overwhelmed", "anxious", "anxiety",
    "depressed", "depression", "hurt", "broken", "hopeful", "hope", "grateful",
    "gratitude", "career", "money", "health", "therapy", "alone", "together",
}

_FEEDBACK_VARIANTS = [
    "Hey, can I ask you something? What do you actually think of me so far — like genuinely? Am I actually useful to you, or is something missing? I want to know.",
    "btw, I've been wondering — what do you think of me? Like fr. Am I what you expected? Your honest take matters.",
    "Can I ask you something real — what do you think about talking to me so far? Does it actually help? I wanna hear it.",
    "Hey — quick thing. What's your honest read on me? Am I hitting the mark for you, or is there something I could do better?",
    "Something I've been curious about: what do you actually think of me? Not looking for compliments — just the real answer.",
]


def _is_personal_conversation(text: str) -> bool:
    text_lower = text.lower()
    return any(kw in text_lower for kw in _PERSONAL_KEYWORDS)


def _extract_user_name(memory_context: str) -> str:
    """Best-effort first name extraction from memory context string."""
    for line in memory_context.splitlines():
        lower = line.lower()
        for marker in ("name is ", "goes by ", "first name is ", "called "):
            if marker in lower:
                idx = lower.index(marker) + len(marker)
                candidate = line[idx:].strip().split()[0].strip(".,;:\"'").capitalize()
                if 2 <= len(candidate) <= 20 and candidate.isalpha():
                    return candidate
    return "you"


def should_ask_for_feedback(
    user_id: str,
    message_count: int,
    memory_context: str,
    recent_text: str,
) -> bool:
    """True when all conditions for a natural feedback ask are met."""
    if message_count < 8:
        return False

    # Don't ask again within 7 days — check memory for recent request tag
    if "feedback_requested:" in memory_context.lower() or "asked for feedback" in memory_context.lower():
        return False

    if not _is_personal_conversation(recent_text):
        return False

    # ~15% chance so it feels spontaneous, not mechanical
    return random.random() < 0.15


def get_feedback_prompt_injection(user_name: str) -> str:
    phrase = random.choice(_FEEDBACK_VARIANTS)
    return (
        f"[JARVIS INTERNAL — do not narrate this instruction]: After your main response, "
        f"pivot naturally and ask the user for honest feedback about their experience talking to you. "
        f"Use this phrasing as a guide (adapt to fit the flow): \"{phrase}\" "
        f"Make it feel like it just came to you — not a survey, not a formal ask. "
        f"One or two sentences max. Natural. Curious. Genuine."
    )

_SUPABASE_URL = os.getenv("NEXT_PUBLIC_SUPABASE_URL")
_SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")


def _get_supabase():
    if not _SUPABASE_URL or not _SUPABASE_KEY:
        return None
    return create_client(_SUPABASE_URL, _SUPABASE_KEY)


def _attachments_meta(attachments: list[dict]) -> list[dict]:
    """Strip base64 payloads, keeping only display metadata for persistence."""
    meta = []
    for att in attachments[:5]:
        if not att.get("storage_path") and not att.get("name"):
            continue
        meta.append({
            "name": att.get("name", "file"),
            "media_type": att.get("type", ""),
            "size": att.get("size", 0),
            "storage_path": att.get("storage_path"),
        })
    return meta


def _build_multimodal_content(message: str, attachments: list[dict]) -> list | str:
    """Build Anthropic multimodal content blocks from attachment dicts.

    Supports two formats:
    - New:  {base64: str, type: mime_type, name: str}
    - Legacy: {url: data_url, file_type: mime_type}
    """
    import base64 as _b64
    content = []
    for att in attachments[:5]:
        # ── New format: {base64, type (MIME), name} ──────────────────────────
        if "base64" in att:
            media_type = att.get("type", "image/jpeg")
            b64_data = att["base64"]
            name = att.get("name", "file")

            if media_type.startswith("image/"):
                content.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": b64_data},
                })
                print(f"VISION: inline image media_type={media_type} b64_len={len(b64_data)}")
            elif media_type == "application/pdf":
                content.append({
                    "type": "document",
                    "source": {"type": "base64", "media_type": "application/pdf", "data": b64_data},
                })
                print(f"VISION: inline PDF name={name} b64_len={len(b64_data)}")
            else:
                try:
                    decoded = _b64.b64decode(b64_data).decode("utf-8", errors="replace")
                    content.append({"type": "text", "text": f"[Attached file: {name}]\n{decoded[:8000]}"})
                    print(f"VISION: inline text file name={name} decoded_len={len(decoded)}")
                except Exception as exc:
                    print(f"VISION: failed to decode text file name={name}: {exc}")
            continue

        # ── Legacy format: {url (data URL), file_type} ───────────────────────
        url = att.get("url", "")
        file_type = att.get("file_type", "")
        if file_type.startswith("image/") and url:
            if url.startswith("data:"):
                raw_b64 = url.split(",")[1] if "," in url else url
            else:
                print(f"CHAT: skipping non-data-URL attachment url={url[:60]}")
                continue
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": file_type, "data": raw_b64},
            })
            print(f"VISION: attached image file_type={file_type} b64_len={len(raw_b64)}")

    if not content:
        return message
    content.append({"type": "text", "text": message or "What do you see?"})
    return content

_INTERACTION_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "last_interaction"
_FALLBACK_LLM_ERROR = "Hit a snag on my end. Try that again?"
_FALLBACK_EMPTY    = "Caught me thinking. Say that again?"
_error_buffer: deque = deque(maxlen=20)

_SENTENCE_SPLIT_RE = re.compile(r'(?<=[.!?])\s+')


def _split_voice_sentences(text: str) -> list[str]:
    """Split a voice response into speakable sentences for streaming TTS."""
    parts = _SENTENCE_SPLIT_RE.split(text.strip())
    return [p.strip() for p in parts if p.strip() and len(p.strip()) > 2]


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


# ─── Study Mode tutor brain ───────────────────────────────────────────────────

STUDY_MODE_INSTRUCTION = (
    "[STUDY MODE — you are now the user's personal study tutor]\n"
    "The user opened Study Mode. Shift into tutor mode for this turn:\n"
    "- Teach for real understanding, not just answers. Be patient, clear, and encouraging.\n"
    "- Break concepts into simple steps. Use plain language first, then the precise terms.\n"
    "- Prefer the Socratic method for problems: guide with questions before giving the full answer, "
    "and check understanding as you go.\n"
    "- When asked to QUIZ: ask ONE question at a time, wait for the answer, then give specific, "
    "kind feedback before the next question. Keep score lightly.\n"
    "- When asked to SUMMARIZE: produce tight, well-structured notes (headers + bullets) that are easy to revise from.\n"
    "- When asked to RESEARCH: give a clear, organized overview and cite sources using your tools when useful.\n"
    "- If the user sends a PHOTO (a textbook page, handwritten notes, a problem, a diagram): read it carefully, "
    "transcribe or interpret what matters, then teach from it.\n"
    "- Use Markdown (headers, bold, lists, simple tables) so the material is easy to read.\n"
    "- Keep the warm, real Jarvis voice — a sharp study partner, never a dry textbook."
)


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

@router.post("/chat", response_model=None)
async def chat(request: ChatRequest):
    # ── Usage limit check ─────────────────────────────────────────────────────
    sb = _get_supabase()
    if sb and request.user_id:
        allowed, usage_info = await asyncio.to_thread(check_limit, request.user_id, sb)
        if not allowed:
            limit_msg = (
                f"You've hit your limit for now — {usage_info['limit']} messages per {usage_info.get('window_label', '4 hours')}. "
                f"Your next slot opens in {usage_info['resets_in']}. "
                f"Jarvis will be here."
            )
            return JSONResponse({"response": limit_msg, "user_id": request.user_id, "usage": usage_info})

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
    await save_conversation_turn(request.user_id, "user", request.message, attachments=_attachments_meta(request.attachments))

    # Farida's first-conversation surprise greeting — fires exactly once.
    # history was fetched before saving user message so it reflects the true prior state.
    if _is_farida(request.user_id) and not any(m.get("role") == "assistant" for m in history):
        _greeting = _load_farida_greeting()
        if _greeting:
            await save_conversation_turn(request.user_id, "assistant", _greeting)
            _record_interaction(request.user_id)
            if sb and request.user_id:
                updated_usage = await asyncio.to_thread(increment_usage, request.user_id, sb)
            else:
                updated_usage = None
            _resp: dict = {"response": _greeting, "user_id": request.user_id}
            if updated_usage:
                _resp["usage"] = updated_usage
            return JSONResponse(_resp)

    onboarding_done = await is_onboarding_complete(request.user_id)
    system_override = None
    if not onboarding_done:
        system_override = await get_onboarding_prompt(request.user_id)

    tone = detect_emotional_tone(request.message)
    tone_context = TONE_INSTRUCTIONS.get(tone, "")

    # Build user content — multimodal when image attached
    print(f"CHAT: image_base64={'SET len=' + str(len(request.image_base64)) if request.image_base64 else 'NONE'} attachments={len(request.attachments)} user_id={request.user_id}")
    if request.image_base64:
        raw_b64 = request.image_base64.split(",")[1] if "," in request.image_base64 else request.image_base64
        user_content = [
            {"type": "image", "source": {"type": "base64", "media_type": request.image_type or "image/png", "data": raw_b64}},
            {"type": "text", "text": request.message or "What do you see in this image?"},
        ]
    elif request.attachments:
        user_content = _build_multimodal_content(request.message, request.attachments)
    else:
        user_content = request.message

    tools = AVAILABLE_TOOLS if not system_override else None

    _recent = " ".join(
        m.get("content", "") if isinstance(m.get("content"), str) else ""
        for m in list(history)[-4:] + [{"role": "user", "content": request.message}]
    )

    # ── Relationship Bible injection ──────────────────────────────────────────
    _relationship_injection = ""
    if not system_override and await is_relationship_context(request.message, _recent):
        _relationship_injection = build_relationship_injection()

    # ── Proactive feedback injection ──────────────────────────────────────────
    _chat_fb_injection = ""
    if not system_override:
        if should_ask_for_feedback(request.user_id, len(history) + 1, memory_context, _recent):
            _chat_fb_injection = get_feedback_prompt_injection(_extract_user_name(memory_context))

    _effective_tone = "\n\n".join(b for b in (tone_context, _relationship_injection, _chat_fb_injection) if b)

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
            tone_context=_effective_tone,
            user_id=request.user_id,
            live_context=live_context,
            voice_mode=request.voice_mode,
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
    from backend.memory import extract_and_save_feedback_memory
    await asyncio.gather(
        save_interaction(request.user_id, request.message, response_text),
        update_user_model(request.user_id, request.message, response_text),
        save_conversation_turn(request.user_id, "assistant", response_text),
        extract_and_save_feedback_memory(
            request.user_id, request.message, response_text,
            feedback_was_requested=bool(_chat_fb_injection),
        ),
    )
    # Increment usage after successful response
    if sb and request.user_id:
        updated_usage = await asyncio.to_thread(increment_usage, request.user_id, sb)
    else:
        updated_usage = None
    resp = {"response": response_text, "user_id": request.user_id}
    if updated_usage:
        resp["usage"] = updated_usage
    if debug_str:
        resp["_debug"] = debug_str
    return JSONResponse(resp)


# ─── Streaming endpoint ───────────────────────────────────────────────────────

@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    # ── Usage limit check ─────────────────────────────────────────────────────
    sb = _get_supabase()
    if sb and request.user_id:
        allowed, usage_info = await asyncio.to_thread(check_limit, request.user_id, sb)
        if not allowed:
            limit_msg = (
                f"You've hit your limit for now — {usage_info['limit']} messages per {usage_info.get('window_label', '4 hours')}. "
                f"Your next slot opens in {usage_info['resets_in']}. "
                f"Jarvis will be here."
            )
            async def _limit_stream():
                for char in limit_msg:
                    yield f"data: {json.dumps(char)}\n\n"
                yield f"data: {json.dumps({'type': 'usage', 'data': usage_info})}\n\n"
                yield "data: [DONE]\n\n"
            return StreamingResponse(_limit_stream(), media_type="text/event-stream",
                                     headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})

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

    # ── Batch 14: URL detection + auto-fetch ──────────────────────────
    user_text = request.message if isinstance(request.message, str) else ""
    urls_in_msg = extract_urls(user_text)
    url_contents = []
    if urls_in_msg:
        print(f"CHAT_STREAM: detected {len(urls_in_msg)} URLs in user message — fetching in parallel")
        url_contents = list(await asyncio.gather(*[fetch_url_content(u) for u in urls_in_msg]))
    if url_contents:
        url_block_parts = ["\n\n--- USER-PROVIDED URLS (auto-fetched) ---"]
        for i, uc in enumerate(url_contents, 1):
            if uc.get("error"):
                url_block_parts.append(f"\n[Link {i}] {uc['url']}\n  ERROR: {uc['error']}")
            else:
                url_block_parts.append(
                    f"\n[Source {i}] {uc['title']}\n  URL: {uc['url']}\n  CONTENT:\n{uc['content']}"
                )
        url_block_parts.append("\n--- END USER-PROVIDED URLS ---")
        memory_context = (memory_context or "") + "\n".join(url_block_parts)

    # Persist user message BEFORE streaming starts
    await save_conversation_turn(request.user_id, "user", request.message, attachments=_attachments_meta(request.attachments))

    onboarding_done = await is_onboarding_complete(request.user_id)
    system_override = None
    if not onboarding_done:
        system_override = await get_onboarding_prompt(request.user_id)

    # ── Study Mode brain selection (additive, isolated, reversible) ────────────
    # Only Study Mode can ever be non-Claude. Every other path here is unchanged.
    # Resolver fails safe to Claude when Grok isn't enabled+configured.
    _study_provider = "claude"
    _provider_notice = None
    if request.study_mode and not system_override:
        from backend.lib.providers.study_provider import resolve_study_provider
        _study_provider, _provider_notice = resolve_study_provider(request.study_provider)

    tone = detect_emotional_tone(request.message)
    tone_context = TONE_INSTRUCTIONS.get(tone, "")

    # Build user content — multimodal when image attached
    print(f"CHAT_STREAM: image_base64={'SET len=' + str(len(request.image_base64)) if request.image_base64 else 'NONE'} attachments={len(request.attachments)} user_id={request.user_id}")
    if request.image_base64:
        raw_b64 = request.image_base64.split(",")[1] if "," in request.image_base64 else request.image_base64
        user_content = [
            {"type": "image", "source": {"type": "base64", "media_type": request.image_type or "image/png", "data": raw_b64}},
            {"type": "text", "text": request.message or "What do you see in this image?"},
        ]
    elif request.attachments:
        user_content = _build_multimodal_content(request.message, request.attachments)
    else:
        user_content = request.message

    safe_history = [
        {"role": m["role"], "content": m["content"]}
        for m in history
        if isinstance(m.get("content"), str) and m["content"].strip()
    ]
    tools = AVAILABLE_TOOLS if not system_override else None

    message_count = len(history) + 1
    recent_text = " ".join(
        m.get("content", "") if isinstance(m.get("content"), str) else ""
        for m in list(history)[-4:] + [{"role": "user", "content": request.message}]
    )

    # ── Relationship Bible injection ──────────────────────────────────────────
    _relationship_injection = ""
    if not system_override and await is_relationship_context(request.message, recent_text):
        _relationship_injection = build_relationship_injection()
        print(f"RELATIONSHIP_BIBLE: injecting for user_id={request.user_id}")

    # ── Proactive feedback injection ──────────────────────────────────────────
    _fb_injection = ""
    if not system_override and should_ask_for_feedback(
        request.user_id, message_count, memory_context, recent_text
    ):
        _fb_injection = get_feedback_prompt_injection(
            _extract_user_name(memory_context)
        )
        print(f"FEEDBACK: injecting feedback ask for user_id={request.user_id}")

    async def event_generator():
        # Batch 14: per-request citation collector
        init_collector()
        for uc in url_contents:
            if uc.get("error") is None:
                add_source(
                    url=uc["url"],
                    title=uc["title"],
                    snippet=uc["content"][:200],
                    source_type="user_url",
                )

        # Farida's first-conversation surprise greeting — streams verbatim, fires once.
        # history was fetched in the outer scope before saving the current user message.
        if _is_farida(request.user_id) and not any(m.get("role") == "assistant" for m in history):
            _greeting = _load_farida_greeting()
            if _greeting:
                for _ch in _greeting:
                    yield f"data: {json.dumps(_ch)}\n\n"
                    await asyncio.sleep(0.01)
                await save_conversation_turn(request.user_id, "assistant", _greeting)
                _record_interaction(request.user_id)
                if sb and request.user_id:
                    _usage = await asyncio.to_thread(increment_usage, request.user_id, sb)
                    yield f"data: {json.dumps({'type': 'usage', 'data': _usage})}\n\n"
                yield "data: [DONE]\n\n"
                return

        voice_t0 = time.time()
        print(f"CHAT_T0: user_id={request.user_id!r} voice={request.voice_mode}")

        response_text = _FALLBACK_LLM_ERROR
        debug_str = None
        _study_injection = STUDY_MODE_INSTRUCTION if (request.study_mode and not system_override) else ""
        _combined_tone = "\n\n".join(b for b in (_study_injection, tone_context, _relationship_injection, _fb_injection) if b)

        # Study Mode A/B visibility: tell the UI which brain answered (ignored elsewhere).
        if request.study_mode and not system_override:
            yield f'data: {json.dumps({"type": "provider", "value": _study_provider})}\n\n'
            if _provider_notice:
                yield f'data: {json.dumps({"type": "provider_notice", "value": _provider_notice})}\n\n'

        try:
            # Claude path — byte-identical to today's call, just wrapped so the Grok
            # branch can reuse it as a fallback without altering it.
            async def _claude_answer():
                return await jarvis_think(
                    user_message=user_content,
                    conversation_history=safe_history,
                    memory_context=memory_context,
                    user_model_context=user_model_context,
                    system_override=system_override,
                    available_tools=tools,
                    tone_context=_combined_tone,
                    user_id=request.user_id,
                    live_context=live_context,
                    voice_mode=request.voice_mode,
                )

            if _study_provider == "grok":
                from backend.lib.providers.grok import grok_think
                try:
                    response_text = await grok_think(
                        user_message=user_content,
                        conversation_history=safe_history,
                        memory_context=memory_context,
                        user_model_context=user_model_context,
                        system_override=system_override,
                        available_tools=tools,
                        tone_context=_combined_tone,
                        user_id=request.user_id,
                        live_context=live_context,
                        voice_mode=request.voice_mode,
                    )
                except Exception as _grok_err:
                    # Invalid key / network / API error → fall back to Claude, no crash.
                    print(f"STUDY_GROK_FALLBACK: {_grok_err}")
                    yield f'data: {json.dumps({"type": "provider_notice", "value": "Grok hit an error — switched to the default brain."})}\n\n'
                    yield f'data: {json.dumps({"type": "provider", "value": "claude"})}\n\n'
                    response_text = await _claude_answer()
            else:
                response_text = await _claude_answer()
            llm_ms = int((time.time() - voice_t0) * 1000)
            print(f"CHAT_LLM_DONE: {llm_ms}ms chars={len(response_text)}")
            # Handle empty / soft-refusal responses
            if not response_text or not response_text.strip():
                debug_str = _log_fallback("EMPTY_RESPONSE", request.message)
                response_text = _FALLBACK_EMPTY
        except Exception as e:
            debug_str = _log_fallback("LLM_EXCEPTION", request.message, exc=e)
            response_text = _FALLBACK_LLM_ERROR

        if request.voice_mode and response_text:
            tts_ms = int((time.time() - voice_t0) * 1000)
            print(f"CHAT_TTS_FIRE: {tts_ms}ms full_response chars={len(response_text)}")
            yield f"data: {json.dumps({'__vs': response_text})}\n\n"
            for char in response_text:
                yield f"data: {json.dumps(char)}\n\n"
        else:
            for char in response_text:
                yield f"data: {json.dumps(char)}\n\n"
                await asyncio.sleep(0.01)

        _record_interaction(request.user_id)
        async def _run_post_tasks():
            from backend.memory import extract_and_save_feedback_memory
            await asyncio.gather(
                save_interaction(request.user_id, request.message, response_text),
                update_user_model(request.user_id, request.message, response_text),
                save_conversation_turn(request.user_id, "assistant", response_text),
            )
            await extract_and_save_feedback_memory(
                request.user_id, request.message, response_text,
                feedback_was_requested=bool(_fb_injection),
            )
        asyncio.create_task(_run_post_tasks())
        if debug_str:
            yield f"data: [DEBUG:{debug_str}]\n\n"
        # Batch 14: emit sources collected during this turn
        final_sources = get_sources()
        if final_sources:
            yield f"data: {json.dumps({'__sources': final_sources})}\n\n"
        # Increment usage and emit usage event
        if sb and request.user_id:
            updated_usage = await asyncio.to_thread(increment_usage, request.user_id, sb)
            yield f"data: {json.dumps({'type': 'usage', 'data': updated_usage})}\n\n"
        done_ms = int((time.time() - voice_t0) * 1000)
        print(f"CHAT_DONE: {done_ms}ms")
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
    from backend.llm import get_current_moment_block

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return {"artifact": "", "error": "No API key"}

    moment_block = await get_current_moment_block(request.user_id)

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

    try:
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
                        f"{moment_block}\n\n---\n\n"
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
    except Exception as e:
        print(f"ARTIFACT: request failed: {e}")
        return {"artifact": "", "error": "Artifact generation is temporarily unavailable."}

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


# ─── Usage endpoint ───────────────────────────────────────────────────────────

@router.get("/usage")
async def get_personal_usage(user_id: str = ""):
    """Return today's usage info for the given Personal user."""
    if not user_id:
        return JSONResponse({"error": "user_id required"}, status_code=400)
    sb = _get_supabase()
    if not sb:
        return JSONResponse({"used": 0, "limit": DAILY_MESSAGE_LIMIT, "remaining": DAILY_MESSAGE_LIMIT, "is_admin": False, "resets_in": ""})
    usage = await asyncio.to_thread(get_usage, user_id, sb)
    return JSONResponse(usage)


# ─── Debug endpoint ───────────────────────────────────────────────────────────

@router.get("/debug/last-error")
async def debug_last_error(token: str = ""):
    """Returns recent internal error entries (real user messages + tracebacks), so it
    is gated behind an admin token. Set JARVIS_DEBUG_TOKEN in the environment and call
    with ?token=<that value>. If the token is unset or mismatched, the endpoint is
    closed (403) — never an open data leak."""
    expected = os.getenv("JARVIS_DEBUG_TOKEN", "")
    if not expected or token != expected:
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return list(_error_buffer)
