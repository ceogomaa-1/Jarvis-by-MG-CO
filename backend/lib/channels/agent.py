"""Run ONE OS1 business turn for a messaging channel — non-streaming.

This is the same OS1 brain the web app uses (same system prompt, same tools, same model
routing, same entitlements/usage/trial enforcement), collapsed into a single request→reply
call suitable for Telegram/WhatsApp. Differences vs. the web path, by design:

  • Conversational only — there's no cockpit, so write/confirm-gated actions are DEFERRED with
    a nudge to the web app (read tools, web research, lookups all run normally).
  • Output is collected into one text reply (chunked by the channel adapter), not streamed.

Personal and the web SSE path are untouched; this module reuses their building blocks.
"""
import asyncio
import base64
import os

import httpx

from backend.lib.business.system_prompt_builder import build_system_prompt
from backend.lib.business.tool_builder import build_tools_for_user
from backend.lib.business.tool_executor import execute_tool
from backend.lib.business.model_router import select_model, HAIKU
from backend.lib.business.cost import UsageAccumulator
from backend.lib.business.prompt_budget import (
    cap_dynamic_prompt,
    cap_tool_result,
    chat_output_token_budget,
    trim_history,
)
from backend.lib.billing import entitlements, config as billing_config, store as billing_store
from backend.usage_limits import check_limit, increment_usage, DAILY_MESSAGE_LIMIT
# Single source of truth for which tools require hold-to-confirm in the web app.
from backend.routes.business.chat import WRITE_ACTIONS

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
SUPABASE_URL = os.getenv("NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

MAX_TOOL_ROUNDS = 5


def _supabase():
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    from supabase import create_client
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def _build_content(text: str, attachments: list):
    """Anthropic user-content blocks for a channel turn (images / PDFs / text files)."""
    if not attachments:
        return text or "(no text)"
    blocks: list = []
    for att in attachments[:5]:
        mt = att.get("media_type", "") or ""
        if att.get("type") == "image" or mt.startswith("image/"):
            blocks.append({"type": "image", "source": {
                "type": "base64", "media_type": mt or "image/jpeg", "data": att["data"]}})
        elif mt == "application/pdf" or att.get("type") == "document":
            blocks.append({"type": "document", "source": {
                "type": "base64", "media_type": "application/pdf", "data": att["data"]}})
        else:
            try:
                decoded = base64.b64decode(att["data"]).decode("utf-8", errors="replace")
                blocks.append({"type": "text", "text": f"[File: {att.get('name', 'file')}]\n{decoded[:8000]}"})
            except Exception:
                pass
    blocks.append({"type": "text", "text": text or "(the user sent an attachment with no caption)"})
    return blocks


def _deferral_message(tool_name: str) -> str:
    pretty = tool_name.replace("__", " → ").replace("_", " ")
    return (
        f"That action ({pretty}) changes your data and needs hold-to-confirm, which only the "
        f"web app has. Open jarvismgco.com/os1 to approve it. I can still answer questions, "
        f"research, and look things up for you right here."
    )


async def run_channel_turn(user_id: str, text: str, attachments: list = None,
                           history: list = None) -> dict:
    """Execute one OS1 turn. Returns {"reply": str, "ok": bool, "kind": str}.

    kind ∈ {"reply","limit","trial_limit","deferred","error"} for the caller's telemetry.
    """
    attachments = attachments or []
    history = history or []

    # ── Entitlements: tier multiplier, trial cost ceiling, trial cost-control ──────────────
    is_trial = False
    usage_multiplier = 1
    try:
        caps = await asyncio.to_thread(entitlements.for_user, user_id)
        is_trial = caps.get("plan") == "trial"
        usage_multiplier = caps.get("usage_multiplier") or 1
        if usage_multiplier < 1:
            usage_multiplier = 1
    except Exception as e:
        print(f"[CHANNELS] entitlements error: {e}")

    if is_trial:
        try:
            tc = await asyncio.to_thread(entitlements.trial_cost_status, user_id)
            if tc.get("exceeded"):
                return {"ok": False, "kind": "trial_limit", "reply": (
                    "Your free trial limit is reached — pick a plan at jarvismgco.com/os1 to "
                    "keep going. You've seen what Jarvis can do; upgrade to unlock the full "
                    "experience with no cap."
                )}
        except Exception:
            pass

    sb = _supabase()
    effective_limit = DAILY_MESSAGE_LIMIT * usage_multiplier
    if sb:
        try:
            allowed, info = await asyncio.to_thread(check_limit, user_id, sb, effective_limit)
            if not allowed:
                window = info.get("window_label", "4 hours")
                resets = info.get("resets_in", "soon")
                return {"ok": False, "kind": "limit", "reply": (
                    f"You've hit your limit for now — {info.get('limit', effective_limit)} "
                    f"messages per {window}. Your next slot opens in {resets}."
                )}
        except Exception as e:
            print(f"[CHANNELS] limit check error: {e}")

    # ── Build the turn (trials get the cheap model + bounded input/output) ─────────────────
    turn_text = text or ""
    if is_trial:
        turn_text = turn_text[: billing_config.TRIAL_CONTEXT_CHAR_CAP]
        attachments = []  # trials stay text-only to bound cost
        per_turn = max(1000, billing_config.TRIAL_CONTEXT_CHAR_CAP // 6)
        history = [{"role": m["role"], "content": str(m.get("content", ""))[:per_turn]}
                   for m in history[-6:]]

    static_prompt, dynamic_prompt, _used = await build_system_prompt(user_id, turn_text)
    dynamic_prompt = cap_dynamic_prompt(dynamic_prompt)
    tools = await build_tools_for_user(user_id)

    system_blocks = [{"type": "text", "text": static_prompt, "cache_control": {"type": "ephemeral"}}]
    if dynamic_prompt:
        system_blocks.append({"type": "text", "text": dynamic_prompt})
    if tools:
        tools = list(tools)
        tools[-1] = {**tools[-1], "cache_control": {"type": "ephemeral"}}

    safe_history = trim_history(history)
    user_content = _build_content(turn_text, attachments)
    messages = safe_history + [{"role": "user", "content": user_content}]

    model = HAIKU if is_trial else select_model(turn_text, has_attachments=bool(attachments))
    max_tokens = (
        billing_config.TRIAL_MAX_TOKENS if is_trial else chat_output_token_budget(model)
    )
    usage_acc = UsageAccumulator(model)

    final_text = ""
    kind = "reply"
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            for _round in range(MAX_TOOL_ROUNDS):
                body = {
                    "model": model,
                    "max_tokens": max_tokens,
                    "system": system_blocks,
                    "messages": messages,
                    "cache_control": {"type": "ephemeral"},
                }
                if tools:
                    body["tools"] = tools
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": ANTHROPIC_API_KEY,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json=body,
                )
                if resp.status_code != 200:
                    print(f"[CHANNELS] Anthropic error {resp.status_code}: {resp.text[:300]}")
                    return {"ok": False, "kind": "error",
                            "reply": "I hit a snag reaching the AI. Please try again in a moment."}
                data = resp.json()
                usage = data.get("usage", {}) or {}
                usage_acc.add_message_start(usage)
                usage_acc.add_round_output(usage.get("output_tokens") or 0)

                content_blocks = data.get("content", []) or []
                stop_reason = data.get("stop_reason", "end_turn")
                round_text = "".join(
                    b.get("text", "") for b in content_blocks if b.get("type") == "text"
                )
                if round_text:
                    final_text = (final_text + "\n\n" + round_text).strip() if final_text else round_text

                if stop_reason != "tool_use":
                    break

                tool_uses = [b for b in content_blocks if b.get("type") == "tool_use"]

                # Conversational channel: defer any write/confirm-gated action to the web app.
                write_block = next((b for b in tool_uses if b["name"] in WRITE_ACTIONS), None)
                if write_block:
                    note = _deferral_message(write_block["name"])
                    final_text = (final_text + "\n\n" + note).strip() if final_text else note
                    kind = "deferred"
                    break

                messages.append({"role": "assistant", "content": content_blocks})
                async def _run_read_tool(tb: dict) -> dict:
                    result_str = await execute_tool(tb["name"], tb.get("input", {}), user_id)
                    return {
                        "type": "tool_result",
                        "tool_use_id": tb["id"],
                        "content": cap_tool_result(result_str),
                    }

                tool_results = list(await asyncio.gather(
                    *(_run_read_tool(tb) for tb in tool_uses)
                ))
                messages.append({"role": "user", "content": tool_results})
            else:
                # Exhausted tool rounds without a final text answer.
                if not final_text:
                    final_text = "I hit a processing limit on that one. Try asking it more simply."
    except Exception as e:
        import traceback
        print(f"[CHANNELS] run error: {e}")
        traceback.print_exc()
        return {"ok": False, "kind": "error",
                "reply": "Something went wrong handling that. Please try again."}

    # ── Meter: count this turn against the tier window + trial cost ledger ─────────────────
    try:
        print(usage_acc.log_line())
    except Exception:
        pass
    if sb:
        try:
            await asyncio.to_thread(increment_usage, user_id, sb, effective_limit)
        except Exception as e:
            print(f"[CHANNELS] increment error: {e}")
    if is_trial:
        try:
            await asyncio.to_thread(billing_store.add_trial_cost, user_id,
                                    usage_acc.cost().get("total_usd", 0.0))
        except Exception:
            pass

    return {"ok": True, "kind": kind, "reply": final_text or "…"}
