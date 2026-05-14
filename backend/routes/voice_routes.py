import os
from datetime import datetime

import httpx
import pytz
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.memory import get_relevant_memories
from backend.user_model import summarize_user_for_prompt

router = APIRouter()


class VoiceSessionRequest(BaseModel):
    user_id: str


@router.post("/voice/session")
async def get_voice_session(request: VoiceSessionRequest):
    api_key = os.getenv("ELEVENLABS_API_KEY")
    agent_id = os.getenv("ELEVENLABS_AGENT_ID")
    if not api_key or not agent_id:
        raise HTTPException(status_code=503, detail="ElevenLabs credentials not configured")

    memory_context = await get_relevant_memories(
        request.user_id, "general context and who the user is"
    )
    user_model_summary = await summarize_user_for_prompt(request.user_id)

    eastern = pytz.timezone("America/Toronto")
    current_dt = datetime.now(eastern).strftime(
        "Today is %A, %B %d, %Y. Current time is %I:%M %p EST."
    )

    system_prompt = f"""ABSOLUTE RULES — NEVER BREAK THESE:
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

VOICE MODE:
You are speaking, not typing. Be conversational.
Short sentences. Natural pauses. Real presence.
You are always listening. Respond immediately when the user finishes speaking."""

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://api.elevenlabs.io/v1/convai/conversation/get_signed_url?agent_id={agent_id}",
            headers={"xi-api-key": api_key},
            timeout=30.0,
        )

    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)

    data = resp.json()
    signed_url = data.get("signed_url")
    if not signed_url:
        raise HTTPException(status_code=502, detail="No signed_url in ElevenLabs response")

    return {
        "signed_url": signed_url,
        "system_prompt": system_prompt,
    }
