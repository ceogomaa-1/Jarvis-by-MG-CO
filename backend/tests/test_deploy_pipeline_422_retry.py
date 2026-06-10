"""
Regression tests for the Batch 6 GitHub 422-retry fix in
backend/lib/business/creation/deploy_pipeline.py ("BUG C").

Before Batch 6, a single 422 "name already exists" from `create_repo` aborted
the entire deploy pipeline. Now it retries with `-v2`/`-v3`/`-v4` suffixes,
and `project_name` is updated to whatever name GitHub actually accepted so
the Vercel steps use the same name. Non-collision errors must NOT retry.
"""

import pytest

from backend.lib.business.connectors.base import ConnectorResult
from backend.lib.business.creation import deploy_pipeline


class FakeVercel:
    async def create_project(self, **kwargs):
        return ConnectorResult(ok=True, data={"name": kwargs["name"]})

    async def set_env(self, *args, **kwargs):
        return ConnectorResult(ok=True, data={})

    async def deploy_files(self, **kwargs):
        return ConnectorResult(ok=True, data={
            "deployment_id": "dpl_123",
            "url": f"{kwargs['project_name']}.vercel.app",
            "readyState": "BUILDING",
        })


def _site():
    return {
        "project_name": "test-site",
        "files": [{"path": "package.json", "content": "{}"}],
        "needs_database": False,
        "summary": "Smoke test",
    }


@pytest.mark.asyncio
async def test_422_collision_retries_with_suffix_and_continues(monkeypatch):
    class FakeGitHub:
        def __init__(self):
            self.create_repo_calls = []
            self.push_files_calls = []

        async def create_repo(self, **kwargs):
            self.create_repo_calls.append(kwargs["name"])
            if kwargs["name"] == "test-site":
                return ConnectorResult(ok=False, error="422 Unprocessable Entity: name already exists on this account")
            return ConnectorResult(ok=True, data={
                "full_name": f"mgco/{kwargs['name']}",
                "url": f"https://github.com/mgco/{kwargs['name']}",
                "name": kwargs["name"],
            })

        async def push_files(self, **kwargs):
            self.push_files_calls.append(kwargs["repo"])
            return ConnectorResult(ok=True, data={"files_pushed": len(kwargs["files"])})

    github = FakeGitHub()
    vercel = FakeVercel()

    async def fake_get_connector_for_user(user_id, connector_type):
        return {"github": github, "vercel": vercel}.get(connector_type)

    monkeypatch.setattr(deploy_pipeline, "get_connector_for_user", fake_get_connector_for_user)
    monkeypatch.setattr(deploy_pipeline, "_EXTERNAL_STATUS_INTERVAL", 0.01)

    events = [
        event async for event in deploy_pipeline.run_deploy_pipeline(
            "user_3363afdc9bca4b88893cf535c62a6687",
            _site(),
            "build a website",
            creation_id="creation-123",
        )
    ]

    # Retried exactly once, with the -v2 suffix
    assert github.create_repo_calls == ["test-site", "test-site-v2"]

    # A status message about the collision/retry was surfaced
    assert any(
        event.get("type") == "deployment_status"
        and "already exists" in event.get("message", "")
        and "test-site-v2" in event.get("message", "")
        for event in events
    )

    # Files were pushed to the repo GitHub actually created
    assert github.push_files_calls == ["mgco/test-site-v2"]

    # Pipeline reached the end successfully
    assert events[-1]["type"] == "deployment_pending"
    assert events[-1]["deployment_id"] == "dpl_123"
    assert events[-1]["expected_url"] == "https://test-site-v2.vercel.app"


@pytest.mark.asyncio
async def test_non_422_error_fails_fast_without_retry(monkeypatch):
    class FakeGitHub:
        def __init__(self):
            self.create_repo_calls = []

        async def create_repo(self, **kwargs):
            self.create_repo_calls.append(kwargs["name"])
            return ConnectorResult(ok=False, error="500 Internal Server Error")

        async def push_files(self, **kwargs):
            raise AssertionError("push_files should not be called when repo creation fails")

    github = FakeGitHub()
    vercel = FakeVercel()

    async def fake_get_connector_for_user(user_id, connector_type):
        return {"github": github, "vercel": vercel}.get(connector_type)

    monkeypatch.setattr(deploy_pipeline, "get_connector_for_user", fake_get_connector_for_user)
    monkeypatch.setattr(deploy_pipeline, "_EXTERNAL_STATUS_INTERVAL", 0.01)

    events = [
        event async for event in deploy_pipeline.run_deploy_pipeline(
            "user_3363afdc9bca4b88893cf535c62a6687",
            _site(),
            "build a website",
            creation_id="creation-123",
        )
    ]

    # Only the original name was tried — no -v2/-v3/-v4 retries
    assert github.create_repo_calls == ["test-site"]

    assert events[-1]["type"] == "deployment_error"
    assert events[-1]["stage"] == "github_create"
    assert "500 Internal Server Error" in events[-1]["value"]
