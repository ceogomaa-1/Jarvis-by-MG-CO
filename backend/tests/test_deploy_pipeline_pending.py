import pytest
import asyncio

from backend.lib.business.connectors.base import ConnectorResult
from backend.lib.business.creation import deploy_pipeline


class FakeGitHub:
    async def create_repo(self, **kwargs):
        return ConnectorResult(ok=True, data={
            "full_name": "mgco/test-site",
            "url": "https://github.com/mgco/test-site",
        })

    async def push_files(self, **kwargs):
        return ConnectorResult(ok=True, data={"files_pushed": len(kwargs["files"])})


class FakeVercel:
    def __init__(self):
        self.deployment_checks = 0

    async def create_project(self, **kwargs):
        return ConnectorResult(ok=True, data={"name": "test-site"})

    async def deploy_files(self, **kwargs):
        return ConnectorResult(ok=True, data={
            "deployment_id": "dpl_123",
            "url": "test-site.vercel.app",
            "readyState": "BUILDING",
        })

    async def get_deployment(self, deployment_id):
        self.deployment_checks += 1
        return ConnectorResult(ok=True, data={"readyState": "READY"})


@pytest.mark.asyncio
async def test_deploy_pipeline_returns_pending_without_polling(monkeypatch):
    github = FakeGitHub()
    vercel = FakeVercel()

    async def fake_get_connector_for_user(user_id, connector_type):
        return {"github": github, "vercel": vercel}.get(connector_type)

    monkeypatch.setattr(deploy_pipeline, "get_connector_for_user", fake_get_connector_for_user)
    site = {
        "project_name": "test-site",
        "files": [{"path": "package.json", "content": "{}"}],
        "needs_database": False,
        "summary": "Smoke test",
    }

    events = [
        event async for event in deploy_pipeline.run_deploy_pipeline(
            "user_3363afdc9bca4b88893cf535c62a6687",
            site,
            "build a website",
            creation_id="creation-123",
        )
    ]

    assert events[-1]["type"] == "deployment_pending"
    assert events[-1]["deployment_id"] == "dpl_123"
    assert events[-1]["expected_url"] == "https://test-site.vercel.app"
    assert vercel.deployment_checks == 0


@pytest.mark.asyncio
async def test_deploy_pipeline_heartbeats_during_slow_github_push(monkeypatch):
    class SlowGitHub(FakeGitHub):
        async def push_files(self, **kwargs):
            await asyncio.sleep(0.03)
            return await super().push_files(**kwargs)

    github = SlowGitHub()
    vercel = FakeVercel()

    async def fake_get_connector_for_user(user_id, connector_type):
        return {"github": github, "vercel": vercel}.get(connector_type)

    monkeypatch.setattr(deploy_pipeline, "get_connector_for_user", fake_get_connector_for_user)
    monkeypatch.setattr(deploy_pipeline, "_EXTERNAL_STATUS_INTERVAL", 0.01)

    site = {
        "project_name": "test-site",
        "files": [{"path": "package.json", "content": "{}"}],
        "needs_database": False,
        "summary": "Smoke test",
    }

    events = [
        event async for event in deploy_pipeline.run_deploy_pipeline(
            "user_3363afdc9bca4b88893cf535c62a6687",
            site,
            "build a website",
            creation_id="creation-123",
        )
    ]

    assert any(
        event.get("type") == "deployment_status" and "Still pushing files to GitHub" in event.get("message", "")
        for event in events
    )
    assert events[-1]["type"] == "deployment_pending"
