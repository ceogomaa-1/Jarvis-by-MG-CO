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
import base64
import hashlib
import hmac
import os

import httpx

from backend.lib.business.connectors.base import ConnectorResult
from backend.lib.business.twenty import workspaces
from backend.lib.business.twenty.client import TwentyClient

# Apex instance used for the programmatic signUp/auth flow (Option A). Per-workspace
# subdomains derive from here. See infra/twenty/AUTO-PROVISION.md.
PROVISION_BASE_URL = os.getenv("TWENTY_PROVISION_BASE_URL", "").strip() or os.getenv("TWENTY_API_URL", "").strip()
SERVICE_EMAIL_DOMAIN = os.getenv("TWENTY_SERVICE_EMAIL_DOMAIN", "jarvismgco.com").strip()
_FAR_FUTURE = "2125-01-01T00:00:00.000Z"


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


# ── Option A: fully programmatic per-user provisioning ───────────────────────────
async def _auth_call(http: httpx.AsyncClient, query: str, variables: dict, *, token: str | None = None,
                     origin: str | None = None, path: str = "/metadata") -> tuple[dict | None, str | None]:
    """One GraphQL call to the auth endpoint, with an optional bearer + origin.

    `path` defaults to /metadata (where this Twenty build serves the auth + api-key
    mutations); callers can pass /graphql for resolvers only on the core schema.
    """
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if origin:
        headers["Origin"] = origin
    try:
        resp = await http.post(f"{PROVISION_BASE_URL}{path}", headers=headers,
                               json={"query": query, "variables": variables}, timeout=45.0)
        body = resp.json()
    except Exception as e:
        return None, f"request failed: {e}"
    if body.get("errors"):
        return None, "; ".join((e.get("message") or str(e)) for e in body["errors"][:3])
    return body.get("data") or {}, None


def _service_password(user_id: str) -> str:
    """Deterministic, recoverable password for the per-user CRM service account.

    Must be STABLE for a given user_id: a retry needs to sign IN to a service account a
    prior (failed) attempt already created — that is what makes provisioning self-healing
    instead of colliding on the (deterministic) service email. Derived via HMAC from a
    server secret; the secret must never change (accounts created under an old secret could
    no longer be recovered and would have to be deleted in Twenty). Shaped to satisfy any
    min-length / charset policy.
    """
    secret = (os.getenv("TWENTY_SERVICE_SECRET") or os.getenv("APP_SECRET")
              or os.getenv("SUPABASE_SERVICE_ROLE_KEY") or "jarvis-crm-service").encode()
    hex_id = (user_id or "").removeprefix("user_").replace("-", "")
    digest = hmac.new(secret, hex_id.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")[:28] + "Aa1!"


def _is_already_exists(err: str) -> bool:
    """True if a signUp error means the service user already exists (prior attempt)."""
    e = (err or "").lower()
    return any(s in e for s in ("already exist", "already taken", "already used", "already registered"))


def _pick_api_key_role(roles: list[dict]) -> str | None:
    """Pick the role id to attach to the backend API key.

    Prefer a role that (a) can be assigned to API keys and (b) has full settings access
    (Admin). Falls back gracefully if a version exposes neither flag.
    """
    if not roles:
        return None
    pool = [r for r in roles if r.get("canBeAssignedToApiKeys")] or roles
    for r in pool:                                   # full-admin role first
        if r.get("canUpdateAllSettings"):
            return r.get("id")
    for r in pool:                                   # else an explicitly-named Admin role
        if (r.get("label") or "").strip().lower() == "admin":
            return r.get("id")
    return pool[0].get("id")


async def _get_agnostic_token(http: httpx.AsyncClient, email: str, password: str) -> tuple[str | None, str | None]:
    """signUp the service account, or signIn if a prior attempt already created it.

    Both signUp and signIn return the same AvailableWorkspacesAndAccessTokensDTO, so the
    workspace-agnostic token is read identically. Self-heal: a prior attempt that got past
    signUp (e.g. failed later at createApiKey) left this exact account behind; re-running
    must recover it, not collide.
    """
    d, e = await _auth_call(http,
        "mutation S($email:String!,$password:String!){ signUp(email:$email,password:$password){ tokens { accessOrWorkspaceAgnosticToken { token } } } }",
        {"email": email, "password": password})
    if not e:
        tok = (((d or {}).get("signUp") or {}).get("tokens") or {}).get("accessOrWorkspaceAgnosticToken", {}).get("token")
        return (tok, None) if tok else (None, "signUp returned no token")
    if not _is_already_exists(e):
        return None, f"signUp: {e}"
    # Recover the pre-existing service account.
    d, e2 = await _auth_call(http,
        "mutation SI($email:String!,$password:String!){ signIn(email:$email,password:$password){ tokens { accessOrWorkspaceAgnosticToken { token } } } }",
        {"email": email, "password": password})
    if e2:
        return None, f"signUp said user exists but signIn recovery failed ({e2}) — likely an orphan from before deterministic passwords; delete {email} in Twenty."
    tok = (((d or {}).get("signIn") or {}).get("tokens") or {}).get("accessOrWorkspaceAgnosticToken", {}).get("token")
    return (tok, None) if tok else (None, "signIn recovery returned no token")


async def _run_signup_flow(user_id: str, display_name: str) -> ConnectorResult:
    """signUp → signUpInNewWorkspace → token → activate → createApiKey → generateApiKeyToken.

    signUp → (signIn recovery) → signUpInNewWorkspace → token → activate → getRoles →
    createApiKey(roleId) → generateApiKeyToken. Returns ConnectorResult(data={base_url,
    api_key, workspace_id, subdomain, service_email, service_secret}). Shapes validated by
    live introspection (see AUTO-PROVISION.md).
    """
    if not PROVISION_BASE_URL:
        return ConnectorResult(ok=False, error="TWENTY_PROVISION_BASE_URL is not set.")
    hex_id = (user_id or "").removeprefix("user_").replace("-", "")
    email = f"crm+{hex_id}@{SERVICE_EMAIL_DOMAIN}"
    password = _service_password(user_id)  # deterministic → retries can sign back in

    async with httpx.AsyncClient() as http:
        # 1. service signUp (or signIn if a prior attempt already created the account)
        agnostic, e = await _get_agnostic_token(http, email, password)
        if e:
            return ConnectorResult(ok=False, error=e)

        # 2. create the new isolated workspace
        d, e = await _auth_call(http,
            "mutation { signUpInNewWorkspace { loginToken { token } workspace { id workspaceUrls { subdomainUrl } } } }",
            {}, token=agnostic)
        if e:
            return ConnectorResult(ok=False, error=f"signUpInNewWorkspace: {e}")
        sw = (d or {}).get("signUpInNewWorkspace") or {}
        login_token = (sw.get("loginToken") or {}).get("token")
        ws = sw.get("workspace") or {}
        ws_id = ws.get("id")
        base_url = ((ws.get("workspaceUrls") or {}).get("subdomainUrl") or "").rstrip("/")
        if not (login_token and base_url):
            return ConnectorResult(ok=False, error="signUpInNewWorkspace returned no workspace url/token")

        # 3. exchange the login token for a workspace-scoped access token
        d, e = await _auth_call(http,
            "mutation T($t:String!,$o:String!){ getAuthTokensFromLoginToken(loginToken:$t, origin:$o){ tokens { accessOrWorkspaceAgnosticToken { token } } } }",
            {"t": login_token, "o": base_url}, origin=base_url)
        if e:
            return ConnectorResult(ok=False, error=f"getAuthTokensFromLoginToken: {e}")
        access = (((d or {}).get("getAuthTokensFromLoginToken") or {}).get("tokens") or {}).get("accessOrWorkspaceAgnosticToken", {}).get("token")
        if not access:
            return ConnectorResult(ok=False, error="token exchange returned no access token")

        # 4. activate + name the workspace (best-effort)
        await _auth_call(http,
            "mutation A($d:ActivateWorkspaceInput!){ activateWorkspace(data:$d){ id } }",
            {"d": {"displayName": display_name or "Jarvis CRM"}}, token=access, origin=base_url)

        # 5. pick a role for the key — this Twenty build requires roleId on createApiKey.
        d, e = await _auth_call(http,
            "query Roles { getRoles { id label canUpdateAllSettings canBeAssignedToApiKeys } }",
            {}, token=access, origin=base_url)
        if e and ("getRoles" in e or "Cannot query field" in e):   # core-schema fallback
            d, e = await _auth_call(http,
                "query Roles { getRoles { id label canUpdateAllSettings canBeAssignedToApiKeys } }",
                {}, token=access, origin=base_url, path="/graphql")
        if e:
            return ConnectorResult(ok=False, error=f"getRoles: {e}")
        role_id = _pick_api_key_role((d or {}).get("getRoles") or [])
        if not role_id:
            return ConnectorResult(ok=False, error="getRoles returned no role assignable to an API key")

        # 6. create an API key record (scoped to the admin role)
        d, e = await _auth_call(http,
            "mutation K($i:CreateApiKeyInput!){ createApiKey(input:$i){ id } }",
            {"i": {"name": "Jarvis Backend", "expiresAt": _FAR_FUTURE, "roleId": role_id}}, token=access, origin=base_url)
        if e:
            return ConnectorResult(ok=False, error=f"createApiKey: {e}")
        api_key_id = ((d or {}).get("createApiKey") or {}).get("id")
        if not api_key_id:
            return ConnectorResult(ok=False, error="createApiKey returned no id")

        # 7. mint the bearer token the backend will store + use
        d, e = await _auth_call(http,
            "mutation G($id:UUID!,$exp:String!){ generateApiKeyToken(apiKeyId:$id, expiresAt:$exp){ token } }",
            {"id": api_key_id, "exp": _FAR_FUTURE}, token=access, origin=base_url)
        if e:
            return ConnectorResult(ok=False, error=f"generateApiKeyToken: {e}")
        token = ((d or {}).get("generateApiKeyToken") or {}).get("token")
        if not token:
            return ConnectorResult(ok=False, error="generateApiKeyToken returned no token")

    subdomain = base_url.split("//", 1)[-1].split(".", 1)[0]
    return ConnectorResult(ok=True, data={
        "base_url": base_url, "api_key": token, "workspace_id": ws_id, "subdomain": subdomain,
        "service_email": email, "service_secret": password,
    })


async def auto_provision_workspace(user_id: str, display_name: str = "Jarvis CRM") -> ConnectorResult:
    """Idempotently create a brand-new user's isolated workspace (Option A) and store it.

    - Idempotent: returns immediately if the user already has a workspace.
    - Tracks state in crm_provisioning_jobs (pending/done/failed) for the UI + retries.
    - On transient failure, bumps the attempt count and leaves status 'pending' (a retry
      will pick it up); after _MAX_PROVISION_ATTEMPTS, marks 'failed' (admin flag). The
      caller (onboarding) runs this best-effort so the user never sees an error.
    """
    if not user_id:
        return ConnectorResult(ok=False, error="user_id is required.")

    if await workspaces.get_workspace(user_id):
        await workspaces.upsert_job(user_id, status="done")
        return ConnectorResult(ok=True, data={"already_provisioned": True})

    job = await workspaces.get_job(user_id)
    attempts = (job.get("attempts") if job else 0) or 0
    await workspaces.upsert_job(user_id, status="pending", attempts=attempts + 1)

    result = await _run_signup_flow(user_id, display_name)
    if not result.ok:
        final = "failed" if attempts + 1 >= workspaces._MAX_PROVISION_ATTEMPTS else "pending"
        await workspaces.upsert_job(user_id, status=final, last_error=result.error)
        if final == "failed":
            print(f"PROVISION ADMIN-FLAG: user {user_id} failed after {attempts + 1} attempts: {result.error}")
        return result

    d = result.data
    row = await workspaces.upsert_workspace(
        user_id, base_url=d["base_url"], api_key=d["api_key"], subdomain=d.get("subdomain"),
        workspace_id=d.get("workspace_id"), display_name=display_name, branding_applied=True,
        service_email=d.get("service_email"), service_secret=d.get("service_secret"),
    )
    if not row:
        await workspaces.upsert_job(user_id, status="pending", last_error="workspace created but DB store failed")
        return ConnectorResult(ok=False, error="Workspace created but could not be saved (check Supabase env).")

    await workspaces.upsert_job(user_id, status="done")
    return ConnectorResult(ok=True, data={"base_url": d["base_url"], "subdomain": d.get("subdomain"), "workspace_id": d.get("workspace_id")})
