import asyncio
import json
import os
import re
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from supabase import create_client

from backend.lib.business.connectors.registry import list_user_connections
from backend.lib.business.connectors.registry import get_connector_for_user
from backend.lib.business.creation.deploy_pipeline import run_deploy_pipeline
from backend.lib.business.creation.deployment_phase import deploy_project_after_creation
from backend.lib.business.creation.orchestrator import orchestrate_creation
from backend.lib.business.creation.persistence import (
    complete_creation_row,
    create_creation_row,
    fail_creation_row,
    mark_deployment_pending,
    update_deployment_by_id,
)
from backend.lib.business.creation.site_generator import generate_site
from backend.lib.business.system_prompt_builder import _fetch_user_profile

router = APIRouter()

_WEBSITE_BUILD_RE = re.compile(
    r"\b(website|web\s*site|web\s*page|webpage|landing\s*page)\b"
    r"|build\s+(me\s+)?(a\s+)?(site|web)"
    r"|create\s+(a\s+)?(site|web)",
    re.IGNORECASE,
)
# Matches memory/ingest intents — user is sharing reference material, not requesting creation.
# Mirror of INGEST_BLOCKLIST in frontend/lib/business/creationDetector.js.
_INGEST_RE = re.compile(
    r"\b(remember|memorize|save\s+(this|it)|keep\s+(this|it)|store\s+(this|it)|take\s+note)\b"
    r"|\bfor\s+(your\s+)?(memory|reference|records|knowledge)\b"
    r"|\b(bury|file|log)\s+(this|it)\b"
    r"|\bhere'?s\s+(the|our|my)\s+(bible|info|knowledge|details|company|background|context)\b"
    r"|\b(knowledge\s+base|master\s+(document|guide|playbook)|table\s+of\s+contents)\b"
    r"|\bfyi[\s,:]|\bnote\s+this\b|\blearn\s+this\b",
    re.IGNORECASE,
)
_DEPLOY_CONFIRM_RE = re.compile(
    r"^\s*(yes|yeah|yep|please|yes please|do it|go ahead|ship it|deploy it|deploy|push it|"
    r"launch it|make it live|sounds good|ok|okay|sure)\s*[.!?]*\s*$",
    re.IGNORECASE,
)
_DEPLOY_OFFER_RE = re.compile(
    r"(github\s*\+\s*vercel|vercel.*github|github.*vercel|trigger live url|live url generation|"
    r"push all files|spawn a sub-agent.*deploy|deployment)",
    re.IGNORECASE | re.DOTALL,
)


def _is_website_build(message: str) -> bool:
    if not message:
        return False
    # Memory/ingest intents are never website builds — user is sharing reference material
    if _INGEST_RE.search(message):
        return False
    # Long messages (>600 chars or >6 line-breaks) are likely pasted docs.
    # Only treat as a website build when the trigger appears on the very first line.
    if len(message) > 600 or message.count("\n") > 6:
        first_line = message.split("\n")[0][:120]
        return bool(_WEBSITE_BUILD_RE.search(first_line))
    return bool(_WEBSITE_BUILD_RE.search(message))


def _is_deploy_confirmation(message: str) -> bool:
    return bool(_DEPLOY_CONFIRM_RE.search(message or ""))

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


def _ensure_conversation(sb, user_id: str, conv_id: str | None, message: str) -> tuple[str | None, bool]:
    """Create conversation if needed and save user message. Returns (conv_id, is_new)."""
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


def _save_message(sb, conv_id: str, content: str) -> str | None:
    """Save assistant message. Returns message ID."""
    res = sb.table("business_messages").insert({
        "conversation_id": conv_id,
        "role": "assistant",
        "content": content,
    }).execute()
    sb.table("business_conversations").update({
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", conv_id).execute()
    return res.data[0]["id"] if res.data else None


def _update_message(sb, message_id: str, content: str) -> None:
    sb.table("business_messages").update({
        "content": content,
    }).eq("id", message_id).execute()


def _load_deploy_confirmation_artifact(sb, user_id: str, conv_id: str | None) -> str:
    """Find the recent assistant artifact that offered GitHub + Vercel deployment."""
    if not sb or not user_id or not conv_id:
        return ""
    user_uuid = _user_id_to_uuid(user_id)
    conv = (
        sb.table("business_conversations")
        .select("id")
        .eq("id", conv_id)
        .eq("user_id", user_uuid)
        .maybe_single()
        .execute()
    )
    if not conv.data:
        return ""
    msgs = (
        sb.table("business_messages")
        .select("role, content, created_at")
        .eq("conversation_id", conv_id)
        .order("created_at", desc=True)
        .limit(8)
        .execute()
    )
    for msg in msgs.data or []:
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content") or ""
        if _DEPLOY_OFFER_RE.search(content):
            return content
    return ""


async def _collect_deploy_events(user_id: str, deploy_content: str, user_message: str) -> list[dict]:
    """Collect all deployment SSE events into a list (enables timeout wrapping)."""
    events = []
    async for ev in deploy_project_after_creation(
        user_id=user_id,
        artifact_markdown=deploy_content,
        user_message=user_message,
    ):
        events.append(ev)
    return events


async def _await_with_status(coro, status_message: str, interval: float = 8.0):
    """Run a slow coroutine while keeping the SSE stream alive with status events."""
    task = asyncio.create_task(coro)
    elapsed = 0
    while not task.done():
        await asyncio.sleep(interval)
        elapsed += int(interval)
        if not task.done():
            yield {
                "type": "deployment_status",
                "message": f"{status_message} ({elapsed}s elapsed)",
            }
    yield await task


class CreateRequest(BaseModel):
    message: str
    user_id: str = ""
    conversation_id: str | None = None


@router.get("/business/deploy-status")
async def business_deploy_status(user_id: str = "", deployment_id: str = ""):
    if not user_id or not deployment_id:
        return {"state": "ERROR", "url": None, "error": "user_id and deployment_id are required", "logs": None}

    vc = await get_connector_for_user(user_id, "vercel")
    if not vc:
        return {"state": "ERROR", "url": None, "error": "Vercel connector not connected", "logs": None}

    status_res = await vc.get_deployment(deployment_id)
    if not status_res.ok:
        return {"state": "BUILDING", "url": None, "error": status_res.error, "logs": None}

    state = status_res.data.get("readyState") or "BUILDING"
    url = status_res.data.get("alias") or status_res.data.get("url")
    error = status_res.data.get("error_message")
    logs = None

    if state in ("ERROR", "FAILED", "CANCELED"):
        logs = await vc.get_deployment_build_logs(deployment_id)
        error = error or f"Vercel deployment ended with state {state}"

    if state == "READY" and url:
        await update_deployment_by_id(deployment_id, "READY", live_url=url)
    elif state in ("ERROR", "FAILED", "CANCELED"):
        await update_deployment_by_id(deployment_id, state, error=logs or error)
    else:
        await update_deployment_by_id(deployment_id, state)

    return {"state": state, "url": url if state == "READY" else None, "error": error, "logs": logs}


@router.post("/business/create")
async def business_create(request: CreateRequest):
    """Stream a Creation 1.0 sub-agent orchestration with persistence."""
    profile = _fetch_user_profile(request.user_id) if request.user_id else {}

    # Detect deploy connectors upfront so sub-agents can suppress code from chat output
    has_deploy_connectors = False
    if request.user_id:
        try:
            connections = await list_user_connections(request.user_id)
            active_types = {c["connector_type"] for c in connections if c.get("status") == "active"}
            has_deploy_connectors = "github" in active_types and "vercel" in active_types
        except Exception:
            pass

    context = {
        "user_id": request.user_id,
        "industry": profile.get("industry", ""),
        "company_name": profile.get("company_name", ""),
        "role": profile.get("role", ""),
        "has_deploy_connectors": has_deploy_connectors,
    }

    async def generate():
        creation_id = None
        artifact = ""
        code_for_deployment = ""
        has_error = False
        error_msg = ""
        conv_id = request.conversation_id
        saved_msg_id: str | None = None

        try:
            # Immediate signal so UI shows activity during the 2-4s planning gap
            yield f'data: {json.dumps({"type": "status", "value": "spinning up"})}\n\n'

            if _is_deploy_confirmation(request.message) and has_deploy_connectors:
                try:
                    sb = _get_supabase()
                    previous_artifact = ""
                    if sb:
                        conv_id, is_new = await asyncio.to_thread(
                            _ensure_conversation, sb, request.user_id, conv_id, request.message
                        )
                        if conv_id and is_new:
                            yield f'data: {json.dumps({"type": "conv_id", "value": conv_id})}\n\n'
                        previous_artifact = await asyncio.to_thread(
                            _load_deploy_confirmation_artifact, sb, request.user_id, conv_id
                        )

                    if not previous_artifact:
                        yield f'data: {json.dumps({"type": "deployment_error", "value": "I could not find the previous website artifact to deploy. Send the website request again or say exactly what site to build."})}\n\n'
                        yield "data: [DONE]\n\n"
                        return

                    deploy_plan = [
                        {"id": "a1", "role": "designer", "task": "Generate the deployable Next.js website codebase from the approved website brief."},
                        {"id": "a2", "role": "publisher", "task": "Push the generated files to GitHub and trigger a Vercel production build."},
                    ]
                    creation_id = await create_creation_row(
                        user_id=request.user_id,
                        title="Website Deployment",
                        intro="Deploying the approved website to GitHub and Vercel.",
                        user_message=request.message,
                        plan=deploy_plan,
                        industry=context.get("industry", ""),
                        company_name=context.get("company_name", ""),
                    )
                    if creation_id:
                        yield f'data: {json.dumps({"type": "creation_id", "id": creation_id})}\n\n'
                    yield f'data: {json.dumps({"type": "plan", "title": "Website Deployment", "intro": "Deploying the approved website to GitHub and Vercel.", "agents": deploy_plan})}\n\n'
                    yield f'data: {json.dumps({"type": "agent_status", "id": "a1", "status": "started"})}\n\n'
                    yield f'data: {json.dumps({"type": "deployment_status", "message": "Generating Next.js codebase from the approved website brief…"})}\n\n'

                    site = None
                    site_prompt = f"Deploy this approved website brief as a production Next.js site.\n\nUser confirmation: {request.message}"
                    async for result in _await_with_status(
                        generate_site(site_prompt, {**context, "artifact": previous_artifact}),
                        "Still generating the Next.js codebase…",
                    ):
                        if isinstance(result, dict) and "files" in result:
                            site = result
                        else:
                            yield f"data: {json.dumps(result)}\n\n"

                    if not site:
                        raise RuntimeError("site generator returned no files")

                    await complete_creation_row(creation_id, previous_artifact) if creation_id else None
                    yield f'data: {json.dumps({"type": "agent_status", "id": "a1", "status": "complete"})}\n\n'
                    yield f'data: {json.dumps({"type": "artifact", "format": "markdown", "content": previous_artifact})}\n\n'
                    yield f'data: {json.dumps({"type": "complete"})}\n\n'
                    yield f'data: {json.dumps({"type": "agent_status", "id": "a2", "status": "started"})}\n\n'
                    if site.get("is_fallback"):
                        fallback_notice = (
                            "The custom build step hit an issue, so I deployed a clean generic "
                            "starter instead, it will not match the design brief above. "
                            "Say \"rebuild the site\" to retry the custom version."
                        )
                        yield f'data: {json.dumps({"type": "deployment_status", "message": fallback_notice})}\n\n'
                    yield f'data: {json.dumps({"type": "deployment_status", "message": f"Generated {len(site.get('files', []))} files — starting deploy pipeline…"})}\n\n'

                    async for dev in run_deploy_pipeline(request.user_id, site, request.message, creation_id):
                        yield f"data: {json.dumps(dev)}\n\n"
                        if dev.get("type") == "deployment_pending":
                            await mark_deployment_pending(
                                creation_id,
                                dev.get("deployment_id", ""),
                                repo_url=dev.get("repo_url", ""),
                                expected_url=dev.get("expected_url", ""),
                            )
                            yield f'data: {json.dumps({"type": "agent_status", "id": "a2", "status": "complete"})}\n\n'
                        elif dev.get("type") == "deployment_error":
                            yield f'data: {json.dumps({"type": "agent_status", "id": "a2", "status": "failed"})}\n\n'

                    yield "data: [DONE]\n\n"
                    return

                except Exception as dep_err:
                    print(f"[CREATE] Confirmed website deploy failed: {dep_err}")
                    yield f'data: {json.dumps({"type": "deployment_error", "value": "Website deployment failed before the Vercel build could be triggered. The previous design is still saved; retry deployment after checking the logs."})}\n\n'
                    yield "data: [DONE]\n\n"
                    return

            async for event in orchestrate_creation(request.message, context):
                if event["type"] == "plan":
                    creation_id = await create_creation_row(
                        user_id=request.user_id,
                        title=event.get("title", "Creation"),
                        intro=event.get("intro", ""),
                        user_message=request.message,
                        plan=event.get("agents", []),
                        industry=context.get("industry", ""),
                        company_name=context.get("company_name", ""),
                    )
                    if creation_id:
                        yield f'data: {json.dumps({"type": "creation_id", "id": creation_id})}\n\n'

                elif event["type"] == "artifact":
                    artifact = event.get("content", "")

                elif event["type"] == "code_artifact":
                    # Designer's raw code — not shown in chat, passed to deployment
                    code_for_deployment = event.get("content", "")
                    continue  # do NOT forward to frontend

                elif event["type"] == "error":
                    has_error = True
                    error_msg = event.get("value", "")

                elif event["type"] == "complete" and creation_id:
                    if artifact and not has_error:
                        await complete_creation_row(creation_id, artifact)

                        # ── SAVE TO DB BEFORE DEPLOYMENT — safe regardless of what happens next ──
                        if request.user_id:
                            try:
                                sb = _get_supabase()
                                if sb:
                                    conv_id, is_new = await asyncio.to_thread(
                                        _ensure_conversation, sb, request.user_id, conv_id, request.message
                                    )
                                    if conv_id:
                                        if is_new:
                                            yield f'data: {json.dumps({"type": "conv_id", "value": conv_id})}\n\n'
                                        saved_msg_id = await asyncio.to_thread(
                                            _save_message, sb, conv_id, artifact
                                        )
                            except Exception as db_err:
                                print(f"[CREATE] DB save failed (non-fatal): {db_err}")
                    else:
                        await fail_creation_row(creation_id, error_msg or "No artifact generated")

                yield f"data: {json.dumps(event)}\n\n"

            # ── DEPLOYMENT PHASE — isolated try/except ──
            # Creation output is already persisted above; a crash here is non-fatal.
            if artifact and not has_error and request.user_id:

                if _is_website_build(request.message) and has_deploy_connectors:
                    # ── NEW PATH: deterministic Next.js build + real URL ──────────
                    try:
                        yield f'data: {json.dumps({"type": "deployment_status", "message": "Generating Next.js codebase…"})}\n\n'
                        site = None
                        async for result in _await_with_status(
                            generate_site(request.message, {**context, "artifact": artifact}),
                            "Still generating the Next.js codebase…",
                        ):
                            if isinstance(result, dict) and "files" in result:
                                site = result
                            else:
                                yield f"data: {json.dumps(result)}\n\n"

                        if not site:
                            raise RuntimeError("site generator returned no files")
                        if site.get("is_fallback"):
                            fallback_notice = (
                                "The custom build step hit an issue, so I deployed a clean generic "
                                "starter instead, it will not match the design brief above. "
                                "Say \"rebuild the site\" to retry the custom version."
                            )
                            yield f'data: {json.dumps({"type": "deployment_status", "message": fallback_notice})}\n\n'
                        file_count = len(site.get("files", []))
                        yield f'data: {json.dumps({"type": "deployment_status", "message": f"Generated {file_count} files — starting deploy pipeline…"})}\n\n'

                        deploy_url: str | None = None
                        deploy_msg: str | None = None
                        async for dev in run_deploy_pipeline(request.user_id, site, request.message, creation_id):
                            yield f"data: {json.dumps(dev)}\n\n"
                            if dev.get("type") == "deployment_complete":
                                deploy_url = dev.get("url")
                                deploy_msg = dev.get("message", "")
                            elif dev.get("type") == "deployment_pending":
                                await mark_deployment_pending(
                                    creation_id,
                                    dev.get("deployment_id", ""),
                                    repo_url=dev.get("repo_url", ""),
                                    expected_url=dev.get("expected_url", ""),
                                )

                        if saved_msg_id and deploy_url and conv_id:
                            try:
                                sb = _get_supabase()
                                if sb:
                                    updated = artifact + "\n\n---\n\n" + (deploy_msg or f"🚀 Deployed: {deploy_url}")
                                    await asyncio.to_thread(_update_message, sb, saved_msg_id, updated)
                            except Exception as upd_err:
                                print(f"[CREATE] DB update post-deploy failed (non-fatal): {upd_err}")

                    except Exception as dep_err:
                        print(f"[CREATE] Website build failed: {dep_err}")
                        yield f'data: {json.dumps({"type": "deployment_error", "value": "⚠️ Website build hit an error. The design was saved — say \'deploy the last project\' to retry."})}\n\n'

                else:
                    # ── OLD PATH: LLM tool-loop deployment (non-website creations) ──
                    deploy_content = (
                        code_for_deployment
                        if (has_deploy_connectors and code_for_deployment)
                        else artifact
                    )

                    try:
                        deploy_events = await asyncio.wait_for(
                            _collect_deploy_events(request.user_id, deploy_content, request.message),
                            timeout=45.0,
                        )

                        deploy_url = None
                        deploy_msg = None
                        for dev in deploy_events:
                            yield f"data: {json.dumps(dev)}\n\n"
                            if dev.get("type") == "deployment_complete":
                                deploy_url = dev.get("url")
                                deploy_msg = dev.get("message", "")

                        if saved_msg_id and deploy_url and conv_id:
                            try:
                                sb = _get_supabase()
                                if sb:
                                    updated = artifact + "\n\n---\n\n" + (deploy_msg or f"🚀 Deployed: {deploy_url}")
                                    await asyncio.to_thread(_update_message, sb, saved_msg_id, updated)
                            except Exception as upd_err:
                                print(f"[CREATE] DB update post-deploy failed (non-fatal): {upd_err}")

                    except asyncio.TimeoutError:
                        print("[CREATE] Deployment timed out after 45s")
                        yield f'data: {json.dumps({"type": "deployment_error", "value": "⚠️ Deployment timed out after 45s. The code was saved — say \'deploy the last project\' to retry."})}\n\n'

                    except Exception as dep_err:
                        print(f"[CREATE] Deployment phase failed: {dep_err}")
                        yield f'data: {json.dumps({"type": "deployment_error", "value": "⚠️ The website was designed, but deployment hit an error. Say \'deploy the last project\' to retry."})}\n\n'

            yield "data: [DONE]\n\n"

        except Exception as e:
            import traceback
            traceback.print_exc()
            if creation_id:
                await fail_creation_row(creation_id, str(e)[:500])
            yield f'data: {json.dumps({"type": "error", "value": "Creation failed. Please try again."})}\n\n'
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
