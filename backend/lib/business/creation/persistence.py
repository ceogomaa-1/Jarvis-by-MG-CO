import os
import re
from datetime import datetime, timezone

SUPABASE_URL = os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _client():
    from supabase import create_client
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def _is_valid_uuid(value: str) -> bool:
    return bool(value and _UUID_RE.match(value.strip()))


async def create_creation_row(
    user_id: str,
    title: str,
    intro: str,
    user_message: str,
    plan: list,
    industry: str = "",
    company_name: str = "",
) -> str | None:
    """Insert a 'running' creation row. Returns the new UUID or None."""
    if not _is_valid_uuid(user_id):
        return None
    try:
        result = _client().table("business_creations").insert({
            "user_id": user_id,
            "title": title or "Creation",
            "intro": intro or "",
            "user_message": user_message,
            "plan": plan,
            "industry": industry or "",
            "company_name": company_name or "",
            "status": "running",
        }).execute()
        return result.data[0]["id"] if result.data else None
    except Exception as e:
        print(f"PERSISTENCE: create_creation_row failed: {e}")
        return None


async def complete_creation_row(
    creation_id: str,
    artifact_markdown: str,
) -> None:
    try:
        _client().table("business_creations").update({
            "status": "complete",
            "artifact_markdown": artifact_markdown,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", creation_id).execute()
    except Exception as e:
        print(f"PERSISTENCE: complete_creation_row failed: {e}")


async def fail_creation_row(creation_id: str, error: str) -> None:
    try:
        _client().table("business_creations").update({
            "status": "failed",
            "error": error[:500],
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", creation_id).execute()
    except Exception as e:
        print(f"PERSISTENCE: fail_creation_row failed: {e}")


async def get_creation_row(creation_id: str) -> dict | None:
    if not _is_valid_uuid(creation_id):
        return None
    try:
        result = _client().table("business_creations").select("*").eq("id", creation_id).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        print(f"PERSISTENCE: get_creation_row failed: {e}")
        return None


async def update_artifact(creation_id: str, artifact_markdown: str) -> None:
    if not _is_valid_uuid(creation_id):
        return
    try:
        _client().table("business_creations").update({
            "artifact_markdown": artifact_markdown,
        }).eq("id", creation_id).execute()
    except Exception as e:
        print(f"PERSISTENCE: update_artifact failed: {e}")
