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

# Shared privileged provisioner (Option 2). When set, every workspace is created by this
# ONE Twenty server-admin account (signIn, not per-user signUp), so the instance can keep
# IS_WORKSPACE_CREATION_LIMITED_TO_SERVER_ADMINS=true — which is what blocks PUBLIC workspace
# creation on the shared apex API (the API every workspace frontend must reach, so the apex
# can't be IP-locked). Data isolation is unchanged: each workspace still gets its own
# workspace-scoped API key, stored per user_id. Unset → legacy per-user signUp (only safe
# when workspace creation is unrestricted). See infra/twenty/AUTO-PROVISION.md.
PROVISIONER_EMAIL = os.getenv("TWENTY_PROVISIONER_EMAIL", "").strip()
_FAR_FUTURE = "2125-01-01T00:00:00.000Z"


async def read_workspace_identity(client: TwentyClient) -> dict:
    """Best-effort read of the workspace id + subdomain + canonical URL the key belongs to.

    `currentWorkspace` lives on the METADATA schema ({base}/metadata), NOT the core data
    API ({base}/graphql) — querying it on /graphql errors ("Cannot query field
    currentWorkspace on type Query"), which silently left register-path rows with a null
    subdomain/workspace_id and an apex base_url (the MG&CO cockpit "invalid response" bug).
    Returns {} if the query isn't supported on this version — provisioning still works, we
    just won't have the identity on record.
    """
    res = await client.query_meta(
        "query CurrentWorkspace { currentWorkspace { id subdomain displayName "
        "workspaceUrls { subdomainUrl } } }",
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
    # updateWorkspace is on the METADATA schema and takes `data: UpdateWorkspaceInput!`
    # (not `input:`); calling it on /graphql silently no-op'd (branding_applied stayed false).
    res = await client.query_meta(
        """
        mutation SetWorkspaceName($data: UpdateWorkspaceInput!) {
          updateWorkspace(data: $data) { id displayName }
        }
        """,
        {"data": {"displayName": display_name}},
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

    # Persist the workspace's REAL subdomain URL, not whatever base_url was passed. A
    # register call often points at the shared apex (https://crm.jarvismgco.com); storing
    # that makes the cockpit embed the apex, which redirects to the real subdomain that
    # tls-check then refuses ("invalid response"). The workspace's own subdomainUrl is the
    # only host that gets an on-demand cert.
    canonical_url = ((identity.get("workspaceUrls") or {}).get("subdomainUrl") or "").rstrip("/")
    if canonical_url:
        base_url = canonical_url

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


def _provisioner_password() -> str:
    """Password for the shared provisioner admin account (explicit env, else derived)."""
    return os.getenv("TWENTY_PROVISIONER_PASSWORD", "").strip() or _service_password("provisioner:" + PROVISIONER_EMAIL)


async def _signin_agnostic(http: httpx.AsyncClient, email: str, password: str) -> tuple[str | None, str | None]:
    """signIn an existing account → workspace-agnostic token (for creating workspaces)."""
    d, e = await _auth_call(http,
        "mutation SI($email:String!,$password:String!){ signIn(email:$email,password:$password){ tokens { accessOrWorkspaceAgnosticToken { token } } } }",
        {"email": email, "password": password})
    if e:
        return None, e
    tok = (((d or {}).get("signIn") or {}).get("tokens") or {}).get("accessOrWorkspaceAgnosticToken", {}).get("token")
    return (tok, None) if tok else (None, "signIn returned no workspace-agnostic token")


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
        # 1. obtain a workspace-agnostic token to create the new workspace with.
        if PROVISIONER_EMAIL:
            # Option 2: one shared server-admin creates every workspace, so public workspace
            # creation can stay locked at the app layer (admins only).
            agnostic, e = await _signin_agnostic(http, PROVISIONER_EMAIL, _provisioner_password())
            if e:
                return ConnectorResult(ok=False, error=f"provisioner signIn ({PROVISIONER_EMAIL}): {e} — is the account created + promoted to server admin? (--init-provisioner + the SQL in AUTO-PROVISION.md)")
        else:
            # Legacy: a per-user service account signs itself up (self-heals if it exists).
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
    # In provisioner mode the workspace is owned by the shared admin; isolation is enforced
    # by the per-workspace api_key, not the account. Record which account owns it (for iframe
    # SSO later); don't duplicate the admin's master password into every row.
    return ConnectorResult(ok=True, data={
        "base_url": base_url, "api_key": token, "workspace_id": ws_id, "subdomain": subdomain,
        "service_email": PROVISIONER_EMAIL or email,
        "service_secret": None if PROVISIONER_EMAIL else password,
    })


async def create_provisioner_account() -> ConnectorResult:
    """One-time: create the shared provisioner account so it can be promoted to server admin.

    Run from Render (where the apex is reachable) BEFORE flipping
    IS_WORKSPACE_CREATION_LIMITED_TO_SERVER_ADMINS=true. Idempotent — signs in if it already
    exists. After this, promote it to a server admin (the SQL in AUTO-PROVISION.md), then flip
    the flag and drop the apex IP-lock.
    """
    if not PROVISION_BASE_URL:
        return ConnectorResult(ok=False, error="TWENTY_PROVISION_BASE_URL is not set.")
    if not PROVISIONER_EMAIL:
        return ConnectorResult(ok=False, error="TWENTY_PROVISIONER_EMAIL is not set.")
    async with httpx.AsyncClient() as http:
        tok, e = await _get_agnostic_token(http, PROVISIONER_EMAIL, _provisioner_password())
    if e:
        return ConnectorResult(ok=False, error=e)
    return ConnectorResult(ok=True, data={
        "email": PROVISIONER_EMAIL, "created_or_existing": bool(tok),
        "next": "Promote to server admin, then set IS_WORKSPACE_CREATION_LIMITED_TO_SERVER_ADMINS=true.",
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
    if not workspaces.valid_user_id(user_id):
        # Fail BEFORE the signUp flow — a malformed id (e.g. a mistyped hex) would otherwise
        # create a Twenty workspace and only then fail the DB write, leaking an orphan that
        # eats a slot under the 5-workspace cap.
        return ConnectorResult(ok=False, error=(
            f"Malformed user_id {user_id!r}: expected user_<32 hex chars> (or a 32-hex uuid). "
            "Check for a typo — refusing to provision so no orphan workspace is created."))

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


# ── Repair / deprovision ─────────────────────────────────────────────────────────
async def repair_workspace_identity(user_id: str) -> ConnectorResult:
    """Reconcile a stored row with the workspace its API key actually points at.

    Fixes rows whose base_url is the bare apex (or whose subdomain/workspace_id are null) —
    the cause of the cockpit "invalid response": the cockpit embeds the apex, the browser is
    redirected to the workspace's real subdomain, and tls-check refuses a cert for a host the
    registry doesn't know. We read the live identity (currentWorkspace on /metadata) with the
    stored key and rewrite base_url → the real subdomainUrl, plus subdomain + workspace_id.
    The api_key is unchanged (it already reaches the workspace). Idempotent.
    """
    row = await workspaces.get_workspace(user_id)
    if not row:
        return ConnectorResult(ok=False, error=f"No active workspace row for {user_id}.")
    client = TwentyClient(row["base_url"], row["api_key"])
    identity = await read_workspace_identity(client)
    if not identity:
        return ConnectorResult(ok=False, error="Could not read the live workspace identity (key invalid or unreachable).")

    canonical_url = ((identity.get("workspaceUrls") or {}).get("subdomainUrl") or "").rstrip("/")
    subdomain = identity.get("subdomain")
    workspace_id = identity.get("id")
    fields: dict = {}
    if canonical_url and canonical_url != (row.get("base_url") or "").rstrip("/"):
        fields["base_url"] = canonical_url
    if subdomain and subdomain != row.get("subdomain"):
        fields["subdomain"] = subdomain
    if workspace_id and workspace_id != row.get("workspace_id"):
        fields["workspace_id"] = workspace_id
    if not fields:
        return ConnectorResult(ok=True, data={"changed": False, "base_url": row.get("base_url"),
                                              "subdomain": row.get("subdomain"), "workspace_id": row.get("workspace_id")})

    ok = await workspaces.update_workspace_fields(user_id, **fields)
    if not ok:
        return ConnectorResult(ok=False, error="Read live identity but failed to persist the repair (check Supabase service-role env).")
    return ConnectorResult(ok=True, data={"changed": True, **{
        "base_url": fields.get("base_url", row.get("base_url")),
        "subdomain": fields.get("subdomain", row.get("subdomain")),
        "workspace_id": fields.get("workspace_id", row.get("workspace_id")),
    }})


async def deprovision_workspace(row: dict, *, delete_remote: bool = True) -> ConnectorResult:
    """Delete one client's Twenty workspace and its registry row, freeing a slot.

    A workspace's own API key can delete only its own workspace (`deleteCurrentWorkspace`
    takes no args and acts on the token's workspace), so this is structurally unable to
    touch any other tenant — the deprovision is self-scoped to `row`. Steps:
      1. deleteCurrentWorkspace via the row's own key (frees the slot under Twenty's cap).
         If the workspace is already gone (key/host dead), we still drop the stale row.
      2. delete the crm_client_workspaces row.
    Returns data={remote_deleted, row_deleted, already_gone}.
    """
    user_id = row.get("user_id")
    base_url, api_key = row.get("base_url"), row.get("api_key")
    remote_deleted = False
    already_gone = False
    if delete_remote and base_url and api_key:
        res = await TwentyClient(base_url, api_key).query_meta(
            "mutation DeleteWorkspace { deleteCurrentWorkspace { id } }",
            action="Delete Twenty workspace",
        )
        if res.ok:
            remote_deleted = True
        else:
            err = (res.error or "").lower()
            # Treat an unreachable/already-deleted workspace as "gone" so a stale row can
            # still be cleaned; surface a genuine auth/permission failure instead.
            if any(s in err for s in ("not found", "does not exist", "no workspace", "unauthor", "404")) \
               or "failed:" in err and any(s in err for s in ("getaddrinfo", "connect", "timed out", "ssl", "certificate")):
                already_gone = True
            else:
                return ConnectorResult(ok=False, error=f"Workspace delete failed for {user_id}: {res.error}")

    row_deleted = await workspaces.delete_workspace_row(user_id) if user_id else False
    return ConnectorResult(ok=True, data={
        "user_id": user_id, "subdomain": row.get("subdomain"), "display_name": row.get("display_name"),
        "remote_deleted": remote_deleted, "already_gone": already_gone, "row_deleted": row_deleted,
    })
