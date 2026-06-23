"""Deprovision + identity-repair: self-scoped workspace deletion, registry cleanup, and the
apex→subdomain repair that fixes the cockpit "invalid response". Network + store are mocked."""
import pytest

from backend.lib.business.connectors.base import ConnectorResult
from backend.lib.business.twenty import provision, workspaces
from backend.scripts import deprovision_twenty_workspace as cli


# ── keep-list parsing (CLI) ──────────────────────────────────────────────────────
def test_parse_keep_normalises_and_dedupes():
    keep = cli._parse_keep(["user_3363afdc9bca4b88893cf535c62a6687",
                            "7ec1625c-6165-440b-b239-e72710dc5400,  "])
    # user_<hex> and dashed-uuid both normalise to the stored uuid form
    assert "3363afdc-9bca-4b88-893c-f535c62a6687" in keep
    assert "7ec1625c-6165-440b-b239-e72710dc5400" in keep
    # same id in two forms collapses to one
    assert cli._parse_keep(["user_1a85bf0d3508480cb1aa0d4b602b4de5",
                            "1a85bf0d-3508-480c-b1aa-0d4b602b4de5"]).__len__() == 1


# ── user_id validation (typo guard) ──────────────────────────────────────────────
def test_valid_user_id_accepts_canonical_forms():
    assert workspaces.valid_user_id("user_7ec1625c6165440bbb4239e72710dc54")
    assert workspaces.valid_user_id("7ec1625c-6165-440b-bb42-39e72710dc54")
    assert workspaces.valid_user_id("7ec1625c6165440bbb4239e72710dc54")


def test_valid_user_id_rejects_typos():
    # extra digit (33 hex) — the exact Render footgun
    assert not workspaces.valid_user_id("user_7ec16225c6165440bbb4239e72710dc54")
    assert not workspaces.valid_user_id("user_7ec1625c")          # too short
    assert not workspaces.valid_user_id("user_zzzz1625c6165440bbb4239e72710dc54")  # non-hex
    assert not workspaces.valid_user_id("")


@pytest.mark.asyncio
async def test_auto_provision_refuses_malformed_id_before_creating(monkeypatch):
    ran = {"flow": False}

    async def _flow(uid, dn):
        ran["flow"] = True
        return ConnectorResult(ok=True, data={})

    async def _get_ws(uid):
        return None

    monkeypatch.setattr(provision, "_run_signup_flow", _flow)
    monkeypatch.setattr(provision.workspaces, "get_workspace", _get_ws)

    res = await provision.auto_provision_workspace("user_7ec16225c6165440bbb4239e72710dc54", "PPRE")
    assert not res.ok and "Malformed user_id" in res.error
    assert ran["flow"] is False          # never reached the workspace-creating flow → no orphan


# ── deprovision_workspace: self-scoped delete + row cleanup ───────────────────────
@pytest.mark.asyncio
async def test_deprovision_uses_the_rows_own_key_then_drops_row(monkeypatch):
    used = {}

    class FakeClient:
        def __init__(self, base_url, api_key):
            used["base_url"], used["api_key"] = base_url, api_key

        async def query_meta(self, query, action=""):
            used["mutation"] = query
            return ConnectorResult(ok=True, data={"deleteCurrentWorkspace": {"id": "ws-junk"}})

    deleted = {}

    async def _delete_row(uid):
        deleted["uid"] = uid
        return True

    monkeypatch.setattr(provision, "TwentyClient", FakeClient)
    monkeypatch.setattr(provision.workspaces, "delete_workspace_row", _delete_row)

    row = {"user_id": "u-junk", "base_url": "https://junk.crm.jarvismgco.com",
           "api_key": "junk-key", "subdomain": "junk", "display_name": "Junk RE"}
    res = await provision.deprovision_workspace(row)

    assert res.ok and res.data["remote_deleted"] and res.data["row_deleted"]
    # it talked to the workspace's OWN host/key — structurally can't reach another tenant
    assert used["base_url"] == "https://junk.crm.jarvismgco.com" and used["api_key"] == "junk-key"
    assert "deleteCurrentWorkspace" in used["mutation"]
    assert deleted["uid"] == "u-junk"


@pytest.mark.asyncio
async def test_deprovision_cleans_stale_row_when_workspace_already_gone(monkeypatch):
    class FakeClient:
        def __init__(self, *a):
            pass

        async def query_meta(self, query, action=""):
            return ConnectorResult(ok=False, error="Delete failed: [Errno 11001] getaddrinfo failed")

    dropped = {"n": 0}

    async def _delete_row(uid):
        dropped["n"] += 1
        return True

    monkeypatch.setattr(provision, "TwentyClient", FakeClient)
    monkeypatch.setattr(provision.workspaces, "delete_workspace_row", _delete_row)

    res = await provision.deprovision_workspace(
        {"user_id": "u-dead", "base_url": "https://dead.crm.jarvismgco.com", "api_key": "k"})
    assert res.ok and res.data["already_gone"] and res.data["row_deleted"]
    assert dropped["n"] == 1


@pytest.mark.asyncio
async def test_deprovision_surfaces_real_auth_failure_and_keeps_row(monkeypatch):
    class FakeClient:
        def __init__(self, *a):
            pass

        async def query_meta(self, query, action=""):
            return ConnectorResult(ok=False, error="Delete failed: Forbidden — insufficient role")

    called = {"row": False}

    async def _delete_row(uid):
        called["row"] = True
        return True

    monkeypatch.setattr(provision, "TwentyClient", FakeClient)
    monkeypatch.setattr(provision.workspaces, "delete_workspace_row", _delete_row)

    res = await provision.deprovision_workspace(
        {"user_id": "u-x", "base_url": "https://x.crm.jarvismgco.com", "api_key": "k"})
    assert not res.ok                       # genuine failure surfaced
    assert called["row"] is False           # row preserved (don't orphan a live workspace)


# ── repair_workspace_identity: apex → real subdomain ──────────────────────────────
@pytest.mark.asyncio
async def test_repair_rewrites_apex_to_real_subdomain(monkeypatch):
    row = {"user_id": "u-mg", "base_url": "https://crm.jarvismgco.com",
           "api_key": "mg-key", "subdomain": None, "workspace_id": None}
    patched = {}

    async def _get_workspace(uid):
        return row

    async def _read_identity(client):
        return {"id": "ws-00e9", "subdomain": "colorful-maroon-tiger",
                "displayName": "MG&CO Technologies",
                "workspaceUrls": {"subdomainUrl": "https://colorful-maroon-tiger.crm.jarvismgco.com"}}

    async def _update(uid, **fields):
        patched.update(fields)
        patched["uid"] = uid
        return True

    monkeypatch.setattr(provision.workspaces, "get_workspace", _get_workspace)
    monkeypatch.setattr(provision, "read_workspace_identity", _read_identity)
    monkeypatch.setattr(provision.workspaces, "update_workspace_fields", _update)

    res = await provision.repair_workspace_identity("u-mg")
    assert res.ok and res.data["changed"]
    assert patched["base_url"] == "https://colorful-maroon-tiger.crm.jarvismgco.com"
    assert patched["subdomain"] == "colorful-maroon-tiger"
    assert patched["workspace_id"] == "ws-00e9"
    assert patched["uid"] == "u-mg"


@pytest.mark.asyncio
async def test_repair_is_noop_when_already_correct(monkeypatch):
    row = {"user_id": "u-ok", "base_url": "https://acme.crm.jarvismgco.com",
           "api_key": "k", "subdomain": "acme", "workspace_id": "ws1"}

    async def _get_workspace(uid):
        return row

    async def _read_identity(client):
        return {"id": "ws1", "subdomain": "acme",
                "workspaceUrls": {"subdomainUrl": "https://acme.crm.jarvismgco.com"}}

    async def _update(uid, **fields):
        raise AssertionError("must not patch when nothing changed")

    monkeypatch.setattr(provision.workspaces, "get_workspace", _get_workspace)
    monkeypatch.setattr(provision, "read_workspace_identity", _read_identity)
    monkeypatch.setattr(provision.workspaces, "update_workspace_fields", _update)

    res = await provision.repair_workspace_identity("u-ok")
    assert res.ok and res.data["changed"] is False
