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
from backend.lib.business.farida_loader import FARIDA_USER_ID, load_greeting as _load_farida_greeting
from backend.lib.business.model_router import select_model, OPUS
from backend.lib.business.memory import extract_and_store_memories
from backend.lib.business.tool_builder import build_tools_for_user
from backend.lib.business.tool_executor import execute_tool
from backend.usage_limits import check_limit, increment_usage, get_usage

router = APIRouter()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
SUPABASE_URL = os.getenv("NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

MAX_TOOL_ROUNDS = 5  # Safety limit on tool-use iterations per request

# Write actions that require user confirmation before execution.
# When Claude generates tool_use for any of these, the backend intercepts it,
# emits a pending_action SSE event, and waits for explicit hold-to-confirm.
WRITE_ACTIONS = frozenset({
    "google__send_email",
    "google__create_calendar_event",
    "google__update_calendar_event",
    "google__delete_calendar_event",
    "twilio__send_sms",
    "smtp__send_email",
    "notion__create_page",
    "notion__create_database",
    "elevenlabs__create_agent",
    "elevenlabs__update_agent",
    "elevenlabs__delete_agent",
    "gohighlevel__create_contact",
    "buffer__create_post",
    "buffer__schedule_post",
    "buffer__add_to_queue",
})


def _describe_action(tool_name: str, tool_input: dict) -> str:
    """Human-readable label for a pending write action."""
    if "send_email" in tool_name:
        return f"Send email to {tool_input.get('to', '?')}"
    if "create_calendar_event" in tool_name:
        event = tool_input.get("event_body", {})
        return f"Create event: {event.get('summary', '?')}"
    if "update_calendar_event" in tool_name:
        return f"Update event: {tool_input.get('event_id', '?')}"
    if "delete_calendar_event" in tool_name:
        return f"Delete event: {tool_input.get('event_id', '?')}"
    if "send_sms" in tool_name:
        return f"Send SMS to {tool_input.get('to', '?')}"
    if "create_page" in tool_name:
        return "Create Notion page"
    if "create_database" in tool_name:
        return f"Create Notion database: {tool_input.get('title', '?')}"
    if "create_agent" in tool_name:
        return f"Create agent: {tool_input.get('name', '?')}"
    if "update_agent" in tool_name:
        return f"Update agent: {tool_input.get('agent_id', '?')}"
    if "delete_agent" in tool_name:
        return f"Delete agent: {tool_input.get('agent_id', '?')}"
    if "create_contact" in tool_name:
        first = tool_input.get("firstName", "")
        last = tool_input.get("lastName", "")
        return f"Create contact: {(first + ' ' + last).strip() or '?'}"
    if tool_name in {"buffer__create_post", "buffer__schedule_post", "buffer__add_to_queue"}:
        channels = ", ".join(tool_input.get("channel_ids", []) or [])
        publish_at = tool_input.get("publish_at") or "next queue slot"
        text = (tool_input.get("text") or "")[:80]
        action = "Schedule" if tool_name == "buffer__schedule_post" else "Queue" if tool_name == "buffer__add_to_queue" else "Create"
        return f"{action} Buffer post to {channels or '?'} at {publish_at}: {text or '?'}"
    return tool_name.replace("__", " → ").replace("_", " ").title()


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


class AttachmentItem(BaseModel):
    type: str = "image"          # "image" | "document" | "text_file"
    media_type: str = "image/jpeg"
    data: str                    # base64-encoded
    name: str = ""               # original filename (for text_file fallback label)


class BusinessChatRequest(BaseModel):
    message: str
    user_id: str = ""
    conversation_history: list = []
    conversation_id: str | None = None
    attachments: list[AttachmentItem] = []


def _build_user_content(text: str, attachments: list[AttachmentItem]) -> list | str:
    """Build Anthropic content block(s) for a user turn, including images/PDFs/text."""
    if not attachments:
        return text
    import base64
    blocks: list = []
    for att in attachments[:5]:  # enforce max 5 server-side
        if att.type == "image" or att.media_type.startswith("image/"):
            blocks.append({
                "type": "image",
                "source": {"type": "base64", "media_type": att.media_type, "data": att.data},
            })
        elif att.media_type == "application/pdf" or att.type == "document":
            blocks.append({
                "type": "document",
                "source": {"type": "base64", "media_type": "application/pdf", "data": att.data},
            })
        else:
            # Text/CSV/plain — decode and inject as labelled text block
            try:
                decoded = base64.b64decode(att.data).decode("utf-8", errors="replace")
                label = att.name or "file"
                blocks.append({"type": "text", "text": f"[File: {label}]\n{decoded[:8000]}"})
            except Exception:
                pass
    blocks.append({"type": "text", "text": text})
    return blocks


@router.get("/business/usage")
async def get_user_usage(user_id: str = ""):
    """Return today's usage info for the given user."""
    if not user_id:
        return {"error": "user_id required"}
    sb = _get_supabase()
    if not sb:
        return {"used": 0, "limit": 32, "remaining": 32, "is_admin": False, "resets_in": "", "window_minutes": 90}
    usage = await asyncio.to_thread(get_usage, user_id, sb)
    return usage


@router.post("/business/chat/stream")
async def business_chat_stream(request: BusinessChatRequest):
    system_prompt = await build_system_prompt(request.user_id, request.message)
    tools = await build_tools_for_user(request.user_id)

    safe_history = [
        {"role": m.get("role", "user"), "content": str(m.get("content", ""))}
        for m in (request.conversation_history or [])
        if isinstance(m.get("content"), str) and m["content"].strip()
        and m.get("role") in ("user", "assistant")
    ]
    user_content = _build_user_content(request.message, request.attachments)
    messages = safe_history + [{"role": "user", "content": user_content}]

    model = select_model(request.message)
    # 8192 for both Sonnet and Opus: enough headroom for tool call JSON without truncation.
    # 2048 was too small for Sonnet — a mid-tool-call max_tokens hit caused silent tool drops.
    max_tokens = 8192

    sb = _get_supabase() if request.user_id else None
    conv_id = request.conversation_id
    is_new_conv = False

    # Check usage limit before creating conversation or calling Anthropic
    limit_exceeded = False
    limit_usage_info: dict = {}
    if sb and request.user_id:
        allowed, limit_usage_info = await asyncio.to_thread(check_limit, request.user_id, sb)
        if not allowed:
            limit_exceeded = True

    # Detect Farida's first-ever conversation BEFORE setup creates the first row.
    farida_greeting = ""
    if not limit_exceeded and sb and request.user_id:
        if _user_id_to_uuid(request.user_id) == FARIDA_USER_ID and not conv_id:
            try:
                _check = await asyncio.to_thread(
                    lambda: sb.table("business_conversations")
                    .select("id")
                    .eq("user_id", FARIDA_USER_ID)
                    .limit(1)
                    .execute()
                )
                if not _check.data:
                    farida_greeting = _load_farida_greeting()
            except Exception:
                pass

    if not limit_exceeded and sb and request.user_id:
        try:
            conv_id, is_new_conv = await asyncio.to_thread(
                _setup_conversation, sb, request.user_id, conv_id, request.message
            )
        except Exception as e:
            print(f"Pre-stream DB setup error: {e}")
            conv_id = request.conversation_id

    async def generate():
        # Limit check — yield friendly message and bail
        if limit_exceeded:
            limit = limit_usage_info.get("limit", 32)
            window = limit_usage_info.get("window_minutes", 90)
            resets = limit_usage_info.get("resets_in", "soon")
            msg = (
                f"You've hit your limit for now — {limit} messages per {window} minutes. "
                f"Your next slot opens in {resets}. Jarvis will be here."
            )
            yield f"data: {json.dumps(msg)}\n\n"
            yield f'data: {json.dumps({"type": "usage", "data": limit_usage_info})}\n\n'
            yield "data: [DONE]\n\n"
            return

        # Emit conversation ID first so frontend can associate messages
        if conv_id:
            yield f'data: {json.dumps({"type": "conv_id", "value": conv_id})}\n\n'

        # Farida's first-conversation surprise — stream verbatim and return.
        # Fires exactly once: only when no prior conversations existed before this request.
        if farida_greeting:
            yield f'data: {json.dumps({"type": "status", "value": "thinking"})}\n\n'
            yield f"data: {json.dumps(farida_greeting)}\n\n"
            yield f'data: {json.dumps({"type": "usage", "data": {}})}\n\n'
            yield "data: [DONE]\n\n"
            if sb and conv_id:
                try:
                    await asyncio.to_thread(_save_assistant_message, sb, conv_id, farida_greeting)
                    asyncio.create_task(_auto_title(sb, conv_id, request.message))
                except Exception:
                    pass
            return

        # Immediate "thinking" signal — arrives within ~100ms of user sending,
        # guarantees the UI indicator is on before the first model token.
        yield f'data: {json.dumps({"type": "status", "value": "thinking"})}\n\n'

        current_messages = messages.copy()
        final_text = ""
        got_final_response = False

        try:
            async with httpx.AsyncClient() as client:
                for _round in range(MAX_TOOL_ROUNDS):
                    request_body: dict = {
                        "model": model,
                        "max_tokens": max_tokens,
                        "system": system_prompt,
                        "messages": current_messages,
                        "stream": True,
                    }
                    if tools:
                        request_body["tools"] = tools

                    # ── True streaming Anthropic call ─────────────────────────
                    # Tokens arrive and are forwarded to the client as they're
                    # generated — no buffering of the entire completion.
                    content_blocks_map: dict[int, dict] = {}
                    tool_input_buf: dict[int, str] = {}
                    stop_reason = "end_turn"
                    per_round_text = ""
                    stream_api_error: str | None = None

                    async with client.stream(
                        "POST",
                        "https://api.anthropic.com/v1/messages",
                        headers={
                            "x-api-key": ANTHROPIC_API_KEY,
                            "anthropic-version": "2023-06-01",
                            "content-type": "application/json",
                        },
                        json=request_body,
                        timeout=120.0,
                    ) as stream_resp:
                        if stream_resp.status_code != 200:
                            err_bytes = await stream_resp.aread()
                            print(f"Anthropic error {stream_resp.status_code}: {err_bytes[:300]}")
                            yield f'data: {json.dumps("Error connecting to AI. Please try again.")}\n\n'
                            yield "data: [DONE]\n\n"
                            return

                        async for raw_line in stream_resp.aiter_lines():
                            if not raw_line.startswith("data: "):
                                continue
                            raw = raw_line[6:]
                            try:
                                ev = json.loads(raw)
                            except Exception:
                                continue

                            ev_type = ev.get("type", "")

                            if ev_type == "content_block_start":
                                idx = ev["index"]
                                blk = ev["content_block"]
                                btype = blk["type"]
                                if btype == "text":
                                    content_blocks_map[idx] = {"type": "text", "text": ""}
                                elif btype == "tool_use":
                                    content_blocks_map[idx] = {
                                        "type": "tool_use",
                                        "id": blk["id"],
                                        "name": blk["name"],
                                        "input": {},
                                    }
                                    tool_input_buf[idx] = ""

                            elif ev_type == "content_block_delta":
                                idx = ev["index"]
                                delta = ev["delta"]
                                dtype = delta["type"]

                                if dtype == "text_delta":
                                    text = delta.get("text", "")
                                    if text:
                                        # Forward token to client immediately
                                        yield f"data: {json.dumps(text)}\n\n"
                                        per_round_text += text
                                        if idx in content_blocks_map:
                                            content_blocks_map[idx]["text"] += text

                                elif dtype == "input_json_delta":
                                    tool_input_buf[idx] = (
                                        tool_input_buf.get(idx, "") + delta.get("partial_json", "")
                                    )

                            elif ev_type == "content_block_stop":
                                idx = ev["index"]
                                if idx in tool_input_buf:
                                    raw_inp = tool_input_buf.pop(idx)
                                    try:
                                        parsed = json.loads(raw_inp) if raw_inp else {}
                                    except Exception:
                                        parsed = {}
                                    if idx in content_blocks_map:
                                        content_blocks_map[idx]["input"] = parsed

                            elif ev_type == "message_delta":
                                stop_reason = (
                                    ev.get("delta", {}).get("stop_reason") or stop_reason
                                )

                            elif ev_type == "error":
                                stream_api_error = ev.get("error", {}).get("message", "API error")
                                print(f"Anthropic stream error event: {stream_api_error}")
                                break

                    # ── Post-stream: handle API-level error ───────────────────
                    if stream_api_error:
                        yield f'data: {json.dumps("Error connecting to AI. Please try again.")}\n\n'
                        yield "data: [DONE]\n\n"
                        return

                    # ── Reconstruct content_blocks list for message history ────
                    content_blocks = [
                        content_blocks_map[i] for i in sorted(content_blocks_map.keys())
                    ]

                    # Explicit truncation guard: if the model hit max_tokens while a
                    # tool_use block was in-flight, content_block_stop never fired and
                    # the tool call silently vanished. Surface a clear error instead of
                    # letting the model narrate fake success.
                    if stop_reason == "max_tokens":
                        in_flight_tools = [
                            b for b in content_blocks_map.values()
                            if b.get("type") == "tool_use" and not b.get("input")
                        ]
                        if in_flight_tools:
                            tool_names = ", ".join(b.get("name", "?") for b in in_flight_tools)
                            err_msg = (
                                f"The request was too large for the tool call to complete "
                                f"({tool_names}). Try splitting the request into smaller steps "
                                f"or reduce the amount of data you are working with at once."
                            )
                            yield f"data: {json.dumps(err_msg)}\n\n"
                            yield "data: [DONE]\n\n"
                            got_final_response = True
                            break
                        # max_tokens on a pure text response — text already streamed, close gracefully
                        final_text = per_round_text
                        if request.user_id and sb:
                            updated_usage = await asyncio.to_thread(
                                increment_usage, request.user_id, sb
                            )
                            yield f'data: {json.dumps({"type": "usage", "data": updated_usage})}\n\n'
                        yield "data: [DONE]\n\n"
                        got_final_response = True
                        break

                    if stop_reason != "tool_use":
                        # Final response — text was already streamed token-by-token above
                        final_text = per_round_text
                        if request.user_id and sb:
                            updated_usage = await asyncio.to_thread(
                                increment_usage, request.user_id, sb
                            )
                            yield f'data: {json.dumps({"type": "usage", "data": updated_usage})}\n\n'
                        yield "data: [DONE]\n\n"
                        got_final_response = True
                        break

                    # ── Tool use round ────────────────────────────────────────
                    # Text alongside the tool call was already streamed above.
                    tool_use_blocks = [b for b in content_blocks if b.get("type") == "tool_use"]
                    write_blocks = [b for b in tool_use_blocks if b["name"] in WRITE_ACTIONS]

                    if write_blocks:
                        # Intercept: pause before write action and ask for confirmation.
                        w = write_blocks[0]
                        pending_event = {
                            "type": "pending_action",
                            "action": {
                                "tool_name": w["name"],
                                "tool_input": w.get("input", {}),
                                "tool_id": w["id"],
                                "description": _describe_action(w["name"], w.get("input", {})),
                            },
                        }
                        yield f'data: {json.dumps(pending_event)}\n\n'
                        yield "data: [DONE]\n\n"
                        got_final_response = True
                        break

                    # No write actions — execute all tools and continue the loop
                    current_messages.append({"role": "assistant", "content": content_blocks})

                    tool_results = []
                    for block in tool_use_blocks:
                        tool_name = block["name"]
                        tool_id = block["id"]
                        tool_inp = block.get("input", {})

                        yield f'data: {json.dumps({"type": "tool_call", "name": tool_name, "status": "executing"})}\n\n'
                        result_str = await execute_tool(tool_name, tool_inp, request.user_id)
                        yield f'data: {json.dumps({"type": "tool_call", "name": tool_name, "status": "complete"})}\n\n'

                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_id,
                            "content": result_str,
                        })

                    current_messages.append({"role": "user", "content": tool_results})

            if not got_final_response:
                yield f'data: {json.dumps("I hit a processing limit on that request. Please try a simpler query.")}\n\n'
                yield "data: [DONE]\n\n"

        except Exception as e:
            import traceback
            print(f"BUSINESS CHAT: Error: {e}")
            traceback.print_exc()
            yield f'data: {json.dumps("Something went wrong. Please try again.")}\n\n'
            yield "data: [DONE]\n\n"
            return

        # Post-stream: persist assistant message + memory extraction
        if sb and conv_id and final_text:
            try:
                await asyncio.to_thread(_save_assistant_message, sb, conv_id, final_text)

                if is_new_conv:
                    asyncio.create_task(_auto_title(sb, conv_id, request.message))

                await extract_and_store_memories(
                    request.user_id, conv_id, request.message, final_text, sb
                )
            except Exception as e:
                print(f"Post-stream persistence error: {e}")

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


class ConfirmActionRequest(BaseModel):
    user_id: str
    tool_name: str
    tool_input: dict
    conversation_id: str | None = None


@router.post("/business/chat/confirm-action")
async def confirm_action(request: ConfirmActionRequest):
    """Execute a write action that was deferred for user confirmation."""
    result_str = await execute_tool(request.tool_name, request.tool_input, request.user_id)

    try:
        result_data = json.loads(result_str) if isinstance(result_str, str) else result_str
    except Exception:
        result_data = {}

    # Generate a natural language confirmation via a fast model
    confirmation_text = _make_fallback_confirmation(request.tool_name, result_data)
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
                    "max_tokens": 150,
                    "messages": [{
                        "role": "user",
                        "content": (
                            f"The action '{request.tool_name}' was just executed with result: "
                            f"{json.dumps(result_data)[:400]}. "
                            "Write a brief 1-2 sentence natural confirmation of what was done. "
                            "Be specific and direct. No pleasantries."
                        ),
                    }],
                },
                timeout=30.0,
            )
        if resp.status_code == 200:
            text = resp.json().get("content", [{}])[0].get("text", "").strip()
            if text:
                confirmation_text = text
    except Exception as e:
        print(f"confirm-action: LLM fallback error: {e}")

    # Persist the confirmation message to conversation history
    if request.conversation_id and request.user_id:
        sb = _get_supabase()
        if sb:
            try:
                await asyncio.to_thread(_save_assistant_message, sb, request.conversation_id, confirmation_text)
            except Exception as e:
                print(f"confirm-action: DB save error: {e}")

    return {"response": confirmation_text, "tool_result": result_data}


def _make_fallback_confirmation(tool_name: str, result_data: dict) -> str:
    if "error" in result_data:
        return f"Action failed: {result_data['error']}"
    if result_data.get("status") == "deleted":
        return "Deleted successfully."
    if result_data.get("status") == "updated":
        return "Updated successfully."
    if result_data.get("status") == "sent":
        return "Sent successfully."
    if "event_id" in result_data:
        return f"Event created. Link: {result_data.get('link', 'N/A')}"
    return "Done."
