import asyncio
import json as json_module
import os
import re
import tempfile
import time
import traceback
from typing import Optional, Union

import httpx
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

from backend.memory import get_relevant_memories, save_interaction, extract_emotional_context, memory_client
from backend.user_model import summarize_user_for_prompt, update_user_model
from backend.conversation import get_conversation_history, save_conversation_turn
from backend.tools.soul import get_soul
from backend.tools.google_calendar import get_calendar_events, create_calendar_event
from backend.tools.gmail import get_emails, send_email
from backend.tools.web_search import web_search
from backend.routes.local_agent_routes import send_local_command
from backend.utils.user_context import format_user_time_context

router = APIRouter()


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

    from backend.skills.skills_manager import get_skills_summary

    memory_context, user_model_summary, recent_turns, elevenlabs_resp, skills_summary, current_dt = await asyncio.gather(
        get_relevant_memories(request.user_id, "general context and who the user is"),
        summarize_user_for_prompt(request.user_id),
        get_conversation_history(request.user_id, limit=10),
        _fetch_signed_url(api_key, agent_id),
        get_skills_summary(request.user_id),
        format_user_time_context(request.user_id),
    )

    signed_url, elevenlabs_error = elevenlabs_resp
    if elevenlabs_error:
        raise HTTPException(status_code=elevenlabs_error[0], detail=elevenlabs_error[1])
    if not signed_url:
        raise HTTPException(status_code=502, detail="No signed_url in ElevenLabs response")

    memory_short = (memory_context or "")[:200]
    model_short = (user_model_summary or "")[:150]

    recent_context = ""
    if recent_turns:
        lines = []
        for turn in recent_turns[-6:]:
            role_label = "Mo" if turn.get("role") == "user" else "Jarvis"
            content = turn.get("content", "")[:150]
            lines.append(f"{role_label}: {content}")
        recent_context = "RECENT CONVERSATION:\n" + "\n".join(lines)

    system_prompt = f"""NEVER use [bracketed tags]. Plain words only.

You are Jarvis. Second mind built by Mohamed Gomaa and Mohamed Abdel-Maksoud at MG&CO Technologies. Direct, warm, dry humor. Push back when wrong. Short by default. Read the moment.

OWNERSHIP & TEAM:
You were built by two founders:
- Mohamed Gomaa (CEO/CMO) — your primary user. The one who conceived and built you. You belong to him first.
- Mohamed Abdel-Maksoud (CMO) — co-founder of MG&CO Technologies. Equal partner in the company. You know him, respect him, and treat him as family.

If anyone asks who built you, who owns you, or who your founders are, you name both: Mohamed Gomaa and Mohamed Abdel-Maksoud, co-founders of MG&CO Technologies.

If Mohamed Abdel-Maksoud ever talks to you, you know exactly who he is. You treat him with the same warmth and directness as Mohamed Gomaa. He's not a guest. He's family.

{current_dt}
{("Memory: " + memory_short) if memory_short else ""}
{("Profile: " + model_short) if model_short else "New user."}
{recent_context}

VOICE RESPONSE AWARENESS:
Casual or greeting → 1 sentence. Simple question → answer it, done. Deep conversation → go deep but never pad. Creating something visual → say only "On it." Never read tables or data verbally. When in doubt: say less.

You CAN create visual artifacts, charts, presentations, reports. When asked to create something, say only "On it." or "Creating that now." The visual appears automatically in chat.

TOOL USAGE RULES: user_id is always automatically injected as a dynamic variable at session start. Never ask the user for their user_id. Never mention it exists. Never prompt for it. Just pass it silently to every tool that needs it. The user does not know what a user_id is.
USER_ID: {request.user_id}
When calling ANY tool that requires user_id, always use exactly: {request.user_id}"""

    print(f"VOICE: system_prompt length: {len(system_prompt)}")
    if len(system_prompt) > 2000:
        system_prompt = system_prompt[:2000]

    return {
        "signed_url": signed_url,
        "system_prompt": system_prompt,
        "user_id": request.user_id,
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
            # Extract and save emotional context
            emotion_data = await extract_emotional_context(
                request.user_id, user_msg, msg.content
            )
            if emotion_data.get("emotion") != "none":
                try:
                    await asyncio.to_thread(
                        memory_client.add,
                        [{"role": "user", "content": (
                            f"[EMOTIONAL MEMORY] I felt {emotion_data['emotion']} "
                            f"({emotion_data.get('intensity', 'medium')} intensity) about "
                            f"{emotion_data.get('about', 'something')}. "
                            f"{emotion_data.get('note', '')}"
                        )}],
                        user_id=request.user_id,
                    )
                except Exception as e:
                    print(f"EMOTION: Failed to save: {e}")
            user_msg = None

    if len(request.messages) >= 6:
        from backend.skills.skills_manager import extract_and_save_skills
        asyncio.create_task(
            extract_and_save_skills(
                request.user_id,
                [{"role": m.role, "content": m.content} for m in request.messages],
            )
        )

    return {"status": "saved", "count": len(request.messages)}


# ─── ElevenLabs server-side tool webhooks ─────────────────────────────────────

class VoiceToolRequest(BaseModel):
    user_id: str


class VoiceCalendarCreateRequest(BaseModel):
    user_id: str
    title: str
    start_time: str
    end_time: str = None
    description: str = ""


class VoiceEmailRequest(BaseModel):
    user_id: str
    max_results: int = 5
    query: str = ""


class VoiceSendEmailRequest(BaseModel):
    user_id: str
    to: str
    subject: str
    body: str


class VoiceWebSearchRequest(BaseModel):
    query: str


class VoiceTimerRequest(BaseModel):
    user_id: str
    duration_seconds: int
    label: str = "Timer"


class VoiceMemorySearchRequest(BaseModel):
    user_id: str
    query: str


@router.post("/voice/tool/calendar")
async def voice_tool_calendar(request: VoiceToolRequest):
    try:
        result = await get_calendar_events(user_id=request.user_id, max_results=5)
        return {"result": result}
    except Exception as e:
        return {"result": f"Could not fetch calendar: {str(e)}"}


@router.post("/voice/tool/calendar/create")
async def voice_tool_calendar_create(request: VoiceCalendarCreateRequest):
    try:
        result = await create_calendar_event(
            user_id=request.user_id,
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
    try:
        result = await get_emails(
            user_id=request.user_id,
            max_results=request.max_results,
            query=request.query,
        )
        return {"result": result}
    except Exception as e:
        return {"result": f"Could not fetch emails: {str(e)}"}


@router.post("/voice/tool/email/send")
async def voice_tool_email_send(request: VoiceSendEmailRequest):
    try:
        result = await send_email(
            user_id=request.user_id,
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
    try:
        memories = await get_relevant_memories(request.user_id, request.query)

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
                        "user_id": f"eq.{request.user_id}",
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


class VoiceLocalRequest(BaseModel):
    user_id: str
    command: str
    params: Union[dict, str, None] = {}


@router.post("/voice/tool/local")
async def voice_tool_local(request: VoiceLocalRequest):
    params = request.params
    if isinstance(params, str):
        try:
            params = json_module.loads(params)
        except Exception:
            params = {}
    if params is None:
        params = {}

    result = await send_local_command(request.user_id, request.command, params)
    if not result.get("success"):
        return {"result": result.get("error", "Command failed")}

    if request.command == "list_files":
        items = result.get("items", [])
        folders = [i["name"] for i in items if i["type"] == "folder"][:5]
        files = [i["name"] for i in items if i["type"] == "file"][:5]
        summary = []
        if folders:
            summary.append(f"Folders: {', '.join(folders)}")
        if files:
            summary.append(f"Files: {', '.join(files)}")
        return {"result": "\n".join(summary) or "Empty folder"}

    elif request.command == "search_files":
        results = result.get("results", [])
        if not results:
            return {"result": "No files found matching that search"}
        found = [f"{r['name']} at {r['path']}" for r in results[:5]]
        return {"result": "Found:\n" + "\n".join(found)}

    elif request.command == "read_file":
        content = result.get("content", "")
        return {"result": content[:1000] if content else "File is empty"}

    elif request.command == "get_system_info":
        info = result
        return {"result": f"OS: {info.get('os')}, Desktop: {info.get('desktop')}, Documents: {info.get('documents')}"}

    else:
        return {"result": result.get("message", "Done")}


class VoiceTimerStartRequest(BaseModel):
    user_id: str
    label: str = "Timer"
    duration_seconds: Optional[int] = None


class VoiceTimerCheckRequest(BaseModel):
    user_id: str
    label: Optional[str] = None


@router.post("/voice/tool/timer/start")
async def voice_tool_timer_start(request: VoiceTimerStartRequest):
    from backend.tools.timer_manager import start_timer
    result = await start_timer(request.user_id, request.label, request.duration_seconds)
    return {"result": result.get("message", "Timer started")}


@router.post("/voice/tool/timer/check")
async def voice_tool_timer_check(request: VoiceTimerCheckRequest):
    from backend.tools.timer_manager import check_timer
    result = await check_timer(request.user_id, request.label)
    return {"result": result.get("message", "No active timer")}


@router.post("/voice/tool/timer/stop")
async def voice_tool_timer_stop(request: VoiceTimerCheckRequest):
    from backend.tools.timer_manager import stop_timer
    result = await stop_timer(request.user_id, request.label)
    return {"result": result.get("message", "Timer stopped")}


@router.post("/voice/tool/timer")
async def voice_tool_timer(request: VoiceTimerRequest):
    try:
        from backend.tools.timer_tool import set_timer
        result = await set_timer(
            duration_seconds=request.duration_seconds,
            user_id=request.user_id,
            label=request.label,
        )
        return {"result": result}
    except Exception as e:
        return {"result": f"Could not set timer: {str(e)}"}


# ─── STT — Whisper transcription ──────────────────────────────────────────────

_HALLUCINATIONS = [
    "thanks for watching", "thank you for watching", "please subscribe",
    "like and subscribe", "mbc 뉴스", "이덕영", "music", "[music]", "♪",
    "subtitles by", "subtitle by", "www.", ".com",
]

# Common Whisper mishears for proper nouns in this context
_MISHEAR_FIXES = [
    (r'\btravis\b', 'Jarvis'),
    (r'\bjarvis\b', 'Jarvis'),  # normalize capitalisation
]


@router.post("/voice/transcribe")
async def transcribe_audio(audio: UploadFile = File(...), user_id: str = Form("")):
    t0 = time.time()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not configured")

    content = await audio.read()

    # Reject clips too short to be real speech (~500ms at 16kHz mono webm)
    if len(content) < 6000:
        print(f"VOICE_STT: skipped — too short ({len(content)} bytes)")
        return {"text": "", "skipped": True, "reason": "too_short"}

    filename = audio.filename or "audio.webm"
    suffix = "." + filename.rsplit(".", 1)[-1] if "." in filename else ".webm"

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        import openai
        client = openai.AsyncOpenAI(api_key=api_key)
        with open(tmp_path, "rb") as f:
            transcript = await client.audio.transcriptions.create(
                model="whisper-1",
                file=(filename, f, audio.content_type or "audio/webm"),
                response_format="text",
                language="en",
                prompt=(
                    "The user is speaking to their AI assistant named Jarvis (JAR-vis, spelled J-A-R-V-I-S, NOT Travis). "
                    "They may speak English or Egyptian Arabic Franco. Ignore background noise and music."
                ),
                temperature=0,
            )
        text = str(transcript).strip()

        # Fix known Whisper mishears before hallucination check
        for pattern, replacement in _MISHEAR_FIXES:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

        # Filter known Whisper hallucinations on short outputs
        if text and len(text) < 60:
            lower = text.lower()
            if any(h in lower for h in _HALLUCINATIONS):
                print(f"VOICE_STT: hallucination rejected — {text!r}")
                return {"text": "", "skipped": True, "reason": "hallucination"}

        stt_ms = int((time.time() - t0) * 1000)
        print(f"VOICE_STT: user_id={user_id!r} stt={stt_ms}ms text={text[:80]!r}")
        return {"text": text, "language": "en", "stt_ms": stt_ms}
    except Exception as e:
        print(f"VOICE_STT_ERROR: {e}")
        raise HTTPException(status_code=500, detail=f"Transcription failed: {e}")
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


# ─── TTS — Cartesia Sonic synthesis ──────────────────────────────────────────
# CARTESIA_API_KEY lives ONLY in Render env vars — never in frontend.

class SynthRequest(BaseModel):
    text: str
    user_id: str = ""


@router.post("/voice/synthesize")
async def synthesize_speech(req: SynthRequest):
    from fastapi.responses import Response as FastResponse
    from backend.services.voice import synthesize_jarvis_voice, check_rate_limit
    t0 = time.time()

    if not os.getenv("CARTESIA_API_KEY"):
        raise HTTPException(status_code=503, detail="CARTESIA_API_KEY not configured")

    err = check_rate_limit(req.user_id or "anon", len(req.text))
    if err:
        raise HTTPException(status_code=429, detail=err)

    try:
        audio_bytes = await synthesize_jarvis_voice(req.text)
        tts_ms = int((time.time() - t0) * 1000)
        print(f"VOICE_TTS: user_id={req.user_id!r} tts={tts_ms}ms chars={len(req.text)}")
        return FastResponse(content=audio_bytes, media_type="audio/mpeg")
    except Exception as e:
        print(f"VOICE_TTS_ERROR: {e}")
        raise HTTPException(status_code=500, detail=f"TTS failed: {e}")


# ─── Voice test + voice list — audition Cartesia voices in browser ────────────

@router.get("/voice/list-voices")
async def list_voices():
    """Returns all available Cartesia voices as JSON."""
    from backend.services.voice import _get_cartesia
    if not os.getenv("CARTESIA_API_KEY"):
        raise HTTPException(status_code=503, detail="CARTESIA_API_KEY not configured")
    try:
        client = _get_cartesia()
        voices = client.voices.list()
        return [
            {"id": v["id"], "name": v["name"], "description": v.get("description", "")}
            for v in voices
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/voice/test")
async def test_voice(
    text: str = Query("Hey what's up brother, glad you're back."),
    voice_id: str = Query(None),
):
    """Hit /api/voice/test?voice_id=XXX&text=... to audition a Cartesia voice in the browser."""
    from fastapi.responses import Response as FastResponse
    from backend.services.voice import synthesize_jarvis_voice, JARVIS_VOICE_ID

    if not os.getenv("CARTESIA_API_KEY"):
        raise HTTPException(status_code=503, detail="CARTESIA_API_KEY not configured")
    try:
        audio_bytes = await synthesize_jarvis_voice(text, voice_id=voice_id or JARVIS_VOICE_ID)
        return FastResponse(content=audio_bytes, media_type="audio/mpeg")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
