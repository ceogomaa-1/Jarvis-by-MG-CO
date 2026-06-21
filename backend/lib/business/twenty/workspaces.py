"""
Per-client Jarvis CRM workspace registry (Phase 2 multi-tenant).

Phase 1 talked to ONE shared Twenty instance from env. Phase 2 gives each client
their own data-isolated workspace (Twenty native multi-workspace, subdomain-routed)
and stores that workspace's base URL + API key here, keyed by Jarvis user_id, so the
backend can resolve the correct tenant per user.

Backed by Supabase (PostgREST) with the service-role key — identical access pattern
to store.py / connectors/registry.py. Table: crm_client_workspaces
(see supabase/migrations/batch58_twenty_workspaces.sql). The api_key column is a
secret and is only ever read with the service-role key; it is never returned to
end users.

Fallback: if a user has no row here, callers fall back to the single shared
instance (TWENTY_API_URL/TWENTY_API_KEY) so Phase 1 keeps working unchanged.
"""
import os

import httpx

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")


def _user_id_to_uuid(user_id: str) -> str:
    hex_id = (user_id or "").removeprefix("user_")
    if len(hex_id) == 32 and all(c in "0123456789abcdef" for c in hex_id.lower()):
        return f"{hex_id[:8]}-{hex_id[8:12]}-{hex_id[12:16]}-{hex_id[16:20]}-{hex_id[20:]}"
    return user_id


def _headers(extra: dict | None = None) -> dict:
    h = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    if extra:
        h.update(extra)
    return h


def _enabled() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY)


async def get_workspace(user_id: str) -> dict | None:
    """Return the active workspace row for a user, or None.

    Shape: {workspace_id, subdomain, base_url, api_key, display_name, status, ...}.
    Only 'active' workspaces are returned — a disabled one resolves to None so the
    caller can fall back to the shared instance (or refuse).
    """
    if not _enabled():
        return None
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/crm_client_workspaces",
                headers=_headers(),
                params={
                    "select": "workspace_id,subdomain,base_url,api_key,display_name,status,branding_applied",
                    "user_id": f"eq.{_user_id_to_uuid(user_id)}",
                    "status": "eq.active",
                    "limit": "1",
                },
                timeout=10.0,
            )
        if resp.status_code == 200:
            rows = resp.json()
            return rows[0] if rows else None
    except Exception as e:
        print(f"TWENTY.workspaces: get_workspace failed: {e}")
    return None


async def has_workspace(user_id: str) -> bool:
    """True iff the user has an active provisioned workspace."""
    return await get_workspace(user_id) is not None


async def upsert_workspace(
    user_id: str,
    *,
    base_url: str,
    api_key: str,
    subdomain: str | None = None,
    workspace_id: str | None = None,
    display_name: str | None = None,
    branding_applied: bool = False,
    status: str = "active",
) -> dict | None:
    """Insert or update the user's workspace mapping. Returns the row, or None."""
    if not _enabled() or not base_url or not api_key:
        return None
    payload = {
        "user_id": _user_id_to_uuid(user_id),
        "base_url": base_url.rstrip("/"),
        "api_key": api_key.strip(),
        "subdomain": subdomain,
        "workspace_id": workspace_id,
        "display_name": display_name,
        "branding_applied": branding_applied,
        "status": status,
        "updated_at": "now()",
    }
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{SUPABASE_URL}/rest/v1/crm_client_workspaces?on_conflict=user_id",
                headers=_headers({"Prefer": "resolution=merge-duplicates,return=representation"}),
                json=payload,
                timeout=10.0,
            )
        if resp.status_code in (200, 201):
            data = resp.json()
            return data[0] if isinstance(data, list) and data else data
        print(f"TWENTY.workspaces: upsert failed {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"TWENTY.workspaces: upsert_workspace failed: {e}")
    return None


async def list_workspaces() -> list[dict]:
    """Admin/ops view: every provisioned workspace (no api_key)."""
    if not _enabled():
        return []
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/crm_client_workspaces",
                headers=_headers(),
                params={
                    "select": "user_id,workspace_id,subdomain,base_url,display_name,status,branding_applied,created_at",
                    "order": "created_at.desc",
                },
                timeout=10.0,
            )
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print(f"TWENTY.workspaces: list_workspaces failed: {e}")
    return []
