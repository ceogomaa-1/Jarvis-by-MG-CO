import os
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from supabase import create_client

from backend.lib.business.memory import _store_memory_if_new, _user_id_to_uuid

router = APIRouter()

SUPABASE_URL = os.getenv("NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")


def _client():
    return create_client(SUPABASE_URL, SUPABASE_KEY)


class OnboardCompleteRequest(BaseModel):
    user_id: str
    email: Optional[str] = None
    name: str
    industry: str
    custom_industry: Optional[str] = None
    company_name: str
    mission: Optional[str] = None


@router.post("/business/onboard/complete")
async def complete_onboarding(body: OnboardCompleteRequest):
    """Create/update the business_users row, set jarvis_mode, and bury onboarding
    answers as memories so readiness checkpoints light up immediately.

    The business_users upsert is the critical step the chat page's first-timer
    check depends on — if it fails we must surface a real error (not a 200
    with ok:false), otherwise the frontend redirects to chat for a profile
    that was never created, causing an onboarding<->chat redirect loop."""
    sb = _client()

    try:
        result = (
            sb.table("business_users")
            .upsert({
                "user_id": body.user_id,
                "email": body.email,
                "company_name": body.company_name,
                "industry": body.industry,
                "role": "owner",
                "custom_industry": body.custom_industry,
            }, on_conflict="user_id")
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"business_users upsert failed: {e}")

    business_user = result.data[0] if result.data else {
        "user_id": body.user_id,
        "email": body.email,
        "company_name": body.company_name,
        "industry": body.industry,
        "custom_industry": body.custom_industry,
        "role": "owner",
    }

    # Auxiliary steps — best-effort, must not block onboarding completion.
    try:
        sb.table("user_preferences").upsert({
            "user_id": body.user_id,
            "jarvis_mode": "business",
            "updated_at": "now()",
        }).execute()

        user_uuid = _user_id_to_uuid(body.user_id)

        memories = [f"The user's name is {body.name}."]
        if body.industry.lower() == "other" and body.custom_industry:
            memories.append(f"The user's business operates in the {body.custom_industry} industry.")
        else:
            memories.append(f"The user runs a {body.industry} business.")
        memories.append(f"The user's business is called {body.company_name}.")
        if body.mission:
            memories.append(f"The user's goal: {body.mission}")

        for memory_text in memories:
            _store_memory_if_new(sb, user_uuid, memory_text, None)
    except Exception as e:
        return {"ok": True, "business_user": business_user, "warning": str(e)}

    return {"ok": True, "business_user": business_user}
