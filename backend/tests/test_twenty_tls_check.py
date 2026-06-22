"""Caddy on-demand-TLS `ask` endpoint: only the apex + real provisioned subdomains
get a 200 (cert), everything else 403 (no cert — anti-abuse)."""
import pytest

from backend.routes.business import crm_routes


@pytest.fixture
def provisioned(monkeypatch):
    known = {"acme.crm.jarvismgco.com"}

    async def _check(host):
        return host in known
    monkeypatch.setattr(crm_routes.workspaces, "domain_is_provisioned", _check)
    return known


@pytest.mark.asyncio
async def test_apex_allowed(provisioned):
    assert (await crm_routes.tls_check("crm.jarvismgco.com")).status_code == 200


@pytest.mark.asyncio
async def test_provisioned_subdomain_allowed(provisioned):
    assert (await crm_routes.tls_check("acme.crm.jarvismgco.com")).status_code == 200


@pytest.mark.asyncio
async def test_unprovisioned_subdomain_refused(provisioned):
    assert (await crm_routes.tls_check("evil.crm.jarvismgco.com")).status_code == 403


@pytest.mark.asyncio
async def test_foreign_domain_refused(provisioned):
    assert (await crm_routes.tls_check("attacker.com")).status_code == 403
    assert (await crm_routes.tls_check("crm.jarvismgco.com.attacker.com")).status_code == 403
    assert (await crm_routes.tls_check("")).status_code == 403
