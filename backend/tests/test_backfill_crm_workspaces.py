"""Backfill script: idempotent candidate selection + summary. Network + provision mocked."""
import pytest

from backend.lib.business.connectors.base import ConnectorResult
from backend.lib.business.twenty import workspaces
from backend.scripts import backfill_crm_workspaces as bf

USERS = [
    {"user_id": "user_3363afdc9bca4b88893cf535c62a6687", "company_name": "MG&CO"},   # already provisioned
    {"user_id": "user_577c9fc5240f4444996a1865666fc32e", "company_name": "Pioneer"}, # needs it
    {"user_id": "user_25cf124d482448f3b38888a6778b405b", "company_name": "Partners"},# needs it
]
PROVISIONED = {"3363afdc-9bca-4b88-893c-f535c62a6687"}   # uuid form, as stored


def test_select_candidates_skips_already_provisioned():
    candidates, already = bf.select_candidates(USERS, PROVISIONED)
    assert already == 1
    assert [c["user_id"] for c in candidates] == [USERS[1]["user_id"], USERS[2]["user_id"]]


def test_select_candidates_matches_uuid_format():
    # the user_<hex> business id must match the hyphenated uuid stored in the workspace table
    assert workspaces._user_id_to_uuid("user_3363afdc9bca4b88893cf535c62a6687") in PROVISIONED


@pytest.fixture
def mocked(monkeypatch):
    async def _fetch(user_id=None):
        return [u for u in USERS if not user_id or u["user_id"] == user_id]

    async def _prov_uuids():
        return set(PROVISIONED)

    calls = []

    async def _auto(uid, name):
        calls.append(uid)
        return ConnectorResult(ok=True, data={"base_url": f"https://{name.lower()}.crm.jarvismgco.com"})

    monkeypatch.setattr(bf, "_fetch_business_users", _fetch)
    monkeypatch.setattr(bf, "_provisioned_uuids", _prov_uuids)
    monkeypatch.setattr(bf.provision, "auto_provision_workspace", _auto)
    return calls


@pytest.mark.asyncio
async def test_dry_run_makes_no_calls(mocked):
    s = await bf.run_backfill(user_id=None, dry_run=True, limit=None, retries=2)
    assert mocked == []                       # provisioned nothing
    assert s["skipped"] == 1                  # the already-provisioned one


@pytest.mark.asyncio
async def test_real_run_provisions_only_unprovisioned(mocked):
    s = await bf.run_backfill(user_id=None, dry_run=False, limit=None, retries=2)
    assert s["provisioned"] == 2 and s["failed"] == 0 and s["skipped"] == 1
    assert len(mocked) == 2                   # only the two that needed it


@pytest.mark.asyncio
async def test_limit_caps_attempts(mocked):
    s = await bf.run_backfill(user_id=None, dry_run=False, limit=1, retries=2)
    assert s["provisioned"] == 1 and len(mocked) == 1


@pytest.mark.asyncio
async def test_second_run_provisions_zero(monkeypatch):
    """After everyone is provisioned, a re-run does nothing (idempotent)."""
    async def _fetch(user_id=None):
        return USERS

    async def _prov_all():
        return {workspaces._user_id_to_uuid(u["user_id"]) for u in USERS}

    called = []

    async def _auto(uid, name):
        called.append(uid); return ConnectorResult(ok=True, data={})

    monkeypatch.setattr(bf, "_fetch_business_users", _fetch)
    monkeypatch.setattr(bf, "_provisioned_uuids", _prov_all)
    monkeypatch.setattr(bf.provision, "auto_provision_workspace", _auto)

    s = await bf.run_backfill(user_id=None, dry_run=False, limit=None, retries=2)
    assert s["provisioned"] == 0 and called == [] and s["skipped"] == len(USERS)


@pytest.mark.asyncio
async def test_continues_past_a_failure(monkeypatch):
    async def _fetch(user_id=None):
        return USERS[1:]                      # two unprovisioned users

    async def _none():
        return set()

    async def _auto(uid, name):
        if uid == USERS[1]["user_id"]:
            return ConnectorResult(ok=False, error="signUp: boom")   # terminal failure
        return ConnectorResult(ok=True, data={"base_url": "x"})

    monkeypatch.setattr(bf, "_fetch_business_users", _fetch)
    monkeypatch.setattr(bf, "_provisioned_uuids", _none)
    monkeypatch.setattr(bf.provision, "auto_provision_workspace", _auto)

    s = await bf.run_backfill(user_id=None, dry_run=False, limit=None, retries=0)
    assert s["failed"] == 1 and s["provisioned"] == 1     # one failed, run still finished
    assert s["failures"][0][0] == USERS[1]["user_id"]
