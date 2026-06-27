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
from backend.lib.business.creation.orchestrator import orchestrate_creation
from backend.lib.business.creation.persistence import (
    attach_vercel_url,
    complete_creation_row,
    create_creation_row,
    fail_creation_row,
    get_creation_row,
    get_latest_deployable,
    list_creations,
    mark_deployment_pending,
    save_site_files,
    save_standalone_creation,
    update_deployment_by_id,
)
from backend.lib.business.creation.site_generator import (
    SiteGenerationError,
    generate_site,
    _sanitize_name,
)
from backend.lib.business.creation.standalone_generator import (
    WebsiteGenerationError,
    generate_standalone_page,
)
from backend.lib.business.creation.website_context import enrich_website_context
from backend.lib.business.creation.website_quality import (
    extract_client_name,
    should_use_owner_company,
    validate_standalone_html,
)
from backend.lib.business.intent_router import is_website_build_request
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
# Explicit "take it live" request — deploys the LAST creation (standalone → Vercel, or
# multi-file → GitHub+Vercel). Distinct from a bare "yes" confirmation.
_DEPLOY_REQUEST_RE = re.compile(
    r"\b(deploy|publish|push|go\s*live|make\s+(it|this)\s+live|take\s+(it|this)\s+live|"
    r"ship\s+(it|this)|launch\s+(it|this)|put\s+(it|this)\s+(live|online))\b",
    re.IGNORECASE,
)
# When the user explicitly wants the multi-file GitHub route (not a static single-file deploy).
_WANTS_GITHUB_RE = re.compile(
    r"\b(github|repo|repository|next\.?js|multi[-\s]?file|full\s+(site|project|app)|"
    r"to\s+github)\b",
    re.IGNORECASE,
)


def _is_deploy_request(message: str) -> bool:
    return bool(_DEPLOY_REQUEST_RE.search(message or ""))


def _wants_github_deploy(message: str) -> bool:
    return bool(_WANTS_GITHUB_RE.search(message or ""))

# Appended to a website/landing-page artifact so the user can choose to deploy.
# Mentions "GitHub + Vercel" so the explicit "deploy it" path (_DEPLOY_OFFER_RE)
# can later find this artifact. We never deploy without this confirmation.
_DEPLOY_OFFER_SUFFIX = (
    "\n\n---\n\n🚀 **Want this live?** Say **\"deploy it\"** and I'll push it to "
    "GitHub + Vercel and hand you the live URL. Nothing is deployed until you do."
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


# ════════════════════════════════════════════════════════════════════
# MODE HANDLERS (each yields raw SSE event dicts; the route serializes them)
# ════════════════════════════════════════════════════════════════════

async def _run_standalone_build(request, context, conv_id):
    """MODE 1 — produce ONE stunning self-contained HTML page, persisted immediately.

    Yields ("event", dict) tuples and one ("creation_id", id) / ("conv_id", id) signal so the
    caller can manage chat persistence. Persists the moment the HTML exists, so a dropped SSE
    never loses the work — the page is rehydratable from the DB by creation_id.
    """
    explicit_client = extract_client_name(request.message)
    title_guess = (
        explicit_client
        or (
            context.get("company_name")
            if should_use_owner_company(request.message, explicit_client)
            else ""
        )
        or "Client Website"
    )
    yield ("event", {
        "type": "plan",
        "title": title_guess,
        "intro": "Designing a polished, animated landing page you can preview, download, or take live.",
        "agents": [{"id": "a1", "role": "designer", "task": "Design a high-craft standalone landing page."}],
        "mode": "standalone",
    })
    yield ("event", {"type": "agent_status", "id": "a1", "status": "started"})
    yield ("event", {
        "type": "creation_stage",
        "stage": "researching",
        "message": "Resolving the client and studying the current website…",
    })

    build_context = await enrich_website_context(
        request.user_id,
        request.message,
        {**context, "client_name": explicit_client},
    )
    if build_context.get("website_research"):
        yield ("event", {
            "type": "creation_stage",
            "stage": "grounded",
            "message": "Current website and CRM context captured. Designing the replacement…",
        })
    elif build_context.get("client_name"):
        yield ("event", {
            "type": "creation_stage",
            "stage": "grounded",
            "message": f"Building for {build_context['client_name']}. Designing the page…",
        })
    else:
        yield ("event", {
            "type": "creation_stage",
            "stage": "designing",
            "message": "Designing the page from the supplied brief…",
        })

    page = None
    try:
        async for result in _await_with_status(
            generate_standalone_page(request.message, build_context),
            "Opus is still crafting and quality-checking the page…",
        ):
            if isinstance(result, dict) and "html" in result:
                page = result
            else:
                yield ("event", result)
    except WebsiteGenerationError as exc:
        yield ("event", {"type": "agent_status", "id": "a1", "status": "failed"})
        yield ("event", {"type": "error", "value": str(exc)})
        return

    if not page:
        yield ("event", {"type": "agent_status", "id": "a1", "status": "failed"})
        yield ("event", {
            "type": "error",
            "value": "Page generation returned no validated website. Nothing was saved or deployed.",
        })
        return

    yield ("event", {"type": "creation_stage", "stage": "assembling", "message": "Assembling and saving…"})
    creation_id = await save_standalone_creation(
        user_id=request.user_id,
        title=page["title"],
        user_message=request.message,
        html=page["html"],
        summary=page.get("summary", ""),
        project_name=page.get("project_name", ""),
        industry=build_context.get("industry", ""),
        company_name=build_context.get("client_name") or page.get("title", ""),
    )
    if creation_id:
        yield ("creation_id", creation_id)
        yield ("event", {"type": "creation_id", "id": creation_id})

    yield ("event", {"type": "agent_status", "id": "a1", "status": "complete"})
    yield ("event", {
        "type": "html_artifact",
        "creation_id": creation_id,
        "title": page["title"],
        "summary": page.get("summary", ""),
        "project_name": page.get("project_name", ""),
        "html": page["html"],
        "is_fallback": False,
    })
    yield ("event", {"type": "complete"})

    note = (
        f"✅ Built **{page['title']}** — a polished, animated landing page. It's in the preview on the right; "
        f"you can **download the HTML** or say **\"deploy it\"** and I'll publish it to a live URL."
    )
    # Hidden marker so a page refresh can rehydrate this creation's preview from the DB.
    if creation_id:
        note = f"{note}\n\n⟦jarvis-creation:{creation_id}⟧"
    yield ("chat_message", note)


async def _run_deploy_last(request, context, has_deploy_connectors):
    """MODE 2/3 — take the user's last creation live.

    Standalone creation + no GitHub ask → static single-file deploy to Vercel (MODE 2).
    Otherwise → multi-file Next.js → GitHub + Vercel (MODE 3), reusing saved files when present
    (resumable) or generating a project from the saved brief.
    Yields ("event", dict) and ("deployment_pending", dict) signals.
    """
    user_id = request.user_id
    wants_github = _wants_github_deploy(request.message)
    target = await get_latest_deployable(user_id) if user_id else None

    # Nothing built yet → don't fabricate a site from a bare "deploy it". Guide the user.
    if not target:
        yield ("event", {
            "type": "deployment_error",
            "value": "I don't have a saved page or project to deploy yet — build one first (e.g. \"make me a landing page for …\"), then say \"deploy it\".",
            "stage": "preflight",
        })
        return

    # ── MODE 2: standalone HTML → Vercel static deploy ────────────────────────
    if target and target.get("kind") == "standalone" and not wants_github:
        html = target.get("preview_html") or ((target.get("files") or [{}])[0].get("content", ""))
        if not html:
            yield ("event", {"type": "deployment_error", "value": "I couldn't find the saved page to deploy — rebuild it and try again.", "stage": "preflight"})
            return
        quality_errors = validate_standalone_html(
            html,
            target.get("user_message") or "",
            {"client_name": target.get("company_name") or target.get("title") or ""},
        )
        if quality_errors:
            yield ("event", {
                "type": "deployment_error",
                "value": (
                    "The saved page failed the client-safety quality gate, so I refused to "
                    "publish it. Rebuild the page first. "
                    + "; ".join(quality_errors[:4])
                ),
                "stage": "validation",
            })
            return
        vc = await get_connector_for_user(user_id, "vercel")
        if not vc:
            yield ("event", {"type": "deployment_error", "value": "Vercel isn't connected — add it in Settings → Connections, then say 'deploy it' again. (A static page only needs Vercel, not GitHub.)", "stage": "preflight"})
            return
        yield ("event", {"type": "creation_id", "id": target["id"]})
        yield ("event", {"type": "plan", "title": f"Publishing {target.get('title', 'your page')}",
                         "intro": "Taking your landing page live on Vercel.",
                         "agents": [{"id": "a1", "role": "reporter", "task": "Deploy the page to Vercel."}], "mode": "deploy_static"})
        yield ("event", {"type": "agent_status", "id": "a1", "status": "started"})
        yield ("event", {"type": "deployment_started"})
        pre = await vc.preflight()
        if not pre.ok:
            yield ("event", {"type": "deployment_error", "value": pre.error, "stage": "preflight"})
            yield ("event", {"type": "agent_status", "id": "a1", "status": "failed"})
            return
        project = _sanitize_name(target.get("company_name") or target.get("title") or "landing-page")
        yield ("event", {"type": "deployment_status", "message": "Uploading your page to Vercel…"})
        res = None
        async for ev in _await_with_status(vc.deploy_static(project, html), "Still uploading to Vercel…"):
            if isinstance(ev, dict):
                yield ("event", ev)
            else:
                res = ev  # ConnectorResult
        if not res or not res.ok:
            yield ("event", {"type": "deployment_error", "value": f"Vercel deploy failed: {res.error if res else 'unknown error'}. Say 'deploy it' to retry.", "stage": "vercel_deploy"})
            yield ("event", {"type": "agent_status", "id": "a1", "status": "failed"})
            return
        dep_id = res.data.get("deployment_id", "")
        url = res.data.get("url", "")
        expected = url if url else f"https://{project}.vercel.app"
        await attach_vercel_url(target["id"], expected, dep_id, "BUILDING")
        yield ("event", {"type": "agent_status", "id": "a1", "status": "complete"})
        yield ("deployment_pending", {
            "type": "deployment_pending",
            "deployment_id": dep_id,
            "creation_id": target["id"],
            "expected_url": expected,
            "repo_url": "",
            "db_url": None,
            "message": "Publishing on Vercel — I'll update this card the moment it's live.",
        })
        return

    # ── MODE 3: multi-file Next.js → GitHub + Vercel ──────────────────────────
    if not has_deploy_connectors:
        yield ("event", {"type": "deployment_error", "value": "A full GitHub + Vercel deploy needs both connected — add them in Settings → Connections, then say 'deploy the last project'.", "stage": "preflight"})
        return

    site = None
    creation_id = target["id"] if target else None
    if target and target.get("kind") == "site" and target.get("files"):
        # Resumable: redeploy the exact saved file set — no regeneration.
        site = {
            "project_name": _sanitize_name(target.get("company_name") or target.get("title") or "jarvis-site"),
            "framework": "nextjs",
            "needs_database": False,
            "db_plan": None,
            "files": target["files"],
            "summary": target.get("intro", ""),
            "is_fallback": False,
        }
        yield ("event", {"type": "deployment_status", "message": f"Re-deploying the saved project ({len(site['files'])} files)…"})
    else:
        # Generate a Next.js project from the saved brief (or the request) then deploy.
        brief = ""
        if target:
            brief = target.get("preview_html") or target.get("artifact_markdown") or ""
        yield ("event", {"type": "agent_status", "id": "a1", "status": "started"})
        yield ("event", {"type": "deployment_status", "message": "Generating the Next.js codebase…"})
        original_request = (target or {}).get("user_message") or request.message
        site_prompt = (
            "Port the saved approved website into a production Next.js site and prepare it "
            f"for deployment.\n\nOriginal build request: {original_request}"
        )
        site_context = {
            **context,
            "artifact": brief,
            "client_name": (target or {}).get("company_name") or (target or {}).get("title") or "",
        }
        try:
            async for result in _await_with_status(
                generate_site(site_prompt, site_context),
                "Opus is still generating and validating the Next.js codebase…",
            ):
                if isinstance(result, dict) and "files" in result:
                    site = result
                else:
                    yield ("event", result)
        except SiteGenerationError as exc:
            yield ("event", {
                "type": "deployment_error",
                "value": str(exc),
                "stage": "site_gen",
            })
            return
        if not site:
            yield ("event", {"type": "deployment_error", "value": "Site generation failed before deploy. Try again.", "stage": "site_gen"})
            return
        if not creation_id:
            creation_id = await create_creation_row(
                user_id=user_id, title=site.get("project_name", "Website"),
                intro="Deploying a generated Next.js site.", user_message=request.message,
                plan=[{"id": "a1", "role": "designer", "task": "Generate the site"}],
                industry=context.get("industry", ""), company_name=context.get("company_name", ""),
            )
        await save_site_files(creation_id, site["files"], site.get("project_name", ""))

    if creation_id:
        yield ("event", {"type": "creation_id", "id": creation_id})
    async for dev in run_deploy_pipeline(user_id, site, request.message, creation_id):
        if dev.get("type") == "deployment_pending":
            yield ("deployment_pending", dev)
        else:
            yield ("event", dev)


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
        # The status CHECK failed (Vercel API error, disconnected token, etc.) — this
        # is not the same as "still building". Report it honestly as UNKNOWN with the
        # real error, rather than claiming BUILDING while the deployment itself may
        # have already finished (or failed) with no way for us to know right now.
        await update_deployment_by_id(deployment_id, "UNKNOWN", error=status_res.error)
        return {"state": "UNKNOWN", "url": None, "error": status_res.error, "logs": None}

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


@router.get("/business/creations")
async def business_list_creations(user_id: str = "", limit: int = 25):
    """User-visible list of past creations (newest first) for the Creation history panel."""
    if not user_id:
        return {"creations": []}
    rows = await list_creations(user_id, limit=min(max(limit, 1), 100))
    return {"creations": rows}


@router.get("/business/creations/{creation_id}")
async def business_get_creation(creation_id: str, user_id: str = ""):
    """Rehydrate one creation — returns the full row incl. preview_html / files / vercel_url so the
    Creation canvas can restore the live preview after a refresh (refresh never loses work)."""
    row = await get_creation_row(creation_id)
    if not row:
        return {"error": "not found"}
    # Defense-in-depth: only return a row the requester owns.
    if user_id and row.get("user_id") and _user_id_to_uuid(user_id) != row.get("user_id"):
        return {"error": "not found"}
    return {"creation": row}


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
        has_error = False
        error_msg = ""
        conv_id = request.conversation_id
        saved_msg_id: str | None = None

        try:
            # Immediate signal so UI shows activity during the 2-4s planning gap
            yield f'data: {json.dumps({"type": "status", "value": "spinning up"})}\n\n'

            # ── MODE 2/3: explicit "deploy / publish / go live" → take the LAST creation live ──
            if _is_deploy_request(request.message):
                sb = _get_supabase()
                if sb:
                    try:
                        conv_id, is_new = await asyncio.to_thread(
                            _ensure_conversation, sb, request.user_id, conv_id, request.message
                        )
                        if conv_id and is_new:
                            yield f'data: {json.dumps({"type": "conv_id", "value": conv_id})}\n\n'
                    except Exception as e:
                        print(f"[CREATE] deploy conv setup failed: {e}")
                deploy_creation_id = None
                async for kind, payload in _run_deploy_last(request, context, has_deploy_connectors):
                    if kind == "event":
                        yield f"data: {json.dumps(payload)}\n\n"
                    elif kind == "deployment_pending":
                        deploy_creation_id = payload.get("creation_id") or deploy_creation_id
                        yield f"data: {json.dumps(payload)}\n\n"
                        await mark_deployment_pending(
                            payload.get("creation_id"),
                            payload.get("deployment_id", ""),
                            repo_url=payload.get("repo_url", ""),
                            expected_url=payload.get("expected_url", ""),
                        )
                yield "data: [DONE]\n\n"
                return

            # ── MODE 1: website / landing-page build → ONE stunning standalone HTML page ──
            if is_website_build_request(request.message):
                sb = _get_supabase()
                if sb:
                    try:
                        conv_id, is_new = await asyncio.to_thread(
                            _ensure_conversation, sb, request.user_id, conv_id, request.message
                        )
                        if conv_id and is_new:
                            yield f'data: {json.dumps({"type": "conv_id", "value": conv_id})}\n\n'
                    except Exception as e:
                        print(f"[CREATE] standalone conv setup failed: {e}")
                async for kind, payload in _run_standalone_build(request, context, conv_id):
                    if kind == "event":
                        yield f"data: {json.dumps(payload)}\n\n"
                    elif kind == "creation_id":
                        creation_id = payload
                    elif kind == "chat_message":
                        if sb and conv_id:
                            try:
                                await asyncio.to_thread(_save_message, sb, conv_id, payload)
                            except Exception as e:
                                print(f"[CREATE] standalone chat save failed: {e}")
                yield "data: [DONE]\n\n"
                return

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
                    try:
                        async for result in _await_with_status(
                            generate_site(site_prompt, {**context, "artifact": previous_artifact}),
                            "Opus is still generating and validating the Next.js codebase…",
                        ):
                            if isinstance(result, dict) and "files" in result:
                                site = result
                            else:
                                yield f"data: {json.dumps(result)}\n\n"
                    except SiteGenerationError as exc:
                        yield f'data: {json.dumps({"type": "agent_status", "id": "a1", "status": "failed"})}\n\n'
                        yield f'data: {json.dumps({"type": "deployment_error", "value": str(exc), "stage": "site_gen"})}\n\n'
                        yield "data: [DONE]\n\n"
                        return

                    if not site:
                        raise RuntimeError("site generator returned no files")

                    await complete_creation_row(creation_id, previous_artifact) if creation_id else None
                    yield f'data: {json.dumps({"type": "agent_status", "id": "a1", "status": "complete"})}\n\n'
                    yield f'data: {json.dumps({"type": "artifact", "format": "markdown", "content": previous_artifact})}\n\n'
                    yield f'data: {json.dumps({"type": "complete"})}\n\n'
                    yield f'data: {json.dumps({"type": "agent_status", "id": "a2", "status": "started"})}\n\n'
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
                    # For website builds with deploy connectors, OFFER deployment —
                    # never auto-deploy. The offer text (mentioning GitHub + Vercel)
                    # is what the explicit "deploy it" confirmation path keys off of.
                    if _is_website_build(request.message) and has_deploy_connectors:
                        artifact = artifact.rstrip() + _DEPLOY_OFFER_SUFFIX
                        event["content"] = artifact

                elif event["type"] == "code_artifact":
                    # Designer's raw code — never shown in chat (FIX 4: no raw code dumps).
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

            # NOTE: deployment NEVER runs automatically here. A site/page is only
            # pushed to GitHub + Vercel when the user explicitly confirms it — that
            # path is handled at the top of this function via _is_deploy_confirmation.
            # (This is the fix for the phantom auto-deploy that shipped websites no
            # one asked for. For website builds, the artifact above ends with a
            # "say 'deploy it'" offer instead.)

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
