"""
Client workspace membership + seed-data hygiene for per-client Twenty workspaces.

THE BUG THIS EXISTS TO KILL: provisioning created each workspace under a *service*
identity (crm+<hex>@jarvismgco.com) and never added the real client as a workspace
member. The client then logs in at their subdomain and Twenty says "User does not
have access to this workspace" + prompts Sign up. Provisioning was still marked
`done`, so the lockout was invisible.

This module:
  • adds the real client email as a workspace member (invitation),
  • verifies the client is actually present (member or pending invite),
  • wipes Twenty's demo/seed records from a freshly-created workspace,
  • lists members for the cross-workspace audit.

All operations use the workspace-scoped API key (already stored in the registry),
which authenticates as a workspace admin — so they are structurally confined to that
one tenant. GraphQL mutation shapes for invitations/roles vary across Twenty versions;
we try the current names with documented fallbacks and NEVER claim success blindly —
`verify_client_member` is the gate the provisioner trusts, not the invite call alone.
"""
from backend.lib.business.twenty.client import TwentyClient

# Known Twenty demo/seed company names (the standard sample dataset). Used to wipe seed
# precisely when we must preserve real records. A brand-new workspace can also be wiped
# wholesale (wipe_all=True) since it has no real data yet.
DEMO_COMPANY_HINTS = {
    "airbnb", "aircall", "algolia", "amazon", "apple", "atlassian", "blissfields",
    "datadog", "dribbble", "facebook", "figma", "github", "google", "linkedin",
    "linear", "mailchimp", "meta", "microsoft", "netflix", "notion", "openai",
    "qonto", "salesforce", "sequoia", "shopify", "slack", "snowflake", "spacex",
    "spotify", "stripe", "tesla", "twenty", "uber", "vercel", "x (twitter)", "twitter",
}


# ── member listing (audit + verify) ───────────────────────────────────────────────
async def workspace_member_emails(client: TwentyClient) -> tuple[set[str], str | None]:
    """Return the set of lowercased member emails in the workspace, or (set(), error).

    workspaceMembers is a core-data object in Twenty; its email field is `userEmail`.
    """
    res = await client.query_data(
        "query Members { workspaceMembers { edges { node { id userEmail } } } }",
        action="List workspace members",
    )
    if not res.ok:
        return set(), res.error
    edges = ((res.data or {}).get("workspaceMembers") or {}).get("edges") or []
    emails = {
        (e.get("node") or {}).get("userEmail", "").strip().lower()
        for e in edges
        if (e.get("node") or {}).get("userEmail")
    }
    return emails, None


async def pending_invite_emails(client: TwentyClient) -> set[str]:
    """Best-effort set of emails with a pending (un-accepted) invitation. Empty on any error
    or if the query isn't supported on this Twenty version."""
    for query in (
        "query Inv { findWorkspaceInvitations { id email } }",
        "query Inv { workspaceInvitations { edges { node { id email } } } }",
    ):
        res = await client.query_data(query, action="List pending invitations")
        if not res.ok:
            continue
        data = res.data or {}
        if isinstance(data.get("findWorkspaceInvitations"), list):
            return {i.get("email", "").strip().lower() for i in data["findWorkspaceInvitations"] if i.get("email")}
        edges = ((data.get("workspaceInvitations") or {}).get("edges")) or []
        if edges:
            return {(e.get("node") or {}).get("email", "").strip().lower() for e in edges if (e.get("node") or {}).get("email")}
    return set()


async def verify_client_member(client: TwentyClient, client_email: str) -> tuple[bool, str]:
    """True iff the client email is a workspace member OR has a pending invitation.

    Returns (ok, status) where status ∈ {"member", "invited", "absent", "<error>"}.
    This is the gate the provisioner trusts before marking a job done.
    """
    email = (client_email or "").strip().lower()
    if not email:
        return False, "no client_email"
    members, err = await workspace_member_emails(client)
    if err:
        return False, f"member lookup failed: {err}"
    if email in members:
        return True, "member"
    if email in await pending_invite_emails(client):
        return True, "invited"
    return False, "absent"


# ── adding the client as a member ──────────────────────────────────────────────────
async def ensure_client_membership(client: TwentyClient, client_email: str) -> dict:
    """Invite the client email into the workspace (idempotent). Returns a status dict.

    Sends a workspace invitation so the client receives a password-setup link and lands
    in their own workspace as a member. Tries the current Twenty mutation name with a
    fallback. If the client is already present, returns ok without re-inviting.
    """
    email = (client_email or "").strip()
    if not email:
        return {"ok": False, "status": "no client_email", "error": "client_email is required"}

    ok, status = await verify_client_member(client, email)
    if ok:
        return {"ok": True, "status": status, "already": True}

    last_err = None
    for query, variables, extract in (
        # current shape
        ("mutation Inv($emails:[String!]!){ createWorkspaceInvitations(emails:$emails){ id email } }",
         {"emails": [email]}, "createWorkspaceInvitations"),
        # older shape
        ("mutation Inv($emails:[String!]!){ sendInvitations(emails:$emails){ success result { id email } errors } }",
         {"emails": [email]}, "sendInvitations"),
    ):
        res = await client.query_data(query, variables, action="Invite client to workspace")
        if res.ok:
            return {"ok": True, "status": "invited", "mutation": extract}
        last_err = res.error

    return {"ok": False, "status": "invite_failed", "error": last_err}


# ── seed/demo data wipe ─────────────────────────────────────────────────────────────
async def wipe_seed_data(client: TwentyClient, *, wipe_all: bool = False, max_per_object: int = 2000) -> dict:
    """Delete Twenty's demo/seed records so the client opens a clean CRM.

    wipe_all=False (default): only delete companies whose name matches the known demo set
      (preserves anything real) — safe on a workspace that may already hold real records.
    wipe_all=True: delete ALL records across core objects — only safe on a brand-new,
      never-used workspace (e.g. immediately after provisioning, before the client logs in).
    Returns per-object deleted counts.
    """
    from backend.lib.business.twenty import introspect as _intro
    from backend.lib.business.twenty import tools as _tools

    schema_res = await _intro.introspect(client)
    if not schema_res.ok:
        return {"ok": False, "error": f"introspect failed: {schema_res.error}"}
    schema = schema_res.data

    def _cap(s: str) -> str:
        return s[:1].upper() + s[1:]

    async def _delete_one(singular: str, rid: str) -> bool:
        m = f"mutation Del($id: UUID!) {{ delete{_cap(singular)}(id: $id) {{ id }} }}"
        r = await client.query_data(m, {"id": rid}, action=f"Delete {singular}")
        return r.ok

    # Objects to clean, in FK-safe order (children before parents).
    targets = ["note", "task", "opportunity", "person", "company"]
    deleted: dict[str, int] = {}

    for alias in targets:
        obj = schema.obj(alias) if hasattr(schema, "obj") else None
        if not obj:
            continue
        plural = obj.name_plural
        singular = obj.name_singular
        # company nodes need their name for demo-matching; others just need id.
        node_fields = "id name { ... on FullName { firstName lastName } }" if alias == "person" else "id name"
        try:
            nodes = await _tools._page(client, plural, node_fields if alias in ("company", "person") else "id", max_records=max_per_object)
        except Exception as e:
            deleted[plural] = 0
            print(f"WIPE_SEED: list {plural} failed: {e}")
            continue

        count = 0
        for n in nodes:
            rid = n.get("id")
            if not rid:
                continue
            if alias == "company" and not wipe_all:
                name = (n.get("name") or "")
                if isinstance(name, dict):
                    name = ""
                if name.strip().lower() not in DEMO_COMPANY_HINTS:
                    continue  # keep non-demo companies
            elif alias != "company" and not wipe_all:
                # In demo-only mode we only target the sample companies; leave people/opps/etc.
                continue
            if await _delete_one(singular, rid):
                count += 1
        deleted[plural] = count

    return {"ok": True, "deleted": deleted, "wipe_all": wipe_all}
