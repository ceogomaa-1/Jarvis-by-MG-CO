import asyncio
import json
import os
import re
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from supabase import create_client

from backend.lib.business.system_prompt_builder import build_system_prompt
from backend.lib.business.farida_loader import FARIDA_USER_ID, load_greeting as _load_farida_greeting
from backend.lib.business.model_router import select_model, OPUS, HAIKU
from backend.lib.business.cost import UsageAccumulator
from backend.lib.business.memory import extract_and_store_memories, should_extract_memories
from backend.lib.business.mind.graph import record_activity
from backend.lib.business.prompt_budget import (
    CHAT_HISTORY_CHAR_CAP,
    TOOL_RESULT_CHAR_CAP,
    cap_dynamic_prompt,
    cap_tool_result,
    chat_output_token_budget,
    trim_history,
)
from backend.lib.business.tool_builder import (
    build_tools_for_user, TWENTY_WRITE_TOOLS, TWENTY_DESTRUCTIVE_TOOLS, TWENTY_BULK_TOOLS,
    TWENTY_METADATA_TOOLS, TWENTY_METADATA_WRITE, TWENTY_METADATA_DESTRUCTIVE,
)
from backend.lib.business.tool_executor import execute_tool
from backend.lib.business.document_store import save_document
from backend.lib.business.real_estate.profile import is_real_estate_user
from backend.lib.business.intent_router import classify_message_intent
from backend.lib.business import crm_enrich
from backend.lib.business import home_layout as _home_layout
from backend.lib.business import dashboard_studio as _dashboard_studio
from backend.usage_limits import check_limit, increment_usage, get_usage, DAILY_MESSAGE_LIMIT
from backend.lib.billing import entitlements, config as billing_config, store as billing_store
from backend.tools.citation_context import init_collector

router = APIRouter()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
SUPABASE_URL = os.getenv("NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# Tool-round spend guard for the web Business brain. Eight rounds still supports meaningful
# chained work; the environment can raise it to 15 for a deliberate workflow. Genuinely huge
# per-record bulk ops are routed out of the chat turn entirely — see crm_enrich.
try:
    MAX_TOOL_ROUNDS = max(3, min(int(os.getenv("JARVIS_MAX_TOOL_ROUNDS", "8")), 15))
except ValueError:
    MAX_TOOL_ROUNDS = 8

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
    "stripe__create_subscription_tier",
    "stripe__create_product",
    "stripe__create_price",
    "buffer__create_post",
    "buffer__schedule_post",
    "buffer__add_to_queue",
    "realestate__ghl_add_note",
    "realestate__book_showing",
    # Jarvis CRM (Twenty) destructive writes — record deletes + raw-GraphQL escape
    # hatch + structural deletes (field/object/view). Derived from the tool registry.
    *TWENTY_DESTRUCTIVE_TOOLS,
    *TWENTY_METADATA_DESTRUCTIVE,
    # Bulk record edits (set a field across many records) — confirm before they land.
    *TWENTY_BULK_TOOLS,
})

# Every Jarvis CRM write — record-level AND structural — refreshes the embedded CRM
# view ("feels live"). Derived from the registries so new tools are covered automatically.
# leads__push_to_crm creates Companies in the CRM, so it triggers a refresh too.
CRM_WRITE_ACTIONS = frozenset(TWENTY_WRITE_TOOLS.keys()) | TWENTY_METADATA_WRITE | {"leads__push_to_crm"}

# mgcoleads cockpit: a lead search or a push changes the leads pipeline, so the Leads
# cockpit panel refreshes ("feels live") — independent of the CRM embed refresh above.
# (push_to_crm fires both: it adds a CRM Company AND flips the lead's pushed flag.)
LEADS_CHANGED_ACTIONS = frozenset({"leads__find_leads", "leads__push_to_crm"})

# Batch 68: a dashboard__control call mutated the user's Home dashboard — refresh the
# Home cockpit so the new/edited/restyled block (or theme) shows immediately ("feels live").
HOME_CHANGED_ACTIONS = frozenset({"dashboard__control"})


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
        agent_id = tool_input.get("agent_id", "?")
        changes = []
        if "first_message" in tool_input:
            changes.append(f'greeting → "{tool_input["first_message"][:70]}"')
        if "system_prompt" in tool_input:
            changes.append("system prompt")
        if "name" in tool_input:
            changes.append(f'name → {tool_input["name"]}')
        if "voice_id" in tool_input:
            changes.append("voice")
        detail = ", ".join(changes) if changes else "config"
        return f"Update agent {agent_id}: {detail}"
    if "delete_agent" in tool_name:
        return f"Delete agent: {tool_input.get('agent_id', '?')}"
    if "create_contact" in tool_name:
        first = tool_input.get("firstName", "")
        last = tool_input.get("lastName", "")
        return f"Create contact: {(first + ' ' + last).strip() or '?'}"
    if tool_name == "stripe__create_subscription_tier":
        amount = tool_input.get("amount_cents", 0) or 0
        interval = tool_input.get("interval", "month")
        cur = (tool_input.get("currency", "usd") or "usd").upper()
        return f"Create Stripe tier: {tool_input.get('name', '?')} — {cur} {amount / 100:.2f}/{interval}"
    if tool_name == "stripe__create_product":
        return f"Create Stripe product: {tool_input.get('name', '?')}"
    if tool_name == "stripe__create_price":
        amount = tool_input.get("unit_amount", 0) or 0
        cur = (tool_input.get("currency", "usd") or "usd").upper()
        interval = tool_input.get("interval")
        suffix = f"/{interval}" if interval else " one-time"
        return f"Create Stripe price on {tool_input.get('product_id', '?')}: {cur} {amount / 100:.2f}{suffix}"
    if tool_name.startswith("twenty__delete_"):
        obj = tool_name.replace("twenty__delete_", "")
        who = (tool_input.get("query") or tool_input.get(f"{obj}_id")
               or tool_input.get("person_id") or tool_input.get("note_id")
               or tool_input.get("task_id") or "?")
        return f"Delete {obj} from Jarvis CRM: {who}"
    if tool_name == "twenty__delete_field":
        return f"Delete CRM field '{tool_input.get('field', '?')}' from {tool_input.get('object', '?')}"
    if tool_name == "twenty__delete_object":
        return f"Delete CRM type '{tool_input.get('name', '?')}' (and all its records)"
    if tool_name == "twenty__delete_view":
        return f"Delete CRM list '{tool_input.get('name') or tool_input.get('view_id', '?')}'"
    if tool_name == "twenty__bulk_update":
        obj = tool_input.get("object_type", "record")
        n = len(tool_input.get("names") or []) or len(tool_input.get("ids") or [])
        scope = "all" if tool_input.get("all") and not n else f"{n}"
        fields = ", ".join(f"{k}={v}" for k, v in (tool_input.get("fields") or {}).items())
        return f"Bulk-set on {scope} {obj}(s): {fields or '?'}"
    if tool_name == "twenty__rehome_field":
        return (f"Move CRM field '{tool_input.get('from_field', '?')}' → "
                f"'{tool_input.get('to_field', '?')}' on {tool_input.get('object_type', 'company')}(s)")
    if tool_name == "twenty__run_graphql_mutation":
        m = (tool_input.get("mutation") or "").strip().replace("\n", " ")
        return f"Run a custom Jarvis CRM mutation: {m[:90]}"
    if tool_name == "realestate__ghl_add_note":
        note = (tool_input.get("note") or "")[:80]
        return f"Add CRM note: {note or '?'}"
    if tool_name == "realestate__book_showing":
        return f"Book showing: {tool_input.get('property_address', '?')} w/ {tool_input.get('client_name', '?')}"
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


_PARTIAL_FALLBACK = (
    "I made progress but ran out of room to finish this in one go. Want me to keep going? "
    "Say \"keep going\" and I'll pick up where I left off."
)


async def _summarize_partial_progress(model, system_blocks, current_messages, usage_acc) -> str:
    """One final no-tools completion that summarizes the partial work and offers to continue.

    Called only when the tool-round budget is exhausted (after the streaming client has closed,
    so it opens its own). Removing tools forces the model to answer in text (it can't burn
    another round) and bounds the extra cost (small max_tokens)."""
    try:
        nudge = {
            "role": "user",
            "content": (
                "You've hit the step budget for this turn before fully finishing. Do NOT call any "
                "tools. In 2-4 sentences, tell me concretely what you completed so far (with counts "
                "if you have them) and exactly what's left, then ask if I want you to keep going."
            ),
        }
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
                    "max_tokens": 400,
                    "system": system_blocks,
                    "messages": current_messages + [nudge],
                    "cache_control": {"type": "ephemeral"},
                },
                timeout=60.0,
            )
        if resp.status_code == 200:
            body = resp.json()
            try:
                usage_acc.add_message_start(body.get("usage", {}))
                usage_acc.add_round_output((body.get("usage", {}) or {}).get("output_tokens", 0))
            except Exception:
                pass
            text = "".join(
                b.get("text", "") for b in body.get("content", []) if b.get("type") == "text"
            ).strip()
            if text:
                return text
    except Exception as e:
        print(f"BUSINESS CHAT: partial-progress summary failed: {e}")
    return _PARTIAL_FALLBACK


def _setup_conversation(sb, user_id: str, conv_id: str | None, message: str, attachments: list[dict] | None = None) -> tuple[str | None, bool]:
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
        row = {
            "conversation_id": conv_id,
            "role": "user",
            "content": message,
        }
        if attachments:
            row["attachments"] = attachments
        sb.table("business_messages").insert(row).execute()

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
    """Create a useful conversation title without spending a second model call."""
    try:
        clean = re.sub(r"https?://\S+", "", first_user_message or "")
        clean = re.sub(r"[^\w&'+-]+", " ", clean).strip()
        words = clean.split()
        title = " ".join(words[:6]).strip()
        if len(words) > 6:
            title += "…"
        if title:
            await asyncio.to_thread(_update_title, sb, conv_id, title[:80])
    except Exception as e:
        print(f"Auto-title error: {e}")


class AttachmentItem(BaseModel):
    type: str = "image"          # "image" | "document" | "text_file"
    media_type: str = "image/jpeg"
    data: str                    # base64-encoded
    name: str = ""               # original filename (for text_file fallback label)
    storage_path: str | None = None  # path in the chat-attachments Supabase bucket
    size: int | None = None      # file size in bytes


class BusinessChatRequest(BaseModel):
    message: str
    user_id: str = ""
    conversation_history: list = []
    conversation_id: str | None = None
    attachments: list[AttachmentItem] = []
    node_context: dict | None = None
    surface: str | None = None        # 'home' when sent from the docked Home chat (Batch 67)


async def _apply_home_layout_command(user_id: str, message: str) -> tuple[str, bool]:
    """Phase 2: apply a natural-language Home layout command and persist it.

    Returns (reply_text, changed). Reuses the deterministic parser in home_layout; the
    docked Home chat routes layout commands here so customization is conversational and live.
    """
    layout_url = os.getenv("SUPABASE_URL") or SUPABASE_URL or ""
    if not layout_url or not SUPABASE_KEY:
        return "I can't reach your layout store right now.", False
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    current = None
    try:
        custom_specs = _dashboard_studio.custom_layout_specs(
            await _dashboard_studio.list_custom_blocks(user_id))
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{layout_url}/rest/v1/business_home_layout",
                headers=headers,
                params={"select": "layout", "user_id": f"eq.{user_id}", "limit": "1"},
                timeout=10.0,
            )
            if resp.status_code == 200 and resp.json():
                current = resp.json()[0].get("layout")
            new_layout, reply, changed = _home_layout.apply_command(current, message, custom=custom_specs)
            if changed:
                await client.post(
                    f"{layout_url}/rest/v1/business_home_layout?on_conflict=user_id",
                    headers={**headers, "Content-Type": "application/json",
                             "Prefer": "resolution=merge-duplicates,return=minimal"},
                    json={"user_id": user_id, "layout": new_layout,
                          "is_default": False, "updated_at": "now()"},
                    timeout=12.0,
                )
        return reply, changed
    except Exception as e:
        print(f"BUSINESS CHAT: home layout command failed: {e}")
        return "Something went wrong updating your layout.", False


def _node_context_block(node_context: dict | None) -> str:
    """Build a context block for a Mind-graph node the user clicked before sending this message."""
    if not node_context:
        return ""
    mode = node_context.get("mode")
    if mode == "gap":
        label = node_context.get("label", "")
        prompt = node_context.get("prompt", "")
        return (
            f"[Context: The user clicked on a knowledge gap in their Mind graph — \"{label}\". "
            f"They want to give you this missing info now. Ask them directly: {prompt}]"
        )
    if mode == "synapse":
        insight = node_context.get("insight", "")
        memory_a = node_context.get("memory_a_text", "")
        memory_b = node_context.get("memory_b_text", "")
        return (
            f"[Context: The user clicked on a golden synapse in their Mind graph — a hidden connection "
            f"Jarvis found between two memories.\nMemory A: \"{memory_a}\"\nMemory B: \"{memory_b}\"\n"
            f"Insight: {insight}\nDiscuss this connection with the user.]"
        )
    # mode == "memory" (default)
    memory_text = node_context.get("memory_text", "")
    mind_category = node_context.get("mind_category", "")
    return (
        f"[Context: the user clicked on this memory in their Mind graph]\n"
        f"\"{memory_text}\"\nCategory: {mind_category}"
    )


def _build_user_content(
    text: str,
    attachments: list[AttachmentItem],
    stash_pdfs: bool = False,
    node_context: dict | None = None,
) -> list | str:
    """Build Anthropic content block(s) for a user turn, including images/PDFs/text.

    When stash_pdfs is set (Real Estate users), PDF attachments are also saved to
    document_store so Claude can reference them by doc_id with realestate__fill_pdf_form.
    """
    context_block = _node_context_block(node_context)
    if not attachments:
        return f"{context_block}\n\n{text}" if context_block else text
    import base64
    blocks: list = []
    if context_block:
        blocks.append({"type": "text", "text": context_block})
    doc_id_notes: list[str] = []
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
            if stash_pdfs:
                try:
                    pdf_bytes = base64.b64decode(att.data)
                    saved = save_document(pdf_bytes, att.name or "attachment.pdf", "application/pdf")
                    doc_id_notes.append(
                        f'[Attached PDF "{saved["filename"]}" — doc_id: {saved["doc_id"]}. '
                        f"If the user asks you to fill it in, call realestate__fill_pdf_form with this doc_id.]"
                    )
                except Exception:
                    pass
        else:
            # Text/CSV/plain — decode and inject as labelled text block
            try:
                decoded = base64.b64decode(att.data).decode("utf-8", errors="replace")
                label = att.name or "file"
                blocks.append({"type": "text", "text": f"[File: {label}]\n{decoded[:8000]}"})
            except Exception:
                pass
    if doc_id_notes:
        blocks.append({"type": "text", "text": "\n".join(doc_id_notes)})
    blocks.append({"type": "text", "text": text})
    return blocks


def _trim_for_trial(message: str, history: list, char_cap: int) -> tuple[str, list]:
    """Bound a trial turn's input so one huge paste can't spike the cost.

    Caps the current message to `char_cap`, keeps only the last few turns, and truncates each
    of those. Attachments are dropped separately by the caller (images/PDFs are the other big
    input-cost lever on a trial)."""
    msg = (message or "")[:char_cap]
    per_turn = max(1000, char_cap // 6)
    trimmed = [
        {"role": m["role"], "content": str(m.get("content", ""))[:per_turn]}
        for m in (history or [])[-6:]
    ]
    return msg, trimmed


@router.get("/business/usage")
async def get_user_usage(user_id: str = ""):
    """Return today's usage info for the given user (tier-aware: Emperor gets the 5x window)."""
    if not user_id:
        return {"error": "user_id required"}
    sb = _get_supabase()
    if not sb:
        return {"used": 0, "limit": 32, "remaining": 32, "is_admin": False, "resets_in": "", "window_minutes": 90}
    limit = await asyncio.to_thread(entitlements.effective_message_limit, user_id, DAILY_MESSAGE_LIMIT)
    usage = await asyncio.to_thread(get_usage, user_id, sb, limit)
    return usage


@router.get("/business/cost-controls")
async def get_cost_controls():
    """Non-AI deployment probe for the active spend-control revision."""
    from backend.lib.business.operator.creator import creator_advisor_enabled, creator_batch_enabled

    return {
        "revision": "prompt-cache-v2",
        "website_workflow_revision": "surgical-edit-v1",
        "automatic_conversation_caching": True,
        "static_system_caching": True,
        "tool_definition_caching": True,
        "operator_creator_batching": True,
        "operator_creator_batch_active_for_2_plus": creator_batch_enabled(2),
        "operator_creator_batch_discount": 0.5,
        "operator_creator_advisor_enabled": creator_advisor_enabled(),
        "history_char_cap": CHAT_HISTORY_CHAR_CAP,
        "tool_result_char_cap": TOOL_RESULT_CHAR_CAP,
        "max_tool_rounds": MAX_TOOL_ROUNDS,
        "routine_intent_calls": False,
        "routine_memory_calls": False,
    }


class IntentClassifyRequest(BaseModel):
    message: str
    active_agent_id: str | None = None
    recent_assistant_texts: list[str] | None = None
    has_attachments: bool = False


@router.post("/business/classify-intent")
async def classify_intent_route(request: IntentClassifyRequest):
    """Single classification call deciding whether a Business chat message
    belongs to the regular chat flow, a show-me-how walkthrough, or the
    creation pipeline. Replaces the old frontend regex cascade."""
    return await classify_message_intent(
        request.message,
        active_agent_id=request.active_agent_id,
        recent_assistant_texts=request.recent_assistant_texts,
        has_attachments=request.has_attachments,
    )


@router.post("/business/chat/stream")
async def business_chat_stream(request: BusinessChatRequest):
    # Phase 2 (Batch 67): the docked Home chat sends surface="home". If the message is a
    # deterministic layout command ("move CRM to the top", "build me a CEO dashboard"),
    # apply it live and emit home_changed — no model call, instant + conversational.
    if (request.surface == "home" and request.user_id
            and _home_layout.is_home_layout_command(request.message)):
        async def _home_cmd_stream():
            reply, changed = await _apply_home_layout_command(request.user_id, request.message)
            yield f"data: {json.dumps(reply)}\n\n"
            if changed:
                yield f'data: {json.dumps({"type": "home_changed"})}\n\n'
            yield "data: [DONE]\n\n"
        return StreamingResponse(
            _home_cmd_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )

    static_prompt, dynamic_prompt, used_memory_ids = await build_system_prompt(request.user_id, request.message)
    dynamic_prompt = cap_dynamic_prompt(dynamic_prompt)
    tools = await build_tools_for_user(request.user_id)
    is_re_user = bool(request.user_id) and await is_real_estate_user(request.user_id)

    # ── OS1 tier enforcement ──────────────────────────────────────────────────
    # Resolve this user's plan once. Drives THREE caps on the OS1 Business path:
    #   • usage window multiplier (Emperor = 5x base, Pro/trial = base)
    #   • trial COST ceiling (a hard $ cap that replaces the old message-count taste)
    #   • trial cost-control: cheapest model + capped output + truncated input
    # Grandfathered / no-row users map to a 1x multiplier and are never trials, so existing
    # users are unaffected.
    is_trial = False
    usage_multiplier = 1
    trial_cost_blocked = False
    trial_cost_info: dict = {}
    if request.user_id:
        try:
            caps = await asyncio.to_thread(entitlements.for_user, request.user_id)
            is_trial = caps.get("plan") == "trial"
            usage_multiplier = caps.get("usage_multiplier") or 1
            if usage_multiplier < 1:
                usage_multiplier = 1
            if is_trial:
                trial_cost_info = await asyncio.to_thread(
                    entitlements.trial_cost_status, request.user_id
                )
                trial_cost_blocked = bool(trial_cost_info.get("exceeded"))
        except Exception as e:
            print(f"[OS1 ENTITLEMENTS] resolve error: {e}")

    # ── Prompt caching ────────────────────────────────────────────────────────
    # Two system blocks: a STATIC block (persona, contracts, capabilities, connector rules)
    # carrying the cache_control breakpoint — byte-identical across turns for this user, so it
    # is WRITTEN once and READ (~0.1x) on every subsequent turn and every tool round — then a
    # DYNAMIC block (memories, queue, skills, per-message bible) placed AFTER the breakpoint so
    # it never disturbs the cached prefix. Tool defs are cached too (breakpoint on the last
    # tool). Render order is tools → system → messages.
    system_blocks = [{
        "type": "text",
        "text": static_prompt,
        "cache_control": {"type": "ephemeral"},
    }]
    if dynamic_prompt:
        system_blocks.append({"type": "text", "text": dynamic_prompt})
    if tools:
        # Don't mutate the cached tool dicts in the registry — copy the last one.
        tools = list(tools)
        tools[-1] = {**tools[-1], "cache_control": {"type": "ephemeral"}}

    safe_history = trim_history(request.conversation_history)

    # Trials: bound the INPUT so a huge paste can't spike one turn, and drop attachments
    # (images/PDFs are the other big input-cost lever). The taste stays text-only and cheap.
    trial_message = request.message
    trial_attachments = request.attachments
    if is_trial:
        trial_message, safe_history = _trim_for_trial(
            request.message, safe_history, billing_config.TRIAL_CONTEXT_CHAR_CAP
        )
        trial_attachments = []

    user_content = _build_user_content(
        trial_message, trial_attachments, stash_pdfs=is_re_user, node_context=request.node_context
    )
    messages = safe_history + [{"role": "user", "content": user_content}]

    model = select_model(request.message, has_attachments=bool(trial_attachments))
    # Model-specific ceilings prevent runaway prose while retaining tool-call headroom.
    max_tokens = chat_output_token_budget(model)
    # Trials run on the cheapest tier with a capped output budget so the same cost ceiling
    # buys many more turns AND no single response can blow it.
    if is_trial:
        model = HAIKU
        max_tokens = billing_config.TRIAL_MAX_TOKENS

    sb = _get_supabase() if request.user_id else None
    conv_id = request.conversation_id
    is_new_conv = False

    # Check usage limit before creating conversation or calling Anthropic. The ceiling is
    # tier-scaled: Emperor gets 5x the base window, Pro/trial get the base.
    effective_limit = DAILY_MESSAGE_LIMIT * usage_multiplier
    limit_exceeded = False
    limit_usage_info: dict = {}
    if sb and request.user_id:
        allowed, limit_usage_info = await asyncio.to_thread(
            check_limit, request.user_id, sb, effective_limit
        )
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

    if not limit_exceeded and not trial_cost_blocked and sb and request.user_id:
        try:
            attachments_meta = [
                {
                    "name": a.name,
                    "media_type": a.media_type,
                    "size": a.size,
                    "storage_path": a.storage_path,
                }
                for a in request.attachments if a.storage_path
            ]
            conv_id, is_new_conv = await asyncio.to_thread(
                _setup_conversation, sb, request.user_id, conv_id, request.message, attachments_meta
            )
        except Exception as e:
            print(f"Pre-stream DB setup error: {e}")
            conv_id = request.conversation_id

    async def generate():
        # Per-request citation collector — so web__search / web__fetch_url register
        # sources and their inline [1], [2] numbering lines up. Tools run in tasks
        # whose context is copied AFTER this set(), and add_source mutates the shared
        # list, so appends remain visible across those tasks.
        init_collector()

        # Limit check — yield friendly message and bail
        if limit_exceeded:
            limit = limit_usage_info.get("limit", 32)
            window = limit_usage_info.get("window_label", "4 hours")
            resets = limit_usage_info.get("resets_in", "soon")
            msg = (
                f"You've hit your limit for now — {limit} messages per {window}. "
                f"Your next slot opens in {resets}. Jarvis will be here."
            )
            yield f"data: {json.dumps(msg)}\n\n"
            yield f'data: {json.dumps({"type": "usage", "data": limit_usage_info})}\n\n'
            yield "data: [DONE]\n\n"
            return

        # Trial COST ceiling — the hard $ cap that replaces the old message-count taste.
        if trial_cost_blocked:
            msg = (
                "Your free trial limit is reached — pick a plan to keep going. "
                "You've explored what Jarvis can do; upgrade to Pro or Emperor to unlock "
                "the full experience with no cap."
            )
            yield f"data: {json.dumps(msg)}\n\n"
            yield f'data: {json.dumps({"type": "trial_limit", "data": trial_cost_info})}\n\n'
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

        # Mind thought-trace: light up the memories injected into this turn's system prompt.
        if used_memory_ids and request.user_id:
            yield f'data: {json.dumps({"type": "memory_used", "ids": used_memory_ids})}\n\n'
            asyncio.create_task(record_activity(request.user_id, used_memory_ids, "used", conv_id))

        current_messages = messages.copy()
        final_text = ""
        got_final_response = False

        # Per-turn cost accounting — sums token usage across every tool round so
        # we can log the real cost of this action and show the cache savings.
        usage_acc = UsageAccumulator(model)

        def _cost_event() -> str:
            """Log the turn cost and return an SSE 'cost' event (call once, at the end).

            For trial users this is also where we bill the turn against the hard cost ceiling:
            the accumulated, cache-net cost of every round in this turn is added to the trial
            ledger (fire-and-forget — best effort, like the memory extraction below)."""
            try:
                print(usage_acc.log_line())
            except Exception:
                pass
            if is_trial and request.user_id:
                turn_cost = usage_acc.cost().get("total_usd", 0.0)
                asyncio.create_task(
                    asyncio.to_thread(billing_store.add_trial_cost, request.user_id, turn_cost)
                )
            return f'data: {json.dumps({"type": "cost", "data": usage_acc.cost()})}\n\n'

        # ── Bulk CRM enrichment → detached background job ─────────────────────
        # "Get phone numbers for all 42 companies" is a per-record bulk op that blows past
        # the tool-round budget AND the 120s request window. Detect it up front, answer
        # immediately, and hand the work to a task that writes results into the CRM as it
        # finds them and reports back here when done — outside this HTTP request, so it can't
        # time out mid-run. Trials are excluded (bulk Maps lookups are a cost lever the taste
        # shouldn't spend); anything not enrichable here falls through to the normal model.
        bulk = crm_enrich.detect_bulk_enrichment(request.message) if (request.user_id and not is_trial) else None
        if bulk:
            try:
                prepared = await crm_enrich.prepare(request.user_id, bulk["fields"], bulk.get("limit"))
            except Exception as e:
                print(f"BUSINESS CHAT: bulk-enrich prepare failed: {e}")
                prepared = {"status": "skip"}

            if prepared["status"] in ("ok", "nothing"):
                reply = prepared["ack"] if prepared["status"] == "ok" else prepared["message"]
                yield f"data: {json.dumps(reply)}\n\n"
                if prepared["status"] == "ok":
                    task = asyncio.create_task(
                        crm_enrich.run_enrichment(request.user_id, conv_id, prepared)
                    )
                    crm_enrich.track_task(task)
                if request.user_id and sb:
                    updated_usage = await asyncio.to_thread(
                        increment_usage, request.user_id, sb, effective_limit
                    )
                    yield f'data: {json.dumps({"type": "usage", "data": updated_usage})}\n\n'
                yield _cost_event()
                yield "data: [DONE]\n\n"
                if sb and conv_id:
                    try:
                        await asyncio.to_thread(_save_assistant_message, sb, conv_id, reply)
                        if is_new_conv:
                            asyncio.create_task(_auto_title(sb, conv_id, request.message))
                    except Exception as e:
                        print(f"BUSINESS CHAT: bulk-enrich ack persist error: {e}")
                return
            # status == "skip" → fall through to the normal model flow.

        try:
            async with httpx.AsyncClient() as client:
                for _round in range(MAX_TOOL_ROUNDS):
                    request_body: dict = {
                        "model": model,
                        "max_tokens": max_tokens,
                        "system": system_blocks,
                        "messages": current_messages,
                        "stream": True,
                        # Automatic caching advances the breakpoint through the growing message
                        # history on every tool/chat round. Explicit breakpoints above still keep
                        # tools and the stable system block independently reusable.
                        "cache_control": {"type": "ephemeral"},
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
                    round_output_tokens = 0  # latest cumulative output for THIS round

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

                            if ev_type == "message_start":
                                # Input/cache token buckets for this round.
                                usage_acc.add_message_start(
                                    ev.get("message", {}).get("usage", {})
                                )

                            elif ev_type == "content_block_start":
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
                                _u = ev.get("usage") or {}
                                if _u.get("output_tokens") is not None:
                                    round_output_tokens = _u["output_tokens"]

                            elif ev_type == "error":
                                stream_api_error = ev.get("error", {}).get("message", "API error")
                                print(f"Anthropic stream error event: {stream_api_error}")
                                break

                    # Finalize this round's output-token contribution.
                    usage_acc.add_round_output(round_output_tokens)

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
                            yield _cost_event()
                            yield "data: [DONE]\n\n"
                            got_final_response = True
                            break
                        # max_tokens on a pure text response — text already streamed, close gracefully
                        final_text = per_round_text
                        if request.user_id and sb:
                            updated_usage = await asyncio.to_thread(
                                increment_usage, request.user_id, sb, effective_limit
                            )
                            yield f'data: {json.dumps({"type": "usage", "data": updated_usage})}\n\n'
                        yield _cost_event()
                        yield "data: [DONE]\n\n"
                        got_final_response = True
                        break

                    if stop_reason != "tool_use":
                        # Final response — text was already streamed token-by-token above
                        final_text = per_round_text
                        if request.user_id and sb:
                            updated_usage = await asyncio.to_thread(
                                increment_usage, request.user_id, sb, effective_limit
                            )
                            yield f'data: {json.dumps({"type": "usage", "data": updated_usage})}\n\n'
                        yield _cost_event()
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
                        yield _cost_event()
                        yield "data: [DONE]\n\n"
                        got_final_response = True
                        break

                    # No write actions — independent read tools from the same model round can run
                    # concurrently. This shortens the turn without adding another model round.
                    current_messages.append({"role": "assistant", "content": content_blocks})

                    running_tools: list[tuple[dict, asyncio.Task, asyncio.Queue]] = []
                    for block in tool_use_blocks:
                        tool_name = block["name"]
                        tool_inp = block.get("input", {})

                        yield f'data: {json.dumps({"type": "tool_call", "name": tool_name, "status": "executing"})}\n\n'

                        progress_q: asyncio.Queue = asyncio.Queue()

                        async def _progress_cb(msg: str, queue: asyncio.Queue = progress_q):
                            await queue.put(msg)

                        tool_task = asyncio.create_task(
                            execute_tool(tool_name, tool_inp, request.user_id, progress_cb=_progress_cb)
                        )
                        running_tools.append((block, tool_task, progress_q))

                    # Drain progress from every running tool so long research steps stay visible.
                    while any(not task.done() or not queue.empty() for _, task, queue in running_tools):
                        emitted_progress = False
                        for block, _, progress_q in running_tools:
                            while not progress_q.empty():
                                msg = progress_q.get_nowait()
                                emitted_progress = True
                                yield f'data: {json.dumps({"type": "tool_progress", "name": block["name"], "value": msg})}\n\n'
                        if not emitted_progress:
                            await asyncio.sleep(0.1)

                    tool_results = []
                    for block, tool_task, _ in running_tools:
                        tool_name = block["name"]
                        result_str = await tool_task
                        yield f'data: {json.dumps({"type": "tool_call", "name": tool_name, "status": "complete"})}\n\n'

                        # "Feels live": signal the embedded CRM view to refresh after a
                        # successful Jarvis CRM write (skip on error results).
                        if tool_name in CRM_WRITE_ACTIONS and '"error"' not in (result_str or ""):
                            yield f'data: {json.dumps({"type": "crm_changed"})}\n\n'

                        # Same idea for the Leads cockpit panel after a find/push.
                        if tool_name in LEADS_CHANGED_ACTIONS and '"error"' not in (result_str or ""):
                            yield f'data: {json.dumps({"type": "leads_changed"})}\n\n'

                        # Batch 68: a dashboard edit landed — refresh the Home cockpit.
                        if tool_name in HOME_CHANGED_ACTIONS and '"error"' not in (result_str or ""):
                            yield f'data: {json.dumps({"type": "home_changed"})}\n\n'

                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block["id"],
                            "content": cap_tool_result(result_str),
                        })

                    current_messages.append({"role": "user", "content": tool_results})

            if not got_final_response:
                # Cap reached mid-task. Don't dead-end — make ONE final no-tools call so the
                # model narrates what it actually got done and offers to keep going, then hand
                # the partial work back. (No tools = it must produce text, and can't spend more
                # rounds.) Falls back to a static message if even that call fails.
                graceful = await _summarize_partial_progress(
                    model, system_blocks, current_messages, usage_acc
                )
                yield f"data: {json.dumps(graceful)}\n\n"
                final_text = graceful
                if request.user_id and sb:
                    updated_usage = await asyncio.to_thread(
                        increment_usage, request.user_id, sb, effective_limit
                    )
                    yield f'data: {json.dumps({"type": "usage", "data": updated_usage})}\n\n'
                yield _cost_event()
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

                # Memory extraction makes its own LLM call (several seconds). Running it
                # inline here held the SSE connection open AFTER [DONE], and the frontend
                # only re-enables the input when the stream actually closes — that was the
                # ~4-5s post-response lockout (P5). Run it in the background so the stream
                # closes immediately after the (fast, essential) message save and the user
                # can send their next message right away. The message itself is already
                # persisted above; only the best-effort memory_born thought-trace is
                # skipped on this connection as a result.
                if should_extract_memories(request.message, final_text):
                    asyncio.create_task(
                        extract_and_store_memories(
                            request.user_id, conv_id, request.message, final_text, sb
                        )
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

    # Confirmation is deterministic: the tool already returned the source of truth, and a
    # cosmetic rewrite is not worth a separate paid model request.
    confirmation_text = _make_fallback_confirmation(request.tool_name, result_data)

    # Persist the confirmation message to conversation history
    if request.conversation_id and request.user_id:
        sb = _get_supabase()
        if sb:
            try:
                await asyncio.to_thread(_save_assistant_message, sb, request.conversation_id, confirmation_text)
            except Exception as e:
                print(f"confirm-action: DB save error: {e}")

    return {
        "response": confirmation_text,
        "tool_result": result_data,
        # Tell the cockpit to refresh the embedded CRM after a confirmed write (e.g. delete).
        "crm_changed": request.tool_name in CRM_WRITE_ACTIONS and "error" not in result_data,
        # Tell the Leads cockpit to refresh its panel after a confirmed leads action.
        "leads_changed": request.tool_name in LEADS_CHANGED_ACTIONS and "error" not in result_data,
    }


def _make_fallback_confirmation(tool_name: str, result_data: dict) -> str:
    if "error" in result_data:
        return f"Action failed: {result_data['error']}"
    if tool_name.startswith("stripe__create"):
        mode = result_data.get("mode", "")
        mode_note = f" ({mode} mode)" if mode else ""
        price_id = result_data.get("price_id")
        product_id = result_data.get("product_id")
        if price_id and product_id:
            return f"Created on Stripe{mode_note}: product {product_id}, price {price_id}."
        if product_id:
            return f"Created Stripe product {product_id}{mode_note}."
    if result_data.get("status") == "deleted":
        return "Deleted successfully."
    if result_data.get("status") == "updated":
        agent_id = result_data.get("agent_id")
        return f"Updated agent {agent_id}." if agent_id else "Updated successfully."
    if result_data.get("status") == "created":
        agent_id = result_data.get("agent_id")
        name = result_data.get("name")
        if agent_id:
            return f'Created agent "{name}" ({agent_id}).'
        return "Created successfully."
    if result_data.get("status") == "sent":
        return "Sent successfully."
    if "event_id" in result_data:
        return f"Event created. Link: {result_data.get('link', 'N/A')}"
    return "Done."
