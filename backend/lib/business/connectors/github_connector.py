"""
GitHub Connector for Jarvis OS1.
Auth: Personal Access Token (PAT) with repo scope.
"""
import httpx

from backend.lib.business.connectors.base import BaseConnector, ConnectorResult

GITHUB_API = "https://api.github.com"


class GitHubConnector(BaseConnector):
    CONNECTOR_TYPE = "github"
    DISPLAY_NAME = "GitHub"
    DESCRIPTION = "Create repos, push code, and manage your GitHub projects from Jarvis."
    DOCS_URL = "https://github.com/settings/tokens"
    REQUIRED_FIELDS = {
        "api_key": {
            "label": "Personal Access Token (needs `repo` scope)",
            "type": "password",
            "placeholder": "ghp_...",
            "secret": True,
            "required": True,
        },
    }

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.credentials.get('api_key', '')}",
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def test(self) -> ConnectorResult:
        missing = self._missing_fields()
        if missing:
            return ConnectorResult(ok=False, error=f"Missing required fields: {', '.join(missing)}")
        try:
            async with httpx.AsyncClient() as client:
                res = await client.get(f"{GITHUB_API}/user", headers=self._headers(), timeout=10.0)
            if res.status_code == 200:
                user = res.json()
                return ConnectorResult(ok=True, data={"username": user["login"], "name": user.get("name")})
            if res.status_code == 401:
                return ConnectorResult(ok=False, error="Invalid GitHub token — check the token at github.com/settings/tokens.")
            return ConnectorResult(ok=False, error=f"GitHub auth failed: {res.status_code}")
        except Exception as e:
            return ConnectorResult(ok=False, error=f"GitHub connection failed: {e}")

    async def list_repos(self, limit: int = 10) -> ConnectorResult:
        try:
            async with httpx.AsyncClient() as client:
                res = await client.get(
                    f"{GITHUB_API}/user/repos",
                    headers=self._headers(),
                    params={"sort": "updated", "per_page": min(limit, 100)},
                    timeout=15.0,
                )
            if res.status_code == 200:
                repos = res.json()
                return ConnectorResult(ok=True, data={
                    "repos": [
                        {
                            "name": r["name"],
                            "full_name": r["full_name"],
                            "url": r["html_url"],
                            "private": r["private"],
                            "description": r.get("description"),
                            "updated_at": r["updated_at"],
                        }
                        for r in repos
                    ]
                })
            return ConnectorResult(ok=False, error=f"Failed to list repos: {res.status_code}")
        except Exception as e:
            return ConnectorResult(ok=False, error=f"List repos failed: {e}")

    async def create_repo(self, name: str, description: str = "", private: bool = False) -> ConnectorResult:
        try:
            async with httpx.AsyncClient() as client:
                res = await client.post(
                    f"{GITHUB_API}/user/repos",
                    headers=self._headers(),
                    json={
                        "name": name,
                        "description": description or "Created by Jarvis OS1",
                        "private": private,
                        "auto_init": True,
                    },
                    timeout=15.0,
                )
            if res.status_code == 201:
                repo = res.json()
                return ConnectorResult(ok=True, data={
                    "name": repo["name"],
                    "full_name": repo["full_name"],
                    "url": repo["html_url"],
                    "clone_url": repo["clone_url"],
                })
            return ConnectorResult(ok=False, error=f"Create repo failed: {res.status_code} — {res.text[:200]}")
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Create repo failed: {e}")

    async def push_files(
        self,
        repo: str,
        files: list,
        message: str = "Jarvis OS1: automated commit",
        branch: str = "main",
    ) -> ConnectorResult:
        """
        Push files in one commit using GitHub's Git Data API.
        The older Contents API path did one GET+PUT per file, which could leave
        the SSE stream silent for minutes. This creates blobs, one tree, one
        commit, then moves the branch ref atomically.
        """
        upload_files = files[:60]
        if not upload_files:
            return ConnectorResult(ok=False, error="No files to push.")

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=10.0)) as client:
                ref_res = await client.get(
                    f"{GITHUB_API}/repos/{repo}/git/ref/heads/{branch}",
                    headers=self._headers(),
                )
                if ref_res.status_code != 200:
                    return ConnectorResult(
                        ok=False,
                        error=f"Read branch ref failed: {ref_res.status_code} — {ref_res.text[:200]}",
                    )

                base_commit_sha = ref_res.json()["object"]["sha"]
                commit_res = await client.get(
                    f"{GITHUB_API}/repos/{repo}/git/commits/{base_commit_sha}",
                    headers=self._headers(),
                )
                if commit_res.status_code != 200:
                    return ConnectorResult(
                        ok=False,
                        error=f"Read base commit failed: {commit_res.status_code} — {commit_res.text[:200]}",
                    )
                base_tree_sha = commit_res.json()["tree"]["sha"]

                tree_items = []
                for f in upload_files:
                    blob_res = await client.post(
                        f"{GITHUB_API}/repos/{repo}/git/blobs",
                        headers=self._headers(),
                        json={
                            "content": f.get("content", ""),
                            "encoding": "utf-8",
                        },
                    )
                    if blob_res.status_code != 201:
                        return ConnectorResult(
                            ok=False,
                            error=f"Create blob failed for {f.get('path')}: {blob_res.status_code} — {blob_res.text[:200]}",
                        )
                    tree_items.append({
                        "path": f["path"],
                        "mode": "100644",
                        "type": "blob",
                        "sha": blob_res.json()["sha"],
                    })

                tree_res = await client.post(
                    f"{GITHUB_API}/repos/{repo}/git/trees",
                    headers=self._headers(),
                    json={"base_tree": base_tree_sha, "tree": tree_items},
                )
                if tree_res.status_code != 201:
                    return ConnectorResult(
                        ok=False,
                        error=f"Create tree failed: {tree_res.status_code} — {tree_res.text[:200]}",
                    )

                new_tree_sha = tree_res.json()["sha"]
                new_commit_res = await client.post(
                    f"{GITHUB_API}/repos/{repo}/git/commits",
                    headers=self._headers(),
                    json={
                        "message": message,
                        "tree": new_tree_sha,
                        "parents": [base_commit_sha],
                    },
                )
                if new_commit_res.status_code != 201:
                    return ConnectorResult(
                        ok=False,
                        error=f"Create commit failed: {new_commit_res.status_code} — {new_commit_res.text[:200]}",
                    )

                new_commit_sha = new_commit_res.json()["sha"]
                update_ref_res = await client.patch(
                    f"{GITHUB_API}/repos/{repo}/git/refs/heads/{branch}",
                    headers=self._headers(),
                    json={"sha": new_commit_sha, "force": False},
                )
                if update_ref_res.status_code != 200:
                    return ConnectorResult(
                        ok=False,
                        error=f"Update branch failed: {update_ref_res.status_code} — {update_ref_res.text[:200]}",
                    )

        except Exception as e:
            return ConnectorResult(ok=False, error=f"Push files failed: {e}")

        pushed = [f["path"] for f in upload_files]
        return ConnectorResult(ok=True, data={
            "success": True,
            "files_pushed": len(pushed),
            "files": pushed,
            "url": f"https://github.com/{repo}",
            "message": message,
        })
