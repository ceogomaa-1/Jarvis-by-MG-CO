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


async def update_standalone_html(
    creation_id: str,
    html: str,
    summary: str = "",
    *,
    has_live_deployment: bool = False,
) -> None:
    """Atomically replace the preview and deployable index.html after a surgical edit."""
    if not _is_valid_uuid(creation_id):
        return
    data: dict = {
        "preview_html": html,
        "files": [{"path": "index.html", "content": html}],
        "status": "complete",
    }
    if summary:
        data["artifact_markdown"] = summary
        data["intro"] = summary
    if has_live_deployment:
        # Keep the existing URL visible, but make it explicit that it serves the prior revision
        # until the operator clicks/says redeploy.
        data["deployment_status"] = "DIRTY"
        data["deployment_id"] = None
        data["deployment_error"] = None
    try:
        _client().table("business_creations").update(data).eq("id", creation_id).execute()
    except Exception as e:
        print(f"PERSISTENCE: update_standalone_html failed: {e}")


# ── Standalone (single-file HTML) creations ──────────────────────────────────

async def save_standalone_creation(
    user_id: str,
    title: str,
    user_message: str,
    html: str,
    summary: str = "",
    project_name: str = "",
    industry: str = "",
    company_name: str = "",
) -> str | None:
    """Persist a finished standalone HTML creation the MOMENT it's produced.

    Stores the rendered HTML in BOTH preview_html (for the live preview panel) and files
    (as a single index.html, so the same row can later be static-deployed to Vercel).
    Returns the new creation UUID, or None.
    """
    user_id = _user_id_to_uuid(user_id)
    if not _is_valid_uuid(user_id):
        return None
    files = [{"path": "index.html", "content": html}]
    try:
        result = _client().table("business_creations").insert({
            "user_id": user_id,
            "title": title or "Landing Page",
            "intro": summary or "",
            "user_message": user_message,
            "plan": [{"id": "a1", "role": "designer", "task": "Design a standalone landing page."}],
            "kind": "standalone",
            "files": files,
            "preview_html": html,
            "artifact_markdown": summary or "",
            "industry": industry or "",
            "company_name": company_name or project_name or "",
            "status": "complete",
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
        return result.data[0]["id"] if result.data else None
    except Exception as e:
        print(f"PERSISTENCE: save_standalone_creation failed: {e}")
        return None


async def save_site_files(creation_id: str | None, files: list, project_name: str = "") -> None:
    """Attach the generated multi-file project to its creation row (for resumable deploy)."""
    if not creation_id or not _is_valid_uuid(creation_id):
        return
    try:
        data = {"kind": "site", "files": files}
        if project_name:
            data["company_name"] = project_name
        _client().table("business_creations").update(data).eq("id", creation_id).execute()
    except Exception as e:
        print(f"PERSISTENCE: save_site_files failed: {e}")


async def attach_vercel_url(
    creation_id: str | None,
    vercel_url: str,
    deployment_id: str = "",
    state: str = "READY",
) -> None:
    """Record the live Vercel URL on a standalone creation after a static deploy."""
    if not creation_id or not _is_valid_uuid(creation_id):
        return
    data: dict = {"vercel_url": vercel_url, "live_url": vercel_url, "deployment_status": state}
    if deployment_id:
        data["deployment_id"] = deployment_id
    try:
        _client().table("business_creations").update(data).eq("id", creation_id).execute()
    except Exception as e:
        print(f"PERSISTENCE: attach_vercel_url failed: {e}")


async def get_latest_deployable(user_id: str) -> dict | None:
    """Most recent creation that has a saved file set — powers 'deploy the last project'."""
    user_uuid = _user_id_to_uuid(user_id)
    if not _is_valid_uuid(user_uuid):
        return None
    try:
        result = (
            _client().table("business_creations")
            .select("*")
            .eq("user_id", user_uuid)
            .not_.is_("files", "null")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None
    except Exception as e:
        print(f"PERSISTENCE: get_latest_deployable failed: {e}")
        return None


async def list_creations(user_id: str, limit: int = 25) -> list[dict]:
    """A user-visible list of past creations (newest first), light columns only."""
    user_uuid = _user_id_to_uuid(user_id)
    if not _is_valid_uuid(user_uuid):
        return []
    try:
        result = (
            _client().table("business_creations")
            .select("id,title,intro,kind,status,vercel_url,live_url,repo_url,created_at")
            .eq("user_id", user_uuid)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []
    except Exception as e:
        print(f"PERSISTENCE: list_creations failed: {e}")
        return []


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
