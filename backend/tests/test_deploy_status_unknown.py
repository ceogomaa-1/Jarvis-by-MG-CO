"""
Regression test for backend/routes/business/create.py — Phase 3
(JARVIS-BRAIN-MAP.md section C7): if the Vercel deployment-status CHECK itself
fails (network/auth error, not the deployment failing), /business/deploy-status
must report state UNKNOWN with the real error — never BUILDING, which would
tell the user "still in progress" forever for a connector failure that already
happened.
"""
import pytest

from backend.lib.business.connectors.base import ConnectorResult
from backend.routes.business import create


class _StatusCheckFailsVercel:
    async def get_deployment(self, deployment_id):
        return ConnectorResult(ok=False, error="Deployment lookup failed: 404")


@pytest.mark.asyncio
async def test_status_check_failure_is_unknown_not_building(monkeypatch):
    async def fake_get_connector_for_user(user_id, connector_type):
        return _StatusCheckFailsVercel()

    persisted = {}

    async def fake_update_deployment_by_id(deployment_id, state, live_url=None, error=None):
        persisted.update(deployment_id=deployment_id, state=state, error=error)

    monkeypatch.setattr(create, "get_connector_for_user", fake_get_connector_for_user)
    monkeypatch.setattr(create, "update_deployment_by_id", fake_update_deployment_by_id)

    result = await create.business_deploy_status(user_id="user_1", deployment_id="dpl_test_unknown")

    assert result["state"] == "UNKNOWN"
    assert result["state"] != "BUILDING"
    assert result["error"] == "Deployment lookup failed: 404"
    assert persisted == {"deployment_id": "dpl_test_unknown", "state": "UNKNOWN", "error": "Deployment lookup failed: 404"}
