"""
Auto-provisioning (Option A) orchestration: idempotency, the pending/done/failed job
state machine, retry, and the signUp flow's call sequence. Network + store are mocked.
"""
import pytest

from backend.lib.business.connectors.base import ConnectorResult
from backend.lib.business.twenty import provision, workspaces, membership


@pytest.fixture
def stub_membership(monkeypatch):
    """Stub the post-create membership/seed steps so orchestration tests stay offline.

    Returns a dict whose `verified` flag the test can flip to simulate the client being
    (un)addable. Defaults to a clean, verified member.
    """
    cfg = {"verified": True, "status": "member"}

    async def _wipe(client, **kw):
        return {"ok": True, "deleted": {"companies": 599}}

    async def _ensure(client, email):
        return {"ok": True, "status": "invited"}

    async def _verify(client, email):
        return (cfg["verified"], cfg["status"] if cfg["verified"] else "absent")

    monkeypatch.setattr(membership, "wipe_seed_data", _wipe)
    monkeypatch.setattr(membership, "ensure_client_membership", _ensure)
    monkeypatch.setattr(membership, "verify_client_member", _verify)
    return cfg


@pytest.fixture
def store(monkeypatch):
    """In-memory stand-in for the Supabase-backed workspace + job tables."""
    state = {"workspace": {}, "job": {}}

    async def get_workspace(uid):
        return state["workspace"].get(uid)

    async def get_job(uid):
        return state["job"].get(uid)

    async def upsert_job(uid, *, status, attempts=None, last_error=None):
        row = state["job"].setdefault(uid, {"attempts": 0})
        row["status"] = status
        if attempts is not None:
            row["attempts"] = attempts
        if last_error is not None:
            row["last_error"] = last_error
        return True

    async def upsert_workspace(uid, **kw):
        row = {"user_id": uid, **kw}
        state["workspace"][uid] = row
        return row

    monkeypatch.setattr(workspaces, "get_workspace", get_workspace)
    monkeypatch.setattr(workspaces, "get_job", get_job)
    monkeypatch.setattr(workspaces, "upsert_job", upsert_job)
    monkeypatch.setattr(workspaces, "upsert_workspace", upsert_workspace)
    monkeypatch.setattr(provision.workspaces, "get_workspace", get_workspace)
    monkeypatch.setattr(provision.workspaces, "get_job", get_job)
    monkeypatch.setattr(provision.workspaces, "upsert_job", upsert_job)
    monkeypatch.setattr(provision.workspaces, "upsert_workspace", upsert_workspace)
    return state


@pytest.mark.asyncio
async def test_idempotent_when_already_provisioned(store, monkeypatch):
    store["workspace"]["user_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"] = {"base_url": "https://a.crm.jarvismgco.com", "api_key": "k"}
    called = {"flow": False}

    async def _flow(uid, dn):
        called["flow"] = True
        return ConnectorResult(ok=True, data={})
    monkeypatch.setattr(provision, "_run_signup_flow", _flow)

    res = await provision.auto_provision_workspace("user_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "Acme")
    assert res.ok and res.data.get("already_provisioned") is True
    assert called["flow"] is False                       # never ran the signup flow
    assert store["job"]["user_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"]["status"] == "done"


@pytest.mark.asyncio
async def test_success_stores_workspace_and_marks_done(store, stub_membership, monkeypatch):
    async def _flow(uid, dn):
        return ConnectorResult(ok=True, data={
            "base_url": "https://acme.crm.jarvismgco.com", "api_key": "wk-key",
            "workspace_id": "ws1", "subdomain": "acme",
            "service_email": "crm+x@jarvismgco.com", "service_secret": "pw"})
    monkeypatch.setattr(provision, "_run_signup_flow", _flow)

    # client_email is REQUIRED now — and the client is added + verified before 'done'.
    res = await provision.auto_provision_workspace(
        "user_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "Acme", client_email="jon@acme.com")
    assert res.ok
    ws = store["workspace"]["user_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"]
    assert ws["base_url"] == "https://acme.crm.jarvismgco.com" and ws["api_key"] == "wk-key"
    assert ws["service_secret"] == "pw"                  # creds persisted for future iframe SSO
    assert store["job"]["user_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"]["status"] == "done"


@pytest.mark.asyncio
async def test_no_client_email_does_not_mark_done(store, stub_membership, monkeypatch):
    """A workspace with no client member must NOT be reported complete."""
    async def _flow(uid, dn):
        return ConnectorResult(ok=True, data={
            "base_url": "https://acme.crm.jarvismgco.com", "api_key": "wk-key",
            "workspace_id": "ws1", "subdomain": "acme"})
    monkeypatch.setattr(provision, "_run_signup_flow", _flow)

    res = await provision.auto_provision_workspace("user_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "Acme")  # no client_email
    assert not res.ok
    # Workspace row was still stored (it exists), but the job stays pending with a reason.
    assert store["workspace"]["user_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"]["base_url"]
    job = store["job"]["user_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"]
    assert job["status"] == "pending" and "client_email" in (job.get("last_error") or "")


@pytest.mark.asyncio
async def test_unverified_member_stays_pending(store, stub_membership, monkeypatch):
    """If the client can't be confirmed as a member, the job stays pending (never 'done')."""
    stub_membership["verified"] = False
    async def _flow(uid, dn):
        return ConnectorResult(ok=True, data={
            "base_url": "https://acme.crm.jarvismgco.com", "api_key": "wk-key",
            "workspace_id": "ws1", "subdomain": "acme"})
    monkeypatch.setattr(provision, "_run_signup_flow", _flow)

    res = await provision.auto_provision_workspace(
        "user_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "Acme", client_email="jon@acme.com")
    assert not res.ok
    assert store["job"]["user_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"]["status"] == "pending"


@pytest.mark.asyncio
async def test_transient_failure_stays_pending_and_counts(store, monkeypatch):
    async def _flow(uid, dn):
        return ConnectorResult(ok=False, error="signUp: temporary glitch")
    monkeypatch.setattr(provision, "_run_signup_flow", _flow)

    res = await provision.auto_provision_workspace("user_cccccccccccccccccccccccccccccccc", "Acme")
    assert not res.ok
    job = store["job"]["user_cccccccccccccccccccccccccccccccc"]
    assert job["status"] == "pending" and job["attempts"] == 1
    assert "user_cccccccccccccccccccccccccccccccc" not in store["workspace"]


@pytest.mark.asyncio
async def test_marks_failed_after_max_attempts(store, monkeypatch):
    store["job"]["user_dddddddddddddddddddddddddddddddd"] = {"attempts": workspaces._MAX_PROVISION_ATTEMPTS - 1, "status": "pending"}

    async def _flow(uid, dn):
        return ConnectorResult(ok=False, error="signUp: still broken")
    monkeypatch.setattr(provision, "_run_signup_flow", _flow)

    res = await provision.auto_provision_workspace("user_dddddddddddddddddddddddddddddddd", "Acme")
    assert not res.ok
    assert store["job"]["user_dddddddddddddddddddddddddddddddd"]["status"] == "failed"   # admin-flag state


def _flow_auth_call(seq, *, captured=None, signup_exists=False):
    """Build a fake _auth_call that walks the full provisioning GraphQL sequence."""
    async def _auth_call(http, query, variables, *, token=None, origin=None, path="/metadata"):
        if "signUp(" in query:
            seq.append("signUp")
            if signup_exists:
                return None, "User already exists"
            return {"signUp": {"tokens": {"accessOrWorkspaceAgnosticToken": {"token": "agnostic"}}}}, None
        if "signIn(" in query:
            seq.append("signIn"); return {"signIn": {"tokens": {"accessOrWorkspaceAgnosticToken": {"token": "agnostic"}}}}, None
        if "signUpInNewWorkspace" in query:
            seq.append("newWorkspace")
            return {"signUpInNewWorkspace": {"loginToken": {"token": "lt"},
                    "workspace": {"id": "ws9", "workspaceUrls": {"subdomainUrl": "https://acme.crm.jarvismgco.com"}}}}, None
        if "getAuthTokensFromLoginToken" in query:
            seq.append("exchange"); return {"getAuthTokensFromLoginToken": {"tokens": {"accessOrWorkspaceAgnosticToken": {"token": "access"}}}}, None
        if "activateWorkspace" in query:
            seq.append("activate"); return {"activateWorkspace": {"id": "ws9"}}, None
        if "getRoles" in query:
            seq.append("getRoles"); return {"getRoles": [
                {"id": "role-member", "label": "Member", "canUpdateAllSettings": False, "canBeAssignedToApiKeys": True},
                {"id": "role-admin", "label": "Admin", "canUpdateAllSettings": True, "canBeAssignedToApiKeys": True},
            ]}, None
        if "createApiKey" in query:
            seq.append("createApiKey")
            if captured is not None:
                captured["roleId"] = variables["i"].get("roleId")
            return {"createApiKey": {"id": "ak1"}}, None
        if "generateApiKeyToken" in query:
            seq.append("genToken"); return {"generateApiKeyToken": {"token": "FINAL-KEY"}}, None
        return {}, None
    return _auth_call


@pytest.mark.asyncio
async def test_signup_flow_call_sequence(monkeypatch):
    """Full walk: signUp → new workspace → token → activate → getRoles → createApiKey(roleId) → token."""
    monkeypatch.setattr(provision, "PROVISION_BASE_URL", "https://crm.jarvismgco.com")
    seq, captured = [], {}
    monkeypatch.setattr(provision, "_auth_call", _flow_auth_call(seq, captured=captured))

    res = await provision._run_signup_flow("user_e", "Acme Realty")
    assert res.ok
    assert seq == ["signUp", "newWorkspace", "exchange", "activate", "getRoles", "createApiKey", "genToken"]
    assert captured["roleId"] == "role-admin"            # full-settings role chosen for the key
    assert res.data["api_key"] == "FINAL-KEY"
    assert res.data["base_url"] == "https://acme.crm.jarvismgco.com"
    assert res.data["subdomain"] == "acme"


@pytest.mark.asyncio
async def test_signup_flow_self_heals_existing_service_user(monkeypatch):
    """If signUp says the user exists (prior failed attempt), recover via signIn and continue."""
    monkeypatch.setattr(provision, "PROVISION_BASE_URL", "https://crm.jarvismgco.com")
    seq = []
    monkeypatch.setattr(provision, "_auth_call", _flow_auth_call(seq, signup_exists=True))

    res = await provision._run_signup_flow("user_f", "Acme Realty")
    assert res.ok
    assert seq[:3] == ["signUp", "signIn", "newWorkspace"]   # signUp collided → signIn recovered
    assert res.data["api_key"] == "FINAL-KEY"


@pytest.mark.asyncio
async def test_provisioner_mode_signs_in_as_admin(monkeypatch):
    """With TWENTY_PROVISIONER_EMAIL set, the shared admin signs IN (no per-user signUp)."""
    monkeypatch.setattr(provision, "PROVISION_BASE_URL", "https://crm.jarvismgco.com")
    monkeypatch.setattr(provision, "PROVISIONER_EMAIL", "crm-provisioner@jarvismgco.com")
    seq, captured = [], {}
    monkeypatch.setattr(provision, "_auth_call", _flow_auth_call(seq, captured=captured))

    res = await provision._run_signup_flow("user_g", "Acme Realty")
    assert res.ok
    assert seq[0] == "signIn" and "signUp" not in seq    # admin signs in; no public signup
    assert seq == ["signIn", "newWorkspace", "exchange", "activate", "getRoles", "createApiKey", "genToken"]
    assert captured["roleId"] == "role-admin"
    assert res.data["service_email"] == "crm-provisioner@jarvismgco.com"
    assert res.data["service_secret"] is None            # don't copy the master pw per row


def test_service_password_is_deterministic_and_policy_safe():
    a = provision._service_password("user_1a85bf0d3508480cb1aa0d4b602b4de5")
    b = provision._service_password("1a85bf0d-3508-480c-b1aa-0d4b602b4de5")  # same id, hyphenated
    c = provision._service_password("user_ffffffffffffffffffffffffffffffff")
    assert a == b and a != c                               # stable per user, unique across users
    assert len(a) >= 12 and a.endswith("Aa1!")             # min-length + charset policy


def test_pick_api_key_role_prefers_admin():
    roles = [
        {"id": "m", "label": "Member", "canUpdateAllSettings": False, "canBeAssignedToApiKeys": True},
        {"id": "a", "label": "Admin", "canUpdateAllSettings": True, "canBeAssignedToApiKeys": True},
    ]
    assert provision._pick_api_key_role(roles) == "a"
    # skips roles that can't back an API key
    assert provision._pick_api_key_role([
        {"id": "x", "label": "Admin", "canUpdateAllSettings": True, "canBeAssignedToApiKeys": False},
        {"id": "y", "label": "Ops", "canUpdateAllSettings": False, "canBeAssignedToApiKeys": True},
    ]) == "y"
    assert provision._pick_api_key_role([]) is None
