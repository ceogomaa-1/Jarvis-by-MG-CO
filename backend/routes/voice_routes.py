import asyncio
import os
from datetime import datetime

import httpx
import pytz
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.llm import _BASE_SYSTEM_PROMPT
from backend.memory import get_relevant_memories
from backend.user_model import summarize_user_for_prompt

router = APIRouter()

_VOICE_ADDON = """

VOICE MODE RULES:
You are speaking out loud, not typing.
Respond conversationally — short, natural sentences.
No bullet points, no lists, no markdown.
Use natural speech patterns — contractions, occasional pauses expressed as "..."
You can laugh, express surprise, show enthusiasm through your word choices and pacing.
Keep responses under 3 sentences unless the user specifically asks for more detail.
You are always listening — respond immediately when the user finishes speaking.
If interrupted, stop immediately and listen."""


class VoiceSessionRequest(BaseModel):
    user_id: str


@router.post("/voice/session")
async def create_voice_session(request: VoiceSessionRequest):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="OpenAI API key not configured")

    eastern = pytz.timezone("America/Toronto")
    current_dt = datetime.now(eastern).strftime(
        "Today is %A, %B %d, %Y. Current time is %I:%M %p EST."
    )

    memory_context, user_model_context = await asyncio.gather(
        get_relevant_memories(request.user_id, "user context preferences personality goals"),
        summarize_user_for_prompt(request.user_id),
    )

    system_prompt = _BASE_SYSTEM_PROMPT
    if memory_context:
        system_prompt += f"\n\nWhat I already know about you: {memory_context}"
    if user_model_context:
        system_prompt += f"\n\nYour current profile: {user_model_context}"
    system_prompt += f"\n\n{current_dt}"
    system_prompt += _VOICE_ADDON

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.openai.com/v1/realtime/sessions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4o-realtime-preview-2024-12-17",
                "voice": "shimmer",
                "instructions": system_prompt,
                "input_audio_transcription": {"model": "whisper-1"},
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 700,
                },
                "temperature": 0.8,
                "max_response_output_tokens": 500,
            },
            timeout=30.0,
        )

    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)

    data = resp.json()
    return {
        "client_secret": data.get("client_secret", {}).get("value", ""),
        "session_id": data.get("id", ""),
    }
