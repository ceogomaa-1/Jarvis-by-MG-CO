import asyncio
import json
import os
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from supabase import create_client

from backend.lib.business.system_prompt_builder import build_system_prompt
from backend.lib.business.model_router import select_model, OPUS
from backend.lib.business.memory import extract_and_store_memories

router = APIRouter()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
SUPABASE_URL = os.getenv("NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")


def _get_supabase():
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def _user_id_to_uuid(user_id: str) -> str:
    hex_id = user_id.removeprefix("user_")
    if len(hex_id) == 32 and all(c in "0123456789abcdef" for c in hex_id.lower()):
        return f"{hex_id[:8]}-{hex_id[8:12]}-{hex_id[12:16]}-{hex_id[16:20]}-{hex_id[20:]}"
    return user_id


def _setup_conversation(sb, user_id: str, conv_id: str | None, message: str) -> tuple[str | None, bool]:
    """
    Create conversation if conv_id is None, then save user message.
    Returns (conv_id, is_new_conversation).
    """
    is_new = not conv_id
    user_uuid = _user_id_to_uuid(user_id)

    if not conv_id:
        res = sb.table("business_conversations").insert({
            "user_id": user_uuid,
            "title": "New conversation",
        }).execute()
        conv_id = res.data[0]["id"] if res.data else None

    if conv_id:
        sb.table("business_messages").insert({
            "conversation_id": conv_id,
            "role": "user",
            "content": message,
        }).execute()

    return conv_id, is_new


def _save_assistant_message(sb, conv_id: str, content: str) -> None:
    sb.table("business_messages").insert({
        "conversation_id": conv_id,
        "role": "assistant",
        "content": content,
    }).execute()
    sb.table("business_conversations").update({
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", conv_id).execute()


def _update_title(sb, conv_id: str, title: str) -> None:
    sb.table("business_conversations").update({
        "title": title,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", conv_id).execute()


async def _auto_title(sb, conv_id: str, first_user_message: str) -> None:
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
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 20,
                    "messages": [
                        {"role": "user", "content": (
                            f"Generate a short 3-6 word title for a conversation that starts with: "
                            f"'{first_user_message[:200]}'. "
                            "Return ONLY the title, no quotes, no explanation."
                        )}
                    ],
                },
                timeout=30.0,
            )
        if resp.status_code == 200:
            title = resp.json().get("content", [{}])[0].get("text", "").strip()
            if title:
                await asyncio.to_thread(_update_title, sb, conv_id, title)
    except Exception as e:
        print(f"Auto-title error: {e}")


class BusinessChatRequest(BaseModel):
    message: str
    user_id: str = ""
    conversation_history: list = []
    conversation_id: str | None = None


@router.post("/business/chat/stream")
async def business_chat_stream(request: BusinessChatRequest):
    system_prompt = await build_system_prompt(request.user_id, request.message)

    safe_history = [
        {"role": m.get("role", "user"), "content": str(m.get("content", ""))}
        for m in (request.conversation_history or [])
        if isinstance(m.get("content"), str) and m["content"].strip()
        and m.get("role") in ("user", "assistant")
    ]
    messages = safe_history + [{"role": "user", "content": request.message}]

    model = select_model(request.message)
    max_tokens = 4096 if model == OPUS else 2048

    # Set up conversation and save user message before streaming
    sb = _get_supabase() if request.user_id else None
    conv_id = request.conversation_id
    is_new_conv = False

    if sb and request.user_id:
        try:
            conv_id, is_new_conv = await asyncio.to_thread(
                _setup_conversation, sb, request.user_id, conv_id, request.message
            )
        except Exception as e:
            print(f"Pre-stream DB setup error: {e}")
            conv_id = request.conversation_id  # Fall back to original

    async def generate():
        # Emit conversation ID first so frontend can associate messages
        if conv_id:
            yield f'data: {json.dumps({"type": "conv_id", "value": conv_id})}\n\n'

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

            # Post-stream: persist assistant message + fire background tasks
            if sb and conv_id and text:
                try:
                    await asyncio.to_thread(_save_assistant_message, sb, conv_id, text)

                    if is_new_conv:
                        asyncio.create_task(_auto_title(sb, conv_id, request.message))

                    asyncio.create_task(
                        extract_and_store_memories(
                            request.user_id, conv_id, request.message, text, sb
                        )
                    )
                except Exception as e:
                    print(f"Post-stream persistence error: {e}")

        except Exception as e:
            print(f"BUSINESS CHAT: Error: {e}")
            yield f'data: {json.dumps("Something went wrong. Please try again.")}\n\n'
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
