"""
Per-client Rue CRM workspace registry (Phase 2 multi-tenant).

Phase 1 talked to ONE shared Twenty instance from env. Phase 2 gives each client
their own data-isolated workspace (Twenty native multi-workspace, subdomain-routed)
and stores that workspace's base URL + API key here, keyed by Rue user_id, so the
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


def _hex_id(user_id: str) -> str:
    """Strip the user_ prefix and any dashes → the raw 32-char hex (or whatever was given)."""
    return (user_id or "").strip().removeprefix("user_").replace("-", "")


def valid_user_id(user_id: str) -> bool:
    """True iff user_id is a well-formed Rue id (user_<32 hex> or a 32-hex uuid).

    A malformed id (e.g. a hand-typed hex with a transposed/extra digit) must be caught
    BEFORE the provisioning flow runs — otherwise the signUp flow creates a Twenty
    workspace under the bad id and only then fails the DB write, leaking an orphan
    workspace that consumes a slot under Twenty's cap.
    """
    hid = _hex_id(user_id).lower()
    return len(hid) == 32 and all(c in "0123456789abcdef" for c in hid)


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


async def get_service_creds(user_id: str) -> dict:
    """Service-role only: the workspace's service-account email + secret (for signing in as
    the workspace owner to invite the client). Returns {} if unavailable. Never expose."""
    if not _enabled():
        return {}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/crm_client_workspaces",
                headers=_headers(),
                params={"select": "service_email,service_secret,base_url,subdomain,workspace_id",
                        "user_id": f"eq.{_user_id_to_uuid(user_id)}", "limit": "1"},
                timeout=10.0,
            )
        if resp.status_code == 200:
            rows = resp.json()
            return rows[0] if rows else {}
    except Exception as e:
        print(f"TWENTY.workspaces: get_service_creds failed: {e}")
    return {}


async def domain_is_provisioned(host: str) -> bool:
    """True iff `host` (e.g. acme.crm.jarvismgco.com) belongs to a provisioned workspace.

    Backs Caddy's on-demand-TLS `ask` so certs are only minted for real workspaces.
    Matched against the stored base_url; host is pre-validated by the caller.
    """
    host = (host or "").strip().lower()
    if not _enabled() or not host:
        return False
    sub = host.split(".", 1)[0]
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/crm_client_workspaces",
                headers=_headers(),
                params={"select": "user_id", "status": "eq.active",
                        "or": f"(base_url.ilike.*{host}*,subdomain.eq.{sub})", "limit": "1"},
                timeout=5.0,
            )
        if resp.status_code == 200:
            return bool(resp.json())
    except Exception as e:
        print(f"TWENTY.workspaces: domain_is_provisioned failed: {e}")
    return False


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
    service_email: str | None = None,
    service_secret: str | None = None,
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
    if service_email is not None:
        payload["service_email"] = service_email
    if service_secret is not None:
        payload["service_secret"] = service_secret
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


async def update_workspace_fields(user_id: str, **fields) -> bool:
    """PATCH selected columns on a user's workspace row (e.g. repair base_url/subdomain).

    Unlike upsert_workspace this touches only the given fields, so it can't clobber the
    api_key/display_name while fixing identity. Returns True on success.
    """
    if not _enabled() or not user_id or not fields:
        return False
    payload = {**fields, "updated_at": "now()"}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.patch(
                f"{SUPABASE_URL}/rest/v1/crm_client_workspaces",
                headers=_headers({"Prefer": "return=minimal"}),
                params={"user_id": f"eq.{_user_id_to_uuid(user_id)}"},
                json=payload,
                timeout=10.0,
            )
        return resp.status_code in (200, 204)
    except Exception as e:
        print(f"TWENTY.workspaces: update_workspace_fields failed: {e}")
        return False


async def delete_workspace_row(user_id: str) -> bool:
    """Delete a user's workspace row from the registry (used by deprovision). Idempotent."""
    if not _enabled() or not user_id:
        return False
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.delete(
                f"{SUPABASE_URL}/rest/v1/crm_client_workspaces",
                headers=_headers({"Prefer": "return=minimal"}),
                params={"user_id": f"eq.{_user_id_to_uuid(user_id)}"},
                timeout=10.0,
            )
        return resp.status_code in (200, 204)
    except Exception as e:
        print(f"TWENTY.workspaces: delete_workspace_row failed: {e}")
        return False


async def list_workspaces_with_keys() -> list[dict]:
    """Internal/ops: every workspace row INCLUDING api_key (needed to deprovision a tenant).

    Service-role only — the key is a secret. Never expose this to end users.
    """
    if not _enabled():
        return []
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/crm_client_workspaces",
                headers=_headers(),
                params={"select": "user_id,workspace_id,subdomain,base_url,api_key,display_name,status,created_at",
                        "order": "created_at.asc"},
                timeout=10.0,
            )
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print(f"TWENTY.workspaces: list_workspaces_with_keys failed: {e}")
    return []


_MAX_PROVISION_ATTEMPTS = 5


async def get_job(user_id: str) -> dict | None:
    """Provisioning job state for a user, or None. {status, attempts, last_error}."""
    if not _enabled():
        return None
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/crm_provisioning_jobs",
                headers=_headers(),
                params={"select": "status,attempts,last_error", "user_id": f"eq.{_user_id_to_uuid(user_id)}", "limit": "1"},
                timeout=10.0,
            )
        if resp.status_code == 200:
            rows = resp.json()
            return rows[0] if rows else None
    except Exception as e:
        print(f"TWENTY.workspaces: get_job failed: {e}")
    return None


async def upsert_job(user_id: str, *, status: str, attempts: int | None = None, last_error: str | None = None) -> bool:
    if not _enabled():
        return False
    payload = {"user_id": _user_id_to_uuid(user_id), "status": status, "updated_at": "now()"}
    if attempts is not None:
        payload["attempts"] = attempts
    if last_error is not None:
        payload["last_error"] = last_error[:1000]
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{SUPABASE_URL}/rest/v1/crm_provisioning_jobs?on_conflict=user_id",
                headers=_headers({"Prefer": "resolution=merge-duplicates,return=minimal"}),
                json=payload,
                timeout=10.0,
            )
        return resp.status_code in (200, 201, 204)
    except Exception as e:
        print(f"TWENTY.workspaces: upsert_job failed: {e}")
        return False


async def is_pending(user_id: str) -> bool:
    """True if provisioning is in flight (job pending and no active workspace yet)."""
    if await get_workspace(user_id):
        return False
    job = await get_job(user_id)
    return bool(job and job.get("status") == "pending")


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
