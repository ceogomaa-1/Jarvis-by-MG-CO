"""
Single intent-classification call for Jarvis OS1 (Business) chat input.

Replaces the old frontend cascade of independent regex detectors
(agentEditDetector / showMeHowDetector / creationDetector / isDeployConfirmation)
with one context-aware call so that "adjust the agent's greeting" routes to
the chat/tool-calling flow instead of being misread as a tutorial or a new build.

Returns one of three flows for the frontend to dispatch on:
- "chat": regular chat/tool-calling turn (covers agent edits, questions,
  confirmations unrelated to a build/deploy offer, ambiguous messages).
- "show_me_how": user wants a step-by-step walkthrough they'll do themselves.
- "create": user wants Jarvis to build/generate/deploy something new, or is
  confirming a build/deploy Jarvis just offered.
"""
import json
import os

import httpx

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

VALID_INTENTS = {"chat", "show_me_how", "create"}

_CLASSIFY_PROMPT = """You are a routing classifier for a business assistant chat app. Decide which flow this message belongs to: "chat", "show_me_how", or "create".

DEFINITIONS:
- "create": the user explicitly wants the assistant to BUILD a multi-part DELIVERABLE from scratch — specifically a website, landing page, web page, marketing campaign, slide deck/presentation, or a long multi-section document. This is the heavy "produce an artifact" pipeline. It is ONLY for those build-a-deliverable asks (or a short confirmation like "yes"/"go ahead"/"build it" when the assistant's last message OFFERED to build one of those deliverables).
- "show_me_how": the user's OWN current message explicitly asks the assistant to EXPLAIN or WALK THEM THROUGH how to do something THEMSELVES — a tutorial or steps for the user to follow. Questions starting with what/why/should/which/explain/tell me are NOT show_me_how. A bare confirmation ("yes"/"ok"/etc.) is NEVER show_me_how by itself.
- "chat": EVERYTHING ELSE, and this is the default. It covers: normal conversation and questions; requests to USE A CONNECTED TOOL or PERFORM AN ACTION (create products/prices on Stripe, send an email, draft/schedule an email, check a calendar, book a meeting, add/scan CRM contacts, look up data, post to social, run SQL, create an AI/voice agent); requests to ADJUST/CHANGE/EDIT/TWEAK/FIX/UPDATE/REWRITE/SHORTEN/REGENERATE something that ALREADY EXISTS; planning/advice asks ("plan my pricing tiers", "what should I charge"); content the user is sharing/pasting to remember/store/analyze; confirmations that are NOT about a build-a-deliverable offer; and anything ambiguous.

CRITICAL RULES:
1. A request to USE A TOOL or TAKE AN ACTION is ALWAYS "chat", even when it says "create", "set up", "add", or "make" — because the assistant performs it by calling a tool, not by running the deliverable builder. Examples: "create a Pro product at $249/mo on Stripe" = chat; "set up these pricing tiers in Stripe" = chat; "add a contact to my CRM" = chat; "send this email" = chat; "scan my CRM for stale leads" = chat. The word "create" does NOT imply the "create" flow.
2. "create" is reserved for building a website / landing page / deck / campaign / multi-section document. "Plan my pricing" or "create the tiers on Stripe" is NOT a build-a-deliverable request — it's "chat".
3. A request to modify something that already exists is ALWAYS "chat", even with words like "build"/"create"/"regenerate" (e.g. "regenerate the agent's greeting to sound warmer" = chat).
4. A bare confirmation ("yes"/"ok"/"sure"/"go ahead"/"do it") is "create" ONLY if the assistant's last message explicitly offered to build/deploy one of those deliverables. Otherwise it is "chat" — including when the assistant offered to explain or to perform a tool action. Example: assistant "Want me to create these two tiers on Stripe?", user "yes" -> "chat" (the assistant performs the tool action), NOT "create".
5. If the message is the user pasting/sharing content for the assistant to remember/store/analyze/reference — that's "chat", regardless of words inside the pasted content.
6. When genuinely unsure between "create" and "chat", choose "chat" (the assistant can ask one clarifying question rather than spinning up the heavy builder).

CONTEXT:
{context}

USER MESSAGE:
\"\"\"{message}\"\"\"

Respond with ONLY a compact JSON object, no markdown, no explanation:
{{"intent": "chat" | "show_me_how" | "create", "reason": "<one short phrase>"}}"""


async def classify_message_intent(
    message: str,
    *,
    active_agent_id: str | None = None,
    recent_assistant_texts: list[str] | None = None,
    has_attachments: bool = False,
) -> dict:
    """
    Classify a Business chat message into "chat" / "show_me_how" / "create".

    Deterministic short-circuits (no model call):
    - attachments present -> "chat" (existing behavior — attachments always go
      through the regular chat/tool flow so the model can see them)
    - empty message -> "chat"
    """
    text = (message or "").strip()
    if has_attachments or not text:
        return {"intent": "chat", "reason": "attachments-or-empty"}

    context_lines = []
    if active_agent_id:
        context_lines.append(f"- There IS an active agent in this conversation (id: {active_agent_id}). Requests to adjust/change \"the agent\" refer to this one.")
    else:
        context_lines.append("- There is no active agent in this conversation yet.")

    if recent_assistant_texts:
        last = recent_assistant_texts[-1][:600]
        context_lines.append(f"- The assistant's last message was:\n  \"{last}\"")
    else:
        context_lines.append("- The assistant has not said anything yet in this conversation.")

    prompt = _CLASSIFY_PROMPT.format(context="\n".join(context_lines), message=text)

    if not ANTHROPIC_API_KEY:
        return {"intent": "chat", "reason": "no-api-key"}

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
                    "max_tokens": 80,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=8.0,
            )
        if resp.status_code == 200:
            raw = resp.json().get("content", [{}])[0].get("text", "").strip()
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.strip("`")
                if raw.startswith("json"):
                    raw = raw[4:]
            data = json.loads(raw)
            intent = data.get("intent")
            if intent in VALID_INTENTS:
                return {"intent": intent, "reason": str(data.get("reason", ""))[:200]}
        print(f"INTENT_ROUTER: unexpected response status={resp.status_code} body={resp.text[:200]}")
    except Exception as e:
        print(f"INTENT_ROUTER: classification error: {e}")

    return {"intent": "chat", "reason": "fallback-default"}
