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
- "create": the user wants the assistant to BUILD, GENERATE, or DEPLOY something new (an AI agent, voice agent, campaign, landing page, website, workflow, etc.) — OR the message is a short confirmation ("yes", "yeah", "ok", "go ahead", "ship it", "deploy it", "do it", "sounds good") AND the assistant's last message was OFFERING to build, deploy, launch, or push something live.
- "show_me_how": the user's OWN current message explicitly asks the assistant to EXPLAIN or WALK THEM THROUGH how to do something THEMSELVES — a tutorial or steps for the user to follow. Questions starting with what/why/should/which/explain/tell me are NOT show_me_how. A bare confirmation ("yes"/"ok"/etc.) is NEVER show_me_how by itself, even if the assistant's last message offered to explain something.
- "chat": everything else — normal conversation, questions, requests to ADJUST/CHANGE/EDIT/TWEAK/FIX/UPDATE/REWRITE/SHORTEN/REGENERATE something that ALREADY EXISTS (an agent, its greeting, prompt, voice, persona, a message, a setting), confirmations that are NOT about a build/deploy offer, requests that need a tool (send an email, check a calendar, look up data, post to social), content the user is sharing/pasting for the assistant to remember/store/analyze, or ambiguous messages.

CRITICAL RULES:
1. A request to modify something that already exists is ALWAYS "chat", even if it uses words like "build", "create", "generate", or "regenerate" (e.g. "regenerate the agent's greeting to sound warmer" = chat, not create).
2. A bare confirmation ("yes"/"ok"/"sure"/"go ahead"/"please do") is "create" ONLY if the assistant's last message explicitly offered to build/deploy/launch/push live. In EVERY other case it is "chat" — including when the assistant offered to explain, walk through, or describe something. Example: assistant says "Want me to explain how the call-routing settings work?", user says "yes" -> "chat" (the assistant just explains in the chat reply), NOT "show_me_how".
3. If the message is the user pasting/sharing content (an article, notes, a long block of text) for the assistant to remember, store, analyze, or reference — that's "chat", regardless of words inside the pasted content.
4. "How do I get an agent built for my business" or similar is asking the assistant to DO it — that's "create", not show_me_how.

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
