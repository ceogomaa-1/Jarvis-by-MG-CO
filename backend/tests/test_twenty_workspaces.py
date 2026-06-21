"""
Phase 2 multi-tenant isolation: each user_id resolves ONLY its own Jarvis CRM
workspace, never another client's, and never the shared instance when it has its own.

The isolation boundary is the resolved (base_url, api_key) pair: a workspace API key
is scoped to exactly one Twenty workspace, so if user A always resolves A's key and
user B always resolves B's key, A can never read/write B's records. These tests prove
the resolution layer enforces that, with the Supabase registry mocked (no network).
"""
import pytest

from backend.lib.business.twenty import workspaces
from backend.lib.business.twenty.client import TwentyClient


# Fake registry: user_id -> stored workspace row (what crm_client_workspaces holds).
_FAKE_REGISTRY = {
    "user_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa": {
        "workspace_id": "ws-a", "subdomain": "acme",
        "base_url": "https://acme.crm.jarvismgco.com", "api_key": "key-A",
        "display_name": "Acme Realty", "status": "active", "branding_applied": True,
    },
    "user_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb": {
        "workspace_id": "ws-b", "subdomain": "globex",
        "base_url": "https://globex.crm.jarvismgco.com", "api_key": "key-B",
        "display_name": "Globex", "status": "active", "branding_applied": True,
    },
}


@pytest.fixture
def fake_registry(monkeypatch):
    async def _get_workspace(user_id: str):
        return _FAKE_REGISTRY.get(user_id)
    monkeypatch.setattr(workspaces, "get_workspace", _get_workspace)
    # Ensure no shared env instance bleeds into these tests.
    monkeypatch.delenv("TWENTY_API_URL", raising=False)
    monkeypatch.delenv("TWENTY_API_KEY", raising=False)


@pytest.mark.asyncio
async def test_each_user_resolves_its_own_workspace(fake_registry):
    a = await TwentyClient.for_user("user_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
    b = await TwentyClient.for_user("user_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")

    assert a.base_url == "https://acme.crm.jarvismgco.com"
    assert a.api_key == "key-A"
    assert b.base_url == "https://globex.crm.jarvismgco.com"
    assert b.api_key == "key-B"


@pytest.mark.asyncio
async def test_isolation_a_never_gets_b_key(fake_registry):
    """The core isolation property: A's resolved key is never B's, and vice-versa."""
    a = await TwentyClient.for_user("user_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
    b = await TwentyClient.for_user("user_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")

    assert a.api_key != b.api_key
    assert a.base_url != b.base_url
    # A's credentials can never address B's workspace host.
    assert "globex" not in a.base_url
    assert "acme" not in b.base_url


@pytest.mark.asyncio
async def test_unknown_user_with_no_shared_instance_resolves_none(fake_registry):
    client = await TwentyClient.for_user("user_cccccccccccccccccccccccccccccccc")
    assert client is None


@pytest.mark.asyncio
async def test_falls_back_to_shared_env_instance(fake_registry, monkeypatch):
    """A user with no workspace falls back to the Phase 1 shared instance if configured."""
    monkeypatch.setenv("TWENTY_API_URL", "https://crm.jarvismgco.com")
    monkeypatch.setenv("TWENTY_API_KEY", "shared-key")

    client = await TwentyClient.for_user("user_cccccccccccccccccccccccccccccccc")
    assert client is not None
    assert client.base_url == "https://crm.jarvismgco.com"
    assert client.api_key == "shared-key"


@pytest.mark.asyncio
async def test_own_workspace_wins_over_shared_instance(fake_registry, monkeypatch):
    """A provisioned user uses their OWN workspace even if a shared instance exists."""
    monkeypatch.setenv("TWENTY_API_URL", "https://crm.jarvismgco.com")
    monkeypatch.setenv("TWENTY_API_KEY", "shared-key")

    a = await TwentyClient.for_user("user_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
    assert a.api_key == "key-A"
    assert a.base_url == "https://acme.crm.jarvismgco.com"


@pytest.mark.asyncio
async def test_configured_for_user_true_with_workspace_only(fake_registry, monkeypatch):
    """Tools are offered to a user with a workspace even when no shared env is set."""
    async def _has_workspace(user_id: str):
        return user_id in _FAKE_REGISTRY
    monkeypatch.setattr(workspaces, "has_workspace", _has_workspace)

    assert await TwentyClient.configured_for_user("user_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa") is True
    assert await TwentyClient.configured_for_user("user_cccccccccccccccccccccccccccccccc") is False
