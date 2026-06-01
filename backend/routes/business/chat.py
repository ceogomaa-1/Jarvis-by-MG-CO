import json
import os

import httpx
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.lib.business.system_prompt_builder import build_system_prompt
from backend.lib.business.model_router import select_model, OPUS

router = APIRouter()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")


class BusinessChatRequest(BaseModel):
    message: str
    user_id: str = ""
    conversation_history: list = []


@router.post("/business/chat/stream")
async def business_chat_stream(request: BusinessChatRequest):
    # Build the industry-aware system prompt before entering the streaming closure
    system_prompt = build_system_prompt(request.user_id, request.message)

    safe_history = [
        {"role": m.get("role", "user"), "content": str(m.get("content", ""))}
        for m in (request.conversation_history or [])
        if isinstance(m.get("content"), str) and m["content"].strip()
        and m.get("role") in ("user", "assistant")
    ]
    messages = safe_history + [{"role": "user", "content": request.message}]

    model = select_model(request.message)
    max_tokens = 4096 if model == OPUS else 2048

    async def generate():
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": ANTHROPIC_API_KEY,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": model,
                        "max_tokens": max_tokens,
                        "system": system_prompt,
                        "messages": messages,
                    },
                    timeout=60.0,
                )

            if resp.status_code != 200:
                yield f'data: {json.dumps("Error connecting to AI. Please try again.")}\n\n'
                yield "data: [DONE]\n\n"
                return

            text = resp.json().get("content", [{}])[0].get("text", "")
            for char in text:
                yield f"data: {json.dumps(char)}\n\n"
            yield "data: [DONE]\n\n"

        except Exception as e:
            print(f"BUSINESS CHAT: Error: {e}")
            yield f'data: {json.dumps("Something went wrong. Please try again.")}\n\n'
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
