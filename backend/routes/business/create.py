import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.lib.business.creation.orchestrator import orchestrate_creation
from backend.lib.business.system_prompt_builder import _fetch_user_profile

router = APIRouter()


class CreateRequest(BaseModel):
    message: str
    user_id: str = ""


@router.post("/business/create")
async def business_create(request: CreateRequest):
    """Stream a Creation 1.0 sub-agent orchestration."""

    # Look up the user's industry / company so sub-agents are industry-aware
    profile = _fetch_user_profile(request.user_id) if request.user_id else {}
    context = {
        "user_id": request.user_id,
        "industry": profile.get("industry", ""),
        "company_name": profile.get("company_name", ""),
        "role": profile.get("role", ""),
    }

    async def generate():
        try:
            async for event in orchestrate_creation(request.message, context):
                yield f"data: {json.dumps(event)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            import traceback
            traceback.print_exc()
            yield f'data: {json.dumps({"type": "error", "value": "Creation failed. Please try again."})}\n\n'
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
