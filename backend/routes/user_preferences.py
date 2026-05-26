from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
import os
from supabase import create_client

router = APIRouter()

SUPABASE_URL = os.getenv("NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")


def _client():
    return create_client(SUPABASE_URL, SUPABASE_KEY)


class PreferenceUpdate(BaseModel):
    user_id: str
    jarvis_mode: str  # 'personal' | 'business'


class TimezoneUpdate(BaseModel):
    user_id: str
    timezone: str
    timezone_confirmed: bool = False


class CompleteOnboardingRequest(BaseModel):
    user_id: str


class BusinessUserCreate(BaseModel):
    user_id: str
    email: Optional[str] = None
    company_name: str
    industry: str
    role: str  # 'owner' | 'manager' | 'operator'


@router.get("/user-preferences/{user_id}")
async def get_preference(user_id: str):
    try:
        sb = _client()
        res = sb.table("user_preferences").select("jarvis_mode,timezone,timezone_confirmed").eq("user_id", user_id).maybe_single().execute()
        if res.data:
            return res.data
        return {"jarvis_mode": None, "timezone": None, "timezone_confirmed": False}
    except Exception as e:
        return {"jarvis_mode": None, "timezone": None, "timezone_confirmed": False, "error": str(e)}


@router.post("/user-preferences")
async def set_preference(body: PreferenceUpdate):
    try:
        sb = _client()
        sb.table("user_preferences").upsert({
            "user_id": body.user_id,
            "jarvis_mode": body.jarvis_mode,
            "updated_at": "now()",
        }).execute()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.patch("/user-preferences/timezone")
async def set_timezone(body: TimezoneUpdate):
    try:
        sb = _client()
        data: dict = {"user_id": body.user_id, "timezone": body.timezone}
        # Only write timezone_confirmed when explicitly confirming — silent captures
        # must not overwrite an existing True value for returning users.
        if body.timezone_confirmed:
            data["timezone_confirmed"] = True
        sb.table("user_preferences").upsert(data).execute()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/user-preferences/complete-onboarding")
async def complete_onboarding(body: CompleteOnboardingRequest):
    try:
        sb = _client()
        sb.table("user_preferences").upsert({
            "user_id": body.user_id,
            "onboarding_complete": True,
        }).execute()
        print(f"ONBOARDING_GATE: marked complete for user_id={body.user_id}")
        return {"ok": True}
    except Exception as e:
        print(f"ONBOARDING_GATE: ERROR marking complete for {body.user_id}: {e}")
        return {"ok": False, "error": str(e)}


@router.post("/business-users")
async def create_business_user(body: BusinessUserCreate):
    try:
        sb = _client()
        # Upsert by user_id so re-onboarding doesn't duplicate
        sb.table("business_users").upsert({
            "user_id": body.user_id,
            "email": body.email,
            "company_name": body.company_name,
            "industry": body.industry,
            "role": body.role,
        }, on_conflict="user_id").execute()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}
