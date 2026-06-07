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
        Push files to a repo using the Contents API (one PUT per file).
        Much faster and more reliable than the Git Trees API for small projects:
        no blob→tree→commit→ref chain, each file is independent.
        """
        import base64

        pushed = []
        errors = []

        async def _put_file(client: httpx.AsyncClient, file_path: str, content: str, attempt: int = 1) -> bool:
            encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
            sha = None
            check = await client.get(
                f"{GITHUB_API}/repos/{repo}/contents/{file_path}",
                headers=self._headers(),
                params={"ref": branch},
            )
            if check.status_code == 200:
                sha = check.json().get("sha")

            body: dict = {"message": message, "content": encoded, "branch": branch}
            if sha:
                body["sha"] = sha

            res = await client.put(
                f"{GITHUB_API}/repos/{repo}/contents/{file_path}",
                headers=self._headers(),
                json=body,
            )
            if res.status_code in (200, 201):
                return True
            # 409/422: SHA conflict — refetch and retry once
            if res.status_code in (409, 422) and attempt == 1:
                return await _put_file(client, file_path, content, attempt=2)
            errors.append(f"{file_path}: {res.status_code} {res.text[:120]}")
            return False

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                for f in files[:60]:  # raised cap: Next.js projects routinely exceed 20
                    file_path = f["path"]
                    content = f.get("content", "")
                    ok = await _put_file(client, file_path, content)
                    if ok:
                        pushed.append(file_path)

        except Exception as e:
            return ConnectorResult(ok=False, error=f"Push files failed: {e}")

        if pushed:
            return ConnectorResult(ok=True, data={
                "success": True,
                "files_pushed": len(pushed),
                "files": pushed,
                "errors": errors or None,
                "url": f"https://github.com/{repo}",
                "message": message,
            })
        return ConnectorResult(ok=False, error=f"No files pushed. Errors: {errors}")
