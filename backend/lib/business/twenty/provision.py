"""
Per-client Jarvis CRM workspace provisioning (Phase 2).

A new client gets their OWN data-isolated Twenty workspace. The repeatable path:

    create workspace  →  apply Jarvis CRM branding/defaults  →  generate that
    workspace's API key  →  store it against the client (user_id) so Jarvis talks
    to the right workspace per client.

This module owns the parts Jarvis can do over the API: verify a workspace API key,
read the workspace identity (id + subdomain), push workspace-level Jarvis CRM
defaults (display name), and register the workspace against a user_id.

Two provisioning modes (see backend/scripts/provision_twenty_workspace.py):

  • register  (reliable, recommended): the workspace + API key are created in the
    Twenty admin UI (Settings → API & Webhooks), then this registers the key against
    a Jarvis user. Works on every Twenty version.

  • auto (best-effort): attempt programmatic workspace creation via Twenty's GraphQL.
    The exact sign-up/createWorkspace + token mutations are version-sensitive, so this
    path is gated and must be live-verified against the deployed Twenty version before
    relying on it. `register` is the supported path until then.

Isolation note: a workspace API key is scoped to ONE Twenty workspace. Storing it
against a single user_id means that user can only ever read/write that workspace's
records — that is the data-isolation boundary (proven in tests/test_twenty_workspaces.py).
"""
from backend.lib.business.connectors.base import ConnectorResult
from backend.lib.business.twenty import workspaces
from backend.lib.business.twenty.client import TwentyClient


async def read_workspace_identity(client: TwentyClient) -> dict:
    """Best-effort read of the workspace id + subdomain the API key belongs to.

    Returns {} if the query isn't supported on this version — provisioning still works,
    we just won't have the workspace_id/subdomain on record.
    """
    res = await client.query_data(
        "query CurrentWorkspace { currentWorkspace { id subdomain displayName } }",
        action="Read current workspace",
    )
    if res.ok:
        return (res.data or {}).get("currentWorkspace") or {}
    return {}


async def apply_branding_defaults(client: TwentyClient, display_name: str) -> bool:
    """Push workspace-level Jarvis CRM defaults (display name).

    Visual branding (app name, logo, favicon, theme) is global — baked into the
    white-labeled image (see infra/twenty/branding/), so it applies to every
    workspace automatically. The only per-workspace default is the client-facing
    display name. Best-effort: returns False if the mutation isn't available.
    """
    if not display_name:
        return False
    res = await client.query_data(
        """
        mutation SetWorkspaceName($displayName: String!) {
          updateWorkspace(input: { displayName: $displayName }) { id displayName }
        }
        """,
        {"displayName": display_name},
        action="Apply Jarvis CRM workspace defaults",
    )
    return res.ok


async def register_workspace(
    user_id: str,
    *,
    base_url: str,
    api_key: str,
    subdomain: str | None = None,
    display_name: str | None = None,
    apply_branding: bool = True,
) -> ConnectorResult:
    """Verify a workspace API key works, then register it against a user_id.

    This is the supported provisioning path. Steps:
      1. Build a client from the given base_url + api_key and ping it (proves the key
         is valid and the workspace is reachable).
      2. Read the workspace identity (id/subdomain) for our records.
      3. Optionally push Jarvis CRM display-name defaults.
      4. Persist the mapping in crm_client_workspaces (keyed by user_id).
    """
    if not user_id:
        return ConnectorResult(ok=False, error="user_id is required to register a workspace.")
    if not base_url or not api_key:
        return ConnectorResult(ok=False, error="base_url and api_key are required.")

    client = TwentyClient(base_url, api_key)

    ping = await client.ping()
    if not ping.ok:
        return ConnectorResult(ok=False, error=f"Could not reach the workspace with that key: {ping.error}")

    identity = await read_workspace_identity(client)
    workspace_id = identity.get("id")
    subdomain = subdomain or identity.get("subdomain")
    display_name = display_name or identity.get("displayName")

    branding_applied = False
    if apply_branding and display_name:
        branding_applied = await apply_branding_defaults(client, display_name)

    row = await workspaces.upsert_workspace(
        user_id,
        base_url=base_url,
        api_key=api_key,
        subdomain=subdomain,
        workspace_id=workspace_id,
        display_name=display_name,
        branding_applied=branding_applied,
    )
    if not row:
        return ConnectorResult(ok=False, error="Workspace verified but could not be saved to the registry (check Supabase service-role env).")

    return ConnectorResult(
        ok=True,
        data={
            "user_id": user_id,
            "workspace_id": workspace_id,
            "subdomain": subdomain,
            "base_url": base_url.rstrip("/"),
            "display_name": display_name,
            "branding_applied": branding_applied,
        },
    )
