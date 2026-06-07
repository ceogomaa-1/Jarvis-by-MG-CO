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


def _user_id_to_uuid(user_id: str) -> str:
    hex_id = (user_id or "").removeprefix("user_")
    if len(hex_id) == 32 and all(c in "0123456789abcdef" for c in hex_id.lower()):
        return f"{hex_id[:8]}-{hex_id[8:12]}-{hex_id[12:16]}-{hex_id[16:20]}-{hex_id[20:]}"
    return user_id


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
    user_id = _user_id_to_uuid(user_id)
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


async def mark_deployment_pending(
    creation_id: str | None,
    deployment_id: str,
    repo_url: str = "",
    expected_url: str = "",
) -> None:
    if not creation_id or not _is_valid_uuid(creation_id):
        return
    try:
        _client().table("business_creations").update({
            "status": "building",
            "deployment_id": deployment_id,
            "repo_url": repo_url,
            "expected_url": expected_url,
            "deployment_status": "BUILDING",
            "deployment_error": None,
        }).eq("id", creation_id).execute()
    except Exception as e:
        print(f"PERSISTENCE: mark_deployment_pending failed: {e}")


async def update_deployment_by_id(
    deployment_id: str,
    state: str,
    live_url: str | None = None,
    error: str | None = None,
) -> None:
    if not deployment_id:
        return
    status = "complete" if state == "READY" else "failed" if state in {"ERROR", "FAILED", "CANCELED"} else "building"
    data = {
        "status": status,
        "deployment_status": state,
        "deployment_error": error,
    }
    if live_url:
        data["live_url"] = live_url
    if status in {"complete", "failed"}:
        data["completed_at"] = datetime.now(timezone.utc).isoformat()
    try:
        _client().table("business_creations").update(data).eq("deployment_id", deployment_id).execute()
    except Exception as e:
        print(f"PERSISTENCE: update_deployment_by_id failed: {e}")
