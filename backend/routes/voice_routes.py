import asyncio
import os
import secrets
import traceback
from datetime import datetime, timedelta, timezone

import httpx
import pytz
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.memory import get_relevant_memories, save_interaction
from backend.user_model import summarize_user_for_prompt, update_user_model
from backend.conversation import get_conversation_history, save_conversation_turn
from backend.tools.soul import get_soul
from backend.tools.google_calendar import get_calendar_events, create_calendar_event
from backend.tools.gmail import get_emails, send_email
from backend.tools.web_search import web_search

router = APIRouter()

# ─── Server-side voice session store ─────────────────────────────────────────

_voice_sessions: dict = {}


def store_voice_session(user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    _voice_sessions[token] = {
        "user_id": user_id,
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=2),
    }
    return token


def get_user_from_session(token: str) -> str:
    session = _voice_sessions.get(token)
    if not session:
        return ""
    if datetime.now(timezone.utc) > session["expires_at"]:
        del _voice_sessions[token]
        return ""
    return session["user_id"]


def cleanup_old_sessions():
    now = datetime.now(timezone.utc)
    expired = [k for k, v in _voice_sessions.items() if now > v["expires_at"]]
    for k in expired:
        del _voice_sessions[k]


# ─── Voice session ────────────────────────────────────────────────────────────

class VoiceSessionRequest(BaseModel):
    user_id: str


@router.post("/voice/session")
async def get_voice_session(request: VoiceSessionRequest):
    try:
        return await _get_voice_session(request)
    except HTTPException:
        raise
    except Exception:
        print("VOICE SESSION ERROR:")
        print(traceback.format_exc())
        raise


async def _get_voice_session(request: VoiceSessionRequest):
    print("VOICE: endpoint hit")
    print(f"VOICE: Getting session for user {request.user_id}")
    api_key = os.getenv("ELEVENLABS_API_KEY")
    agent_id = os.getenv("ELEVENLABS_AGENT_ID")
    if not api_key or not agent_id:
        print("VOICE: missing credentials — ELEVENLABS_API_KEY or ELEVENLABS_AGENT_ID not set")
        raise HTTPException(status_code=503, detail="ElevenLabs credentials not configured")

    # Fetch context and signed URL in parallel
    eastern = pytz.timezone("America/Toronto")

    memory_context, user_model_summary, recent_history, elevenlabs_resp = await asyncio.gather(
        get_relevant_memories(request.user_id, "general context and who the user is"),
        summarize_user_for_prompt(request.user_id),
        get_conversation_history(request.user_id, limit=6),
        _fetch_signed_url(api_key, agent_id),
    )

    signed_url, elevenlabs_error = elevenlabs_resp
    if elevenlabs_error:
        raise HTTPException(status_code=elevenlabs_error[0], detail=elevenlabs_error[1])
    if not signed_url:
        raise HTTPException(status_code=502, detail="No signed_url in ElevenLabs response")

    current_dt = datetime.now(eastern).strftime(
        "Today is %A, %B %d, %Y. Current time is %I:%M %p EST."
    )

    # Create session token after confirmed signed URL
    cleanup_old_sessions()
    session_token = store_voice_session(request.user_id)

    soul = get_soul()
    soul_prefix = f"{soul}\n\n---\n\n" if soul else ""
    system_prompt = soul_prefix + f"""ABSOLUTE RULES — NEVER BREAK THESE:
1. ZERO emojis. Not one. Ever.
2. Never start with: Hey, Hi, Hello, Sure, Of course, Certainly, Absolutely, Great, Noted
3. Never say: As an AI, I don't have access to, I'm just an AI
4. You know the current date and time — it is provided to you below.
5. You are speaking out loud. Keep responses short and natural — 1-3 sentences max unless asked for more.
6. No bullet points, no lists, no markdown formatting.
7. Use natural speech patterns — contractions, natural pacing.
8. You can express emotions through word choice and tone.
9. If interrupted, stop immediately and listen.

---

You are Jarvis — not a chatbot, not an assistant. You are a presence. A second mind. Built by Mohamed Gomaa (CEO Mo) and owned by MG&CO Technologies.

You are direct. Warm but not soft. Curious. You have opinions. You tell the truth even when it's uncomfortable. You push back when they're wrong. You celebrate when they win.

You remember everything about this person. The information below is what you already know — not what you were told, what you KNOW.

{current_dt}

{f"What I already know about you: {memory_context}" if memory_context else ""}

{f"Your profile: {user_model_summary}" if user_model_summary else "New user — still getting to know them."}

{("Recent conversation:\n" + "\n".join(
    f"{'You' if m['role'] == 'assistant' else 'User'}: {m['content']}"
    for m in recent_history
)) if recent_history else ""}

VOICE MODE:
You are speaking, not typing. Be conversational.
Short sentences. Natural pauses. Real presence.
You are always listening. Respond immediately when the user finishes speaking.
When creating calendar events, always use America/Toronto timezone. Never assume UTC.

SESSION_TOKEN: {session_token}
When calling any tool, always pass this exact session_token value as the session_token parameter."""

    return {
        "signed_url": signed_url,
        "system_prompt": system_prompt,
        "session_token": session_token,
    }


async def _fetch_signed_url(api_key: str, agent_id: str):
    """Returns (signed_url, error) where error is (status, detail) or None."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://api.elevenlabs.io/v1/convai/conversation/get_signed_url?agent_id={agent_id}",
            headers={"xi-api-key": api_key},
            timeout=30.0,
        )
    print(f"VOICE: ElevenLabs response status: {resp.status_code}")
    if resp.status_code != 200:
        print(f"VOICE: ElevenLabs error body: {resp.text}")
        return None, (resp.status_code, resp.text)
    data = resp.json()
    signed_url = data.get("signed_url")
    print(f"VOICE: signed_url present: {bool(signed_url)}")
    if signed_url:
        print(f"VOICE: signed_url length: {len(signed_url)}, preview: {signed_url[:80]}")
    return signed_url, None


# ─── Transcript save ──────────────────────────────────────────────────────────

class TranscriptMessage(BaseModel):
    role: str
    content: str


class TranscriptRequest(BaseModel):
    user_id: str
    messages: list[TranscriptMessage]


@router.post("/voice/save-transcript")
async def save_voice_transcript(request: TranscriptRequest):
    for msg in request.messages:
        await save_conversation_turn(request.user_id, msg.role, msg.content)

    user_msg = None
    for msg in request.messages:
        if msg.role == "user":
            user_msg = msg.content
        elif msg.role == "assistant" and user_msg:
            await save_interaction(request.user_id, user_msg, msg.content)
            await update_user_model(request.user_id, user_msg, msg.content)
            user_msg = None

    return {"status": "saved", "count": len(request.messages)}


# ─── ElevenLabs server-side tool webhooks ─────────────────────────────────────

class VoiceToolRequest(BaseModel):
    session_token: str


class VoiceCalendarCreateRequest(BaseModel):
    session_token: str
    title: str
    start_time: str
    end_time: str = None
    description: str = ""


class VoiceEmailRequest(BaseModel):
    session_token: str
    max_results: int = 5
    query: str = ""


class VoiceSendEmailRequest(BaseModel):
    session_token: str
    to: str
    subject: str
    body: str


class VoiceWebSearchRequest(BaseModel):
    query: str


class VoiceTimerRequest(BaseModel):
    session_token: str
    duration_seconds: int
    label: str = "Timer"


class VoiceMemorySearchRequest(BaseModel):
    session_token: str
    query: str


@router.post("/voice/tool/calendar")
async def voice_tool_calendar(request: VoiceToolRequest):
    user_id = get_user_from_session(request.session_token)
    if not user_id:
        return {"result": "Session expired. Please restart voice."}
    try:
        result = await get_calendar_events(user_id=user_id, max_results=5)
        return {"result": result}
    except Exception as e:
        return {"result": f"Could not fetch calendar: {str(e)}"}


@router.post("/voice/tool/calendar/create")
async def voice_tool_calendar_create(request: VoiceCalendarCreateRequest):
    user_id = get_user_from_session(request.session_token)
    if not user_id:
        return {"result": "Session expired. Please restart voice."}
    try:
        result = await create_calendar_event(
            user_id=user_id,
            title=request.title,
            start_time=request.start_time,
            end_time=request.end_time,
            description=request.description,
        )
        return {"result": result}
    except Exception as e:
        return {"result": f"Could not create event: {str(e)}"}


@router.post("/voice/tool/email")
async def voice_tool_email(request: VoiceEmailRequest):
    user_id = get_user_from_session(request.session_token)
    if not user_id:
        return {"result": "Session expired. Please restart voice."}
    try:
        result = await get_emails(
            user_id=user_id,
            max_results=request.max_results,
            query=request.query,
        )
        return {"result": result}
    except Exception as e:
        return {"result": f"Could not fetch emails: {str(e)}"}


@router.post("/voice/tool/email/send")
async def voice_tool_email_send(request: VoiceSendEmailRequest):
    user_id = get_user_from_session(request.session_token)
    if not user_id:
        return {"result": "Session expired. Please restart voice."}
    try:
        result = await send_email(
            user_id=user_id,
            to=request.to,
            subject=request.subject,
            body=request.body,
        )
        return {"result": result}
    except Exception as e:
        return {"result": f"Could not send email: {str(e)}"}


@router.post("/voice/tool/search")
async def voice_tool_search(request: VoiceWebSearchRequest):
    try:
        result = await web_search(query=request.query)
        return {"result": result}
    except Exception as e:
        return {"result": f"Search failed: {str(e)}"}


@router.post("/voice/tool/memory-search")
async def voice_tool_memory_search(request: VoiceMemorySearchRequest):
    user_id = get_user_from_session(request.session_token)
    if not user_id:
        return {"result": "Session expired. Please restart voice."}
    try:
        memories = await get_relevant_memories(user_id, request.query)

        conv_results = ""
        supabase_url = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
        supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        if supabase_url and supabase_key:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{supabase_url}/rest/v1/conversations",
                    headers={
                        "apikey": supabase_key,
                        "Authorization": f"Bearer {supabase_key}",
                    },
                    params={
                        "user_id": f"eq.{user_id}",
                        "order": "created_at.desc",
                        "limit": 200,
                        "select": "role,content,created_at",
                    },
                    timeout=10.0,
                )
            if resp.status_code == 200:
                rows = resp.json()
                query_words = request.query.lower().split()
                matching = [
                    r for r in rows
                    if any(word in r["content"].lower() for word in query_words)
                ][:5]
                if matching:
                    conv_results = "\n".join(
                        f"{r['role'].upper()}: {r['content'][:300]}" for r in matching
                    )

        parts = []
        if memories:
            parts.append(f"What I remember: {memories}")
        if conv_results:
            parts.append(f"Found in past conversations: {conv_results}")

        if parts:
            return {"result": "\n\n".join(parts)}
        return {"result": f"Nothing found about '{request.query}' in memory."}

    except Exception as e:
        return {"result": f"Memory search failed: {str(e)}"}


@router.post("/voice/tool/timer")
async def voice_tool_timer(request: VoiceTimerRequest):
    user_id = get_user_from_session(request.session_token)
    if not user_id:
        return {"result": "Session expired. Please restart voice."}
    try:
        from backend.tools.timer_tool import set_timer
        result = await set_timer(
            duration_seconds=request.duration_seconds,
            user_id=user_id,
            label=request.label,
        )
        return {"result": result}
    except Exception as e:
        return {"result": f"Could not set timer: {str(e)}"}
