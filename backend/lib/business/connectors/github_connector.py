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
        """Push multiple files to a repo in a single atomic commit via the Git Trees API."""
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                # 1. Get current branch SHA
                ref_res = await client.get(
                    f"{GITHUB_API}/repos/{repo}/git/ref/heads/{branch}",
                    headers=self._headers(),
                )
                if ref_res.status_code != 200:
                    return ConnectorResult(ok=False, error=f"Could not get branch ref: {ref_res.status_code}")
                current_sha = ref_res.json()["object"]["sha"]

                # 2. Get current tree SHA
                commit_res = await client.get(
                    f"{GITHUB_API}/repos/{repo}/git/commits/{current_sha}",
                    headers=self._headers(),
                )
                base_tree_sha = commit_res.json()["tree"]["sha"]

                # 3. Create blobs for each file
                tree_items = []
                for f in files:
                    blob_res = await client.post(
                        f"{GITHUB_API}/repos/{repo}/git/blobs",
                        headers=self._headers(),
                        json={"content": f["content"], "encoding": "utf-8"},
                    )
                    if blob_res.status_code != 201:
                        return ConnectorResult(ok=False, error=f"Blob creation failed for {f['path']}: {blob_res.text[:200]}")
                    tree_items.append({
                        "path": f["path"],
                        "mode": "100644",
                        "type": "blob",
                        "sha": blob_res.json()["sha"],
                    })

                # 4. Create new tree
                tree_res = await client.post(
                    f"{GITHUB_API}/repos/{repo}/git/trees",
                    headers=self._headers(),
                    json={"base_tree": base_tree_sha, "tree": tree_items},
                )
                if tree_res.status_code != 201:
                    return ConnectorResult(ok=False, error=f"Tree creation failed: {tree_res.text[:200]}")
                new_tree_sha = tree_res.json()["sha"]

                # 5. Create commit
                commit_create_res = await client.post(
                    f"{GITHUB_API}/repos/{repo}/git/commits",
                    headers=self._headers(),
                    json={"message": message, "tree": new_tree_sha, "parents": [current_sha]},
                )
                if commit_create_res.status_code != 201:
                    return ConnectorResult(ok=False, error=f"Commit failed: {commit_create_res.text[:200]}")
                new_commit_sha = commit_create_res.json()["sha"]

                # 6. Update branch ref
                update_res = await client.patch(
                    f"{GITHUB_API}/repos/{repo}/git/ref/heads/{branch}",
                    headers=self._headers(),
                    json={"sha": new_commit_sha},
                )
                if update_res.status_code != 200:
                    return ConnectorResult(ok=False, error=f"Ref update failed: {update_res.text[:200]}")

                return ConnectorResult(ok=True, data={
                    "success": True,
                    "commit_sha": new_commit_sha,
                    "files_pushed": len(files),
                    "message": message,
                    "url": f"https://github.com/{repo}/commit/{new_commit_sha}",
                })
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Push files failed: {e}")
