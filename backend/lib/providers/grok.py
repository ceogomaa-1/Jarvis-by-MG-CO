"""
xAI Grok backend for Study Mode (OpenAI-compatible Chat Completions).

`grok_think()` mirrors `backend.llm.jarvis_think()`'s contract exactly — same
arguments, returns the final answer as a string (the Study route fake-streams it
char-by-char, so no SSE translation is needed). It builds the SAME system prompt
and tool set as the Claude path (we swap the brain, not the persona), then
translates to/from xAI's OpenAI-style format:

  - Anthropic tool defs  → OpenAI `tools` (function schema)
  - Anthropic content     → OpenAI messages (text + image_url for vision)
  - OpenAI `tool_calls`   → executed via the SAME tool registry as Claude
  - tool results          → OpenAI `tool` messages

Nothing here touches the Claude code path. If anything goes wrong, the caller
falls back to Claude.
"""
import inspect
import json
import os

import httpx

# xAI is OpenAI-compatible. Defaults are overridable via env so nothing is
# hard-locked. grok-4.3 is xAI's current flagship (1M context, text+image,
# strong tool-calling) — the right pick for a vision-capable tutor.
GROK_BASE_URL = os.getenv("GROK_BASE_URL", "https://api.x.ai/v1")
GROK_MODEL = os.getenv("GROK_MODEL", "grok-4.3")

# Per-1M-token pricing (USD) for the cost log. Approximate, env-overridable via the
# model default above; unknown models fall back to grok-4.3 rates.
_GROK_PRICING: dict[str, tuple[float, float]] = {
    "grok-4.3": (1.25, 2.50),
    "grok-4-fast": (0.20, 0.50),
    "grok-code-fast-1": (0.20, 1.50),
}
_GROK_FALLBACK_RATES = (1.25, 2.50)

_MAX_TOOL_ROUNDS = 5  # mirrors jarvis_think's cap


def _rates(model: str) -> tuple[float, float]:
    for prefix, rates in _GROK_PRICING.items():
        if model.startswith(prefix):
            return rates
    return _GROK_FALLBACK_RATES


def _to_openai_tools(tools: list | None) -> list:
    """Anthropic tool defs → OpenAI function tools."""
    out = []
    for t in tools or []:
        out.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
            },
        })
    return out


def _to_openai_content(user_message):
    """Anthropic user content (str or block list) → OpenAI message content.

    Handles vision: base64 image blocks become OpenAI image_url data URIs so a
    student's textbook photos work the same as on Claude.
    """
    if isinstance(user_message, str):
        return user_message
    parts: list = []
    for b in user_message or []:
        btype = b.get("type")
        if btype == "text":
            parts.append({"type": "text", "text": b.get("text", "")})
        elif btype == "image":
            src = b.get("source", {})
            if src.get("type") == "base64":
                mt = src.get("media_type", "image/jpeg")
                data = src.get("data", "")
                parts.append({"type": "image_url", "image_url": {"url": f"data:{mt};base64,{data}"}})
        elif btype == "document":
            # Inline PDFs aren't supported the same way here; note it rather than drop silently.
            parts.append({"type": "text", "text": "[a PDF was attached but this brain can't read it inline]"})
    return parts or ""


def _to_openai_messages(system_prompt: str, history: list, user_message) -> list:
    msgs: list = [{"role": "system", "content": system_prompt}]
    for m in history or []:
        c = m.get("content")
        role = m.get("role", "user")
        if isinstance(c, str) and c.strip() and role in ("user", "assistant"):
            msgs.append({"role": role, "content": c})
    msgs.append({"role": "user", "content": _to_openai_content(user_message)})
    return msgs


async def _execute_tool_call(name: str, args: dict, user_id: str) -> str:
    """Run a tool the same way jarvis_think does — registry first, legacy fallback."""
    from backend.agent import execute_tool
    from backend.tools.registry import TOOL_REGISTRY
    try:
        if name in TOOL_REGISTRY:
            fn = TOOL_REGISTRY[name]["execute"]
            call_kwargs = {k: v for k, v in (args or {}).items() if k != "user_id"}
            if user_id and "user_id" in inspect.signature(fn).parameters:
                call_kwargs["user_id"] = user_id
            print(f"GROK_TOOL_CALL: {name}({call_kwargs})")
            return str(await fn(**call_kwargs))
        print(f"GROK_TOOL_CALL (legacy): {name}({args})")
        return str(await execute_tool(user_id, name, args))
    except Exception as exc:
        print(f"GROK_TOOL_ERROR: {name} → {exc}")
        return f"The {name} tool hit an error and couldn't complete: {exc}"


def _build_personal_prompt_and_tools(
    memory_context, user_model_context, system_override, tone_context,
    live_context, voice_mode, user_id, available_tools, all_tools, moment_block,
):
    """Assemble the SAME system prompt the Claude path uses (faithful mirror of
    jarvis_think's assembly), so the only variable in the A/B is the brain."""
    from backend.llm import _build_system_prompt
    from backend.lib.grounding import render_capability_manifest

    system_prompt = _build_system_prompt(
        memory_context, user_model_context, system_override, tone_context,
        live_context, moment_block=moment_block, voice_mode=voice_mode, user_id=user_id,
    )
    if not system_override:
        system_prompt = "YOU ARE NOT IN ONBOARDING MODE. ALL TOOLS ARE ACTIVE. CALL THEM WITHOUT HESITATION.\n\n" + system_prompt
        if available_tools:
            try:
                _tool_names = sorted({t["name"] for t in all_tools})
                _can_do = []
                if any("search" in n for n in _tool_names):
                    _can_do.append("Search the live web and read pages for current facts (news, scores, prices, weather, lookups)")
                _can_do.append("Tools available this turn: " + ", ".join(_tool_names))
                _cannot_do = [
                    "Act on Business services like Stripe, a CRM, social publishing, or website deploys — that's Jarvis OS1 (Business mode), not Personal.",
                ]
                system_prompt += "\n\n" + render_capability_manifest(_can_do, [], _cannot_do)
            except Exception as _manifest_err:
                print(f"GROK_MANIFEST: skipped ({_manifest_err})")
    return system_prompt


async def grok_think(
    user_message,
    conversation_history: list,
    memory_context: str = "",
    user_model_context: str = "",
    system_override: str | None = None,
    available_tools: list | None = None,
    tone_context: str = "",
    user_id: str = "",
    live_context: str = "",
    voice_mode: bool = False,
) -> str:
    """Study Mode answer from Grok. Same signature/return as jarvis_think."""
    api_key = (os.getenv("GROK_API_KEY") or "").strip()
    if not api_key:
        # Should never reach here (resolver gates on this), but be explicit.
        raise RuntimeError("GROK_API_KEY not set")

    # Same tool set as the Claude path.
    from backend.agent import ANTHROPIC_TOOLS
    from backend.tools.registry import get_tools_for_claude
    from backend.llm import get_current_moment_block

    registry_names = {t["name"] for t in get_tools_for_claude()}
    all_tools = (
        [t for t in ANTHROPIC_TOOLS if t["name"] not in registry_names]
        + get_tools_for_claude()
    )

    moment_block = await get_current_moment_block(user_id)
    system_prompt = _build_personal_prompt_and_tools(
        memory_context, user_model_context, system_override, tone_context,
        live_context, voice_mode, user_id, available_tools, all_tools, moment_block,
    )

    messages = _to_openai_messages(system_prompt, conversation_history, user_message)
    oai_tools = _to_openai_tools(all_tools) if available_tools else None

    in_tokens = out_tokens = 0
    final_text = ""

    async with httpx.AsyncClient(timeout=90.0) as client:
        for _round in range(_MAX_TOOL_ROUNDS + 1):
            payload: dict = {"model": GROK_MODEL, "max_tokens": 1024, "messages": messages}
            if oai_tools:
                payload["tools"] = oai_tools

            resp = await client.post(
                f"{GROK_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"xAI {resp.status_code}: {resp.text[:300]}")
            data = resp.json()

            usage = data.get("usage") or {}
            in_tokens += int(usage.get("prompt_tokens") or 0)
            out_tokens += int(usage.get("completion_tokens") or 0)

            choice = (data.get("choices") or [{}])[0].get("message", {})
            final_text = choice.get("content") or final_text
            tool_calls = choice.get("tool_calls")

            if not tool_calls:
                break

            # Echo the assistant turn (with its tool_calls) then append each result.
            messages.append({
                "role": "assistant",
                "content": choice.get("content") or "",
                "tool_calls": tool_calls,
            })
            for tc in tool_calls:
                fn = tc.get("function", {})
                name = fn.get("name", "")
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except Exception:
                    args = {}
                result = await _execute_tool_call(name, args, user_id)
                messages.append({"role": "tool", "tool_call_id": tc.get("id"), "content": result})

    # ── Cost/feel visibility (log-only) ──
    in_rate, out_rate = _rates(GROK_MODEL)
    cost = in_tokens / 1_000_000 * in_rate + out_tokens / 1_000_000 * out_rate
    print(
        f"[STUDY_COST] provider=grok model={GROK_MODEL} "
        f"in={in_tokens} out={out_tokens} => ${cost:.4f}"
    )

    return final_text
