"""
Rue GO (Batch 70) — website creation + walkthroughs as chat-callable tools.

Wraps the EXISTING, tested generators (does not reimplement them) so the brain
can invoke them mid-conversation via the normal tool-calling loop, instead of
only being reachable when the classify-intent pre-router decides to send the
user to a separate endpoint. See backend/routes/business/create.py for the
underlying build/edit logic and backend/lib/business/walkthrough_generator.py
for the walkthrough generator — both are reused as-is.

Deploy intentionally stays OUT of this module and on the legacy
/business/create SSE path (the DIRECT_DEPLOY_RE shortcut in ChatCanvas.js,
left active in Rue GO mode): that pipeline is multi-stage, takes real time,
and already streams its own progress/polling UI. Folding it into a single
tool-call/tool-result round-trip would be a UX regression, not an improvement.
"""
from types import SimpleNamespace

from backend.lib.business.system_prompt_builder import _fetch_user_profile
from backend.lib.business.walkthrough_generator import generate_walkthrough


def _build_context(user_id: str) -> dict:
    profile = _fetch_user_profile(user_id) if user_id else {}
    return {
        "user_id": user_id,
        "industry": profile.get("industry", ""),
        "company_name": profile.get("company_name", ""),
        "role": profile.get("role", ""),
    }


def _stage_message(payload: dict) -> str | None:
    t = payload.get("type")
    if t == "creation_stage":
        return payload.get("message")
    if t == "agent_status" and payload.get("status") == "started":
        return "Designing…"
    return None


async def run_website_create(tool_input: dict, user_id: str, progress_cb=None) -> dict:
    """website__create tool — build a new standalone page, or edit the last saved one."""
    # Imported lazily to avoid a circular import (create.py imports tool_builder indirectly
    # via the route graph; chat_tools.py is only imported from tool_executor.py at call time).
    from backend.routes.business.create import _run_standalone_build, _run_standalone_edit

    action = (tool_input.get("action") or "build").strip().lower()
    brief = (tool_input.get("brief") or "").strip()
    if not brief:
        return {"error": "I need a description of what to build or change."}

    context = _build_context(user_id)
    request = SimpleNamespace(message=brief, user_id=user_id, conversation_id=None)

    handler = (
        _run_standalone_edit(request, context)
        if action == "edit"
        else _run_standalone_build(request, context, None)
    )

    artifact = None
    note = ""
    async for kind, payload in handler:
        if kind == "event":
            if payload.get("type") == "error":
                return {"error": payload.get("value") or "Build failed."}
            if payload.get("type") == "html_artifact":
                artifact = payload
            elif progress_cb:
                stage = _stage_message(payload)
                if stage:
                    await progress_cb(stage)
        elif kind == "chat_message":
            note = payload

    if not artifact:
        return {"error": "No website was produced — nothing was saved."}

    return {
        "ok": True,
        "render_as": "creation",
        "creation_id": artifact.get("creation_id"),
        "title": artifact.get("title", ""),
        "summary": artifact.get("summary", ""),
        "html": artifact.get("html", ""),
        "deployment_status": artifact.get("deployment_status"),
        "live_url": artifact.get("live_url"),
        "message": note or f"Built {artifact.get('title') or 'the page'}.",
    }


async def run_walkthrough(tool_input: dict, user_id: str, progress_cb=None) -> dict:
    """walkthrough__generate tool — step-by-step illustrated tutorial."""
    topic = (tool_input.get("topic") or "").strip()
    if not topic:
        return {"error": "What should the walkthrough cover?"}

    if progress_cb:
        await progress_cb("Building the walkthrough…")

    walkthrough = await generate_walkthrough(topic)
    if not walkthrough or not walkthrough.get("steps"):
        return {"error": "Could not generate a walkthrough for that. Try rephrasing it."}

    return {
        "ok": True,
        "render_as": "walkthrough",
        "title": walkthrough.get("title", ""),
        "intro": walkthrough.get("intro", ""),
        "steps": walkthrough.get("steps", []),
        "sources": walkthrough.get("sources", []),
        "message": f"Here's the walkthrough: {walkthrough.get('title') or topic}.",
    }
