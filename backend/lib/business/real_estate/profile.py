"""Shared helpers for the Real Estate Operator Suite: user profile lookup + industry gate."""
import asyncio

from supabase import create_client

from backend.lib.business.bible_loader import get_industry_filename
from backend.utils.env import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY


def _get_supabase():
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return None
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


def _user_id_to_uuid(user_id: str) -> str:
    hex_id = user_id.removeprefix("user_")
    if len(hex_id) == 32 and all(c in "0123456789abcdef" for c in hex_id.lower()):
        return f"{hex_id[:8]}-{hex_id[8:12]}-{hex_id[12:16]}-{hex_id[16:20]}-{hex_id[20:]}"
    return user_id


def _fetch_profile_row(user_id: str) -> dict:
    try:
        sb = _get_supabase()
        if not sb:
            return {}
        res = (
            sb.table("business_users")
            .select("company_name, industry, role, custom_industry, email")
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        return res.data or {}
    except Exception:
        return {}


def _fetch_memories(user_id: str, limit: int = 30) -> list[str]:
    try:
        sb = _get_supabase()
        if not sb:
            return []
        user_uuid = _user_id_to_uuid(user_id)
        res = (
            sb.table("business_user_memories")
            .select("memory")
            .eq("user_id", user_uuid)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return [m["memory"] for m in (res.data or []) if m.get("memory")]
    except Exception:
        return []


async def get_business_profile(user_id: str) -> dict:
    """Returns {company_name, industry, role, custom_industry, email, memories: [...]}."""
    if not user_id:
        return {"memories": []}
    profile = await asyncio.to_thread(_fetch_profile_row, user_id)
    profile["memories"] = await asyncio.to_thread(_fetch_memories, user_id)
    return profile


async def is_real_estate_user(user_id: str) -> bool:
    if not user_id:
        return False
    profile = await asyncio.to_thread(_fetch_profile_row, user_id)
    return get_industry_filename(profile.get("industry", "")) == "real_estate.md"
