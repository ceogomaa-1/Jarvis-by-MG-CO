import asyncio
import json
import os
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from supabase import create_client

from backend.lib.business.connectors.registry import list_user_connections
from backend.lib.business.creation.deployment_phase import deploy_project_after_creation
from backend.lib.business.creation.orchestrator import orchestrate_creation
from backend.lib.business.creation.persistence import (
    complete_creation_row,
    create_creation_row,
    fail_creation_row,
)
from backend.lib.business.system_prompt_builder import _fetch_user_profile

router = APIRouter()

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


class CreateRequest(BaseModel):
    message: str
    user_id: str = ""
    conversation_id: str | None = None


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

            # ── DEPLOYMENT PHASE — isolated try/except + 60s timeout ──
            # The creation output is already persisted above, so a crash here is non-fatal.
            if artifact and not has_error and request.user_id:
                deploy_content = (
                    code_for_deployment
                    if (has_deploy_connectors and code_for_deployment)
                    else artifact
                )

                try:
                    deploy_events = await asyncio.wait_for(
                        _collect_deploy_events(request.user_id, deploy_content, request.message),
                        timeout=60.0,
                    )

                    deploy_url: str | None = None
                    deploy_msg: str | None = None
                    for dev in deploy_events:
                        yield f"data: {json.dumps(dev)}\n\n"
                        if dev.get("type") == "deployment_complete":
                            deploy_url = dev.get("url")
                            deploy_msg = dev.get("message", "")

                    # Append live URL to the saved message
                    if saved_msg_id and deploy_url and conv_id:
                        try:
                            sb = _get_supabase()
                            if sb:
                                updated = artifact + "\n\n---\n\n" + (deploy_msg or f"🚀 Deployed: {deploy_url}")
                                await asyncio.to_thread(_update_message, sb, saved_msg_id, updated)
                        except Exception as upd_err:
                            print(f"[CREATE] DB update post-deploy failed (non-fatal): {upd_err}")

                except asyncio.TimeoutError:
                    print("[CREATE] Deployment timed out after 60s")
                    yield f'data: {json.dumps({"type": "deployment_error", "value": "⚠️ Deployment timed out. The code was generated — say \'deploy the last project\' to retry."})}\n\n'

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
