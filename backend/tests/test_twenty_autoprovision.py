"""
Auto-provisioning (Option A) orchestration: idempotency, the pending/done/failed job
state machine, retry, and the signUp flow's call sequence. Network + store are mocked.
"""
import pytest

from backend.lib.business.connectors.base import ConnectorResult
from backend.lib.business.twenty import provision, workspaces


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
    store["workspace"]["user_a"] = {"base_url": "https://a.crm.jarvismgco.com", "api_key": "k"}
    called = {"flow": False}

    async def _flow(uid, dn):
        called["flow"] = True
        return ConnectorResult(ok=True, data={})
    monkeypatch.setattr(provision, "_run_signup_flow", _flow)

    res = await provision.auto_provision_workspace("user_a", "Acme")
    assert res.ok and res.data.get("already_provisioned") is True
    assert called["flow"] is False                       # never ran the signup flow
    assert store["job"]["user_a"]["status"] == "done"


@pytest.mark.asyncio
async def test_success_stores_workspace_and_marks_done(store, monkeypatch):
    async def _flow(uid, dn):
        return ConnectorResult(ok=True, data={
            "base_url": "https://acme.crm.jarvismgco.com", "api_key": "wk-key",
            "workspace_id": "ws1", "subdomain": "acme",
            "service_email": "crm+x@jarvismgco.com", "service_secret": "pw"})
    monkeypatch.setattr(provision, "_run_signup_flow", _flow)

    res = await provision.auto_provision_workspace("user_b", "Acme")
    assert res.ok
    ws = store["workspace"]["user_b"]
    assert ws["base_url"] == "https://acme.crm.jarvismgco.com" and ws["api_key"] == "wk-key"
    assert ws["service_secret"] == "pw"                  # creds persisted for future iframe SSO
    assert store["job"]["user_b"]["status"] == "done"


@pytest.mark.asyncio
async def test_transient_failure_stays_pending_and_counts(store, monkeypatch):
    async def _flow(uid, dn):
        return ConnectorResult(ok=False, error="signUp: temporary glitch")
    monkeypatch.setattr(provision, "_run_signup_flow", _flow)

    res = await provision.auto_provision_workspace("user_c", "Acme")
    assert not res.ok
    job = store["job"]["user_c"]
    assert job["status"] == "pending" and job["attempts"] == 1
    assert "user_c" not in store["workspace"]


@pytest.mark.asyncio
async def test_marks_failed_after_max_attempts(store, monkeypatch):
    store["job"]["user_d"] = {"attempts": workspaces._MAX_PROVISION_ATTEMPTS - 1, "status": "pending"}

    async def _flow(uid, dn):
        return ConnectorResult(ok=False, error="signUp: still broken")
    monkeypatch.setattr(provision, "_run_signup_flow", _flow)

    res = await provision.auto_provision_workspace("user_d", "Acme")
    assert not res.ok
    assert store["job"]["user_d"]["status"] == "failed"   # admin-flag state


@pytest.mark.asyncio
async def test_signup_flow_call_sequence(monkeypatch):
    """_run_signup_flow walks signUp → new workspace → token → activate → createApiKey → token."""
    monkeypatch.setattr(provision, "PROVISION_BASE_URL", "https://crm.jarvismgco.com")
    seq = []

    async def _auth_call(http, query, variables, *, token=None, origin=None):
        if "signUp(" in query:
            seq.append("signUp"); return {"signUp": {"tokens": {"accessOrWorkspaceAgnosticToken": {"token": "agnostic"}}}}, None
        if "signUpInNewWorkspace" in query:
            seq.append("newWorkspace")
            return {"signUpInNewWorkspace": {"loginToken": {"token": "lt"},
                    "workspace": {"id": "ws9", "workspaceUrls": {"subdomainUrl": "https://acme.crm.jarvismgco.com"}}}}, None
        if "getAuthTokensFromLoginToken" in query:
            seq.append("exchange"); return {"getAuthTokensFromLoginToken": {"tokens": {"accessOrWorkspaceAgnosticToken": {"token": "access"}}}}, None
        if "activateWorkspace" in query:
            seq.append("activate"); return {"activateWorkspace": {"id": "ws9"}}, None
        if "createApiKey" in query:
            seq.append("createApiKey"); return {"createApiKey": {"id": "ak1"}}, None
        if "generateApiKeyToken" in query:
            seq.append("genToken"); return {"generateApiKeyToken": {"token": "FINAL-KEY"}}, None
        return {}, None
    monkeypatch.setattr(provision, "_auth_call", _auth_call)

    res = await provision._run_signup_flow("user_e", "Acme Realty")
    assert res.ok
    assert seq == ["signUp", "newWorkspace", "exchange", "activate", "createApiKey", "genToken"]
    assert res.data["api_key"] == "FINAL-KEY"
    assert res.data["base_url"] == "https://acme.crm.jarvismgco.com"
    assert res.data["subdomain"] == "acme"
