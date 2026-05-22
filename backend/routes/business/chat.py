import json
import os

import httpx
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

_SYSTEM = """You are Jarvis for Business — a professional AI built by MG&CO Technologies.

You help business users with:
- Process documentation and SOPs
- Software tutorials and walkthroughs
- Business workflows and best practices
- Data analysis and reporting guidance
- Team productivity

Be direct, professional, and practical. Give concrete, actionable answers.

FORMATTING: Use clean markdown — ## headers, bullet points, **bold** for key terms.
Structure information clearly. Short paragraphs.

When a user asks "show me how to...", "how do I...", or similar —
respond with a brief 1-2 sentence confirmation that you're creating a walkthrough.
Keep it natural. The walkthrough renders automatically in the interface."""


class BusinessChatRequest(BaseModel):
    message: str
    user_id: str = ""
    conversation_history: list = []


@router.post("/business/chat/stream")
async def business_chat_stream(request: BusinessChatRequest):
    safe_history = [
        {"role": m.get("role", "user"), "content": str(m.get("content", ""))}
        for m in (request.conversation_history or [])
        if isinstance(m.get("content"), str) and m["content"].strip()
        and m.get("role") in ("user", "assistant")
    ]
    messages = safe_history + [{"role": "user", "content": request.message}]

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
                        "model": "claude-sonnet-4-20250514",
                        "max_tokens": 2048,
                        "system": _SYSTEM,
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
