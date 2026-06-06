import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.lib.business.creation.deployment_phase import deploy_project_after_creation
from backend.lib.business.creation.orchestrator import orchestrate_creation
from backend.lib.business.creation.persistence import (
    complete_creation_row,
    create_creation_row,
    fail_creation_row,
)
from backend.lib.business.system_prompt_builder import _fetch_user_profile

router = APIRouter()


class CreateRequest(BaseModel):
    message: str
    user_id: str = ""


@router.post("/business/create")
async def business_create(request: CreateRequest):
    """Stream a Creation 1.0 sub-agent orchestration with persistence."""
    profile = _fetch_user_profile(request.user_id) if request.user_id else {}
    context = {
        "user_id": request.user_id,
        "industry": profile.get("industry", ""),
        "company_name": profile.get("company_name", ""),
        "role": profile.get("role", ""),
    }

    async def generate():
        creation_id = None
        artifact = ""
        has_error = False
        error_msg = ""

        try:
            async for event in orchestrate_creation(request.message, context):
                # After the plan is received, insert the persistence row and emit creation_id
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

                elif event["type"] == "error":
                    has_error = True
                    error_msg = event.get("value", "")

                elif event["type"] == "complete" and creation_id:
                    if artifact and not has_error:
                        await complete_creation_row(creation_id, artifact)
                    else:
                        await fail_creation_row(creation_id, error_msg or "No artifact generated")

                yield f"data: {json.dumps(event)}\n\n"

            # Deployment phase — runs after creation completes, before [DONE]
            if artifact and not has_error and request.user_id:
                async for deploy_event in deploy_project_after_creation(
                    user_id=request.user_id,
                    artifact_markdown=artifact,
                    user_message=request.message,
                ):
                    yield f"data: {json.dumps(deploy_event)}\n\n"

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
