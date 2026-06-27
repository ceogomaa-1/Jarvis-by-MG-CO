"""
Vercel Connector for Jarvis OS1.
Auth: API Token from vercel.com/account/tokens.
"""
import base64
import httpx

from backend.lib.business.connectors.base import BaseConnector, ConnectorResult

VERCEL_API = "https://api.vercel.com"


class VercelConnector(BaseConnector):
    CONNECTOR_TYPE = "vercel"
    DISPLAY_NAME = "Vercel"
    DESCRIPTION = "Deploy projects, create Vercel projects, and monitor deployments."
    DOCS_URL = "https://vercel.com/account/tokens"
    REQUIRED_FIELDS = {
        "api_key": {
            "label": "API Token (from vercel.com/account/tokens)",
            "type": "password",
            "placeholder": "Your Vercel API token",
            "secret": True,
            "required": True,
        },
    }

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.credentials.get('api_key', '')}",
            "Content-Type": "application/json",
        }

    async def test(self) -> ConnectorResult:
        missing = self._missing_fields()
        if missing:
            return ConnectorResult(ok=False, error=f"Missing required fields: {', '.join(missing)}")
        try:
            async with httpx.AsyncClient() as client:
                res = await client.get(f"{VERCEL_API}/v2/user", headers=self._headers(), timeout=10.0)
            if res.status_code == 200:
                user = res.json().get("user", {})
                return ConnectorResult(ok=True, data={"username": user.get("username"), "name": user.get("name")})
            if res.status_code == 403:
                return ConnectorResult(ok=False, error="Invalid Vercel token — check your token at vercel.com/account/tokens.")
            return ConnectorResult(ok=False, error=f"Vercel auth failed: {res.status_code}")
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Vercel connection failed: {e}")

    async def list_projects(self, limit: int = 10) -> ConnectorResult:
        try:
            async with httpx.AsyncClient() as client:
                res = await client.get(
                    f"{VERCEL_API}/v9/projects",
                    headers=self._headers(),
                    params={"limit": limit},
                    timeout=15.0,
                )
            if res.status_code == 200:
                projects = res.json().get("projects", [])
                return ConnectorResult(ok=True, data={
                    "projects": [
                        {
                            "name": p["name"],
                            "id": p["id"],
                            "url": f"https://{p['name']}.vercel.app",
                            "framework": p.get("framework"),
                            "updated_at": p.get("updatedAt"),
                        }
                        for p in projects
                    ]
                })
            return ConnectorResult(ok=False, error=f"Failed to list projects: {res.status_code}")
        except Exception as e:
            return ConnectorResult(ok=False, error=f"List projects failed: {e}")

    async def create_project(self, name: str, github_repo: str = "", framework: str = "nextjs") -> ConnectorResult:
        """Create a new Vercel project."""
        try:
            body: dict = {"name": name, "framework": framework}
            if github_repo:
                body["gitRepository"] = {"type": "github", "repo": github_repo}

            async with httpx.AsyncClient() as client:
                res = await client.post(
                    f"{VERCEL_API}/v10/projects",
                    headers=self._headers(),
                    json=body,
                    timeout=15.0,
                )
            if res.status_code in (200, 201):
                proj = res.json()
                return ConnectorResult(ok=True, data={
                    "name": proj["name"],
                    "id": proj["id"],
                    "url": f"https://{proj['name']}.vercel.app",
                })
            # 409 = project already exists — fetch it
            if res.status_code == 409:
                async with httpx.AsyncClient() as client:
                    get_res = await client.get(
                        f"{VERCEL_API}/v9/projects/{name}",
                        headers=self._headers(),
                        timeout=10.0,
                    )
                if get_res.status_code == 200:
                    proj = get_res.json()
                    return ConnectorResult(ok=True, data={
                        "name": proj["name"],
                        "id": proj["id"],
                        "url": f"https://{proj['name']}.vercel.app",
                    })
            return ConnectorResult(ok=False, error=f"Project creation failed: {res.status_code} — {res.text[:200]}")
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Create project failed: {e}")

    async def set_env(
        self,
        project_name: str,
        key: str,
        value: str,
        targets: list[str] | None = None,
    ) -> ConnectorResult:
        """Set an environment variable on a Vercel project."""
        if targets is None:
            targets = ["production", "preview", "development"]
        try:
            async with httpx.AsyncClient() as client:
                res = await client.post(
                    f"{VERCEL_API}/v10/projects/{project_name}/env",
                    headers=self._headers(),
                    json={"key": key, "value": value, "type": "plain", "target": targets},
                    timeout=15.0,
                )
            if res.status_code in (200, 201):
                return ConnectorResult(ok=True, data={"key": key})
            # 409 = already exists — update it
            if res.status_code == 409:
                data = res.json()
                env_id = None
                if "error" in data and "existing" in str(data):
                    # Try to find and update the existing env var
                    list_res = await httpx.AsyncClient().get(
                        f"{VERCEL_API}/v10/projects/{project_name}/env",
                        headers=self._headers(),
                        timeout=10.0,
                    )
                    if list_res.status_code == 200:
                        for env in list_res.json().get("envs", []):
                            if env.get("key") == key:
                                env_id = env["id"]
                                break
                if env_id:
                    async with httpx.AsyncClient() as client:
                        patch_res = await client.patch(
                            f"{VERCEL_API}/v10/projects/{project_name}/env/{env_id}",
                            headers=self._headers(),
                            json={"value": value, "target": targets},
                            timeout=10.0,
                        )
                    if patch_res.status_code == 200:
                        return ConnectorResult(ok=True, data={"key": key, "updated": True})
            return ConnectorResult(ok=False, error=f"Set env failed: {res.status_code} — {res.text[:200]}")
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Set env failed: {e}")

    async def deploy_files(
        self,
        project_name: str,
        files: list[dict],
        env: dict | None = None,
        framework: str = "nextjs",
    ) -> ConnectorResult:
        """
        Deploy a project by uploading source files directly to Vercel.
        No GitHub App integration required — Vercel builds from the provided files.
        `files`: list of {"path": "...", "content": "..."} dicts.
        `env`: optional dict of env vars to inject into this deployment.
        """
        try:
            vercel_files = []
            for f in files:
                content = f.get("content", "")
                vercel_files.append({
                    "file": f["path"],
                    "data": content,
                    "encoding": "utf-8",
                })

            body: dict = {
                "name": project_name,
                "files": vercel_files,
                "projectSettings": {
                    "framework": framework,
                    "installCommand": "npm ci",
                    "buildCommand": "npm run build",
                    "outputDirectory": ".next",
                },
                "target": "production",
            }
            if env:
                body["env"] = env

            async with httpx.AsyncClient(timeout=60.0) as client:
                res = await client.post(
                    f"{VERCEL_API}/v13/deployments",
                    headers=self._headers(),
                    json=body,
                )

            if res.status_code in (200, 201):
                dep = res.json()
                dep_url = dep.get("url", "")
                if dep_url and not dep_url.startswith("http"):
                    dep_url = f"https://{dep_url}"
                return ConnectorResult(ok=True, data={
                    "deployment_id": dep.get("id"),
                    "url": dep_url,
                    "readyState": dep.get("readyState", dep.get("status", "BUILDING")),
                })
            return ConnectorResult(
                ok=False,
                error=f"Deploy failed: {res.status_code} — {res.text[:400]}",
            )
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Deploy files failed: {e}")

    async def deploy_static(self, project_name: str, html: str) -> ConnectorResult:
        """Deploy a SINGLE self-contained HTML file as a static site — no build, no GitHub.

        Powers the standalone "deploy this page" path: upload index.html, framework=null so
        Vercel serves it as-is. Returns the same shape as deploy_files.
        """
        try:
            body: dict = {
                "name": project_name,
                "files": [{"file": "index.html", "data": html, "encoding": "utf-8"}],
                # framework null + no build/install command → pure static hosting of the file.
                "projectSettings": {
                    "framework": None,
                    "buildCommand": None,
                    "installCommand": None,
                    "outputDirectory": None,
                },
                "target": "production",
            }
            async with httpx.AsyncClient(timeout=60.0) as client:
                res = await client.post(
                    f"{VERCEL_API}/v13/deployments",
                    headers=self._headers(),
                    json=body,
                )
            if res.status_code in (200, 201):
                dep = res.json()
                dep_url = dep.get("url", "")
                if dep_url and not dep_url.startswith("http"):
                    dep_url = f"https://{dep_url}"
                return ConnectorResult(ok=True, data={
                    "deployment_id": dep.get("id"),
                    "url": dep_url,
                    "readyState": dep.get("readyState", dep.get("status", "BUILDING")),
                })
            return ConnectorResult(ok=False, error=f"Static deploy failed: {res.status_code} — {res.text[:400]}")
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Static deploy failed: {e}")

    async def preflight(self) -> ConnectorResult:
        """Verify the Vercel token is present, valid, and not scope-restricted.

        Returns ok=True with {username} when a real deploy can proceed; ok=False with a
        precise, actionable message when the token is missing / invalid / expired.
        """
        if not self.credentials.get("api_key"):
            return ConnectorResult(ok=False, error="Vercel token is missing — add it in Settings → Connections.")
        try:
            async with httpx.AsyncClient() as client:
                res = await client.get(f"{VERCEL_API}/v2/user", headers=self._headers(), timeout=12.0)
            if res.status_code == 200:
                user = res.json().get("user", {})
                return ConnectorResult(ok=True, data={"username": user.get("username")})
            if res.status_code in (401, 403):
                return ConnectorResult(
                    ok=False,
                    error="Vercel token is invalid or expired — regenerate it at vercel.com/account/tokens (needs full account scope) and reconnect.",
                )
            return ConnectorResult(ok=False, error=f"Vercel preflight failed: HTTP {res.status_code} — {res.text[:160]}")
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Vercel preflight failed: {e}")

    async def trigger_deploy(self, project_name: str, github_repo: str = "", branch: str = "main") -> ConnectorResult:
        """Trigger a deployment via git source (requires GitHub App integration)."""
        try:
            body: dict = {"name": project_name, "target": "production"}
            if github_repo:
                body["gitSource"] = {"type": "github", "repo": github_repo, "ref": branch}

            async with httpx.AsyncClient() as client:
                res = await client.post(
                    f"{VERCEL_API}/v13/deployments",
                    headers=self._headers(),
                    json=body,
                    timeout=20.0,
                )
            if res.status_code in (200, 201):
                dep = res.json()
                dep_url = dep.get("url", "")
                if dep_url and not dep_url.startswith("http"):
                    dep_url = f"https://{dep_url}"
                return ConnectorResult(ok=True, data={
                    "deployment_id": dep.get("id"),
                    "url": dep_url,
                    "readyState": dep.get("readyState", dep.get("status")),
                })
            return ConnectorResult(ok=False, error=f"Deploy failed: {res.status_code} — {res.text[:200]}")
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Trigger deploy failed: {e}")

    async def get_deployment(self, deployment_id: str) -> ConnectorResult:
        """Check the status of a Vercel deployment. Returns readyState, url, alias."""
        try:
            async with httpx.AsyncClient() as client:
                res = await client.get(
                    f"{VERCEL_API}/v13/deployments/{deployment_id}",
                    headers=self._headers(),
                    timeout=10.0,
                )
            if res.status_code == 200:
                dep = res.json()
                raw_url = dep.get("url", "")
                # Vercel returns bare domain without scheme
                url = f"https://{raw_url}" if raw_url and not raw_url.startswith("http") else raw_url
                # Prefer alias (production URL) over deployment URL
                aliases = dep.get("alias", [])
                alias_url = f"https://{aliases[0]}" if aliases else url
                return ConnectorResult(ok=True, data={
                    "readyState": dep.get("readyState"),
                    "url": url,
                    "alias": alias_url,
                    "error_message": dep.get("errorMessage"),
                    "created": dep.get("createdAt"),
                })
            return ConnectorResult(ok=False, error=f"Deployment lookup failed: {res.status_code}")
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Get deployment failed: {e}")

    async def get_deployment_build_logs(self, deployment_id: str) -> str:
        """Fetch build logs for a failed deployment. Returns a summary string."""
        try:
            async with httpx.AsyncClient() as client:
                res = await client.get(
                    f"{VERCEL_API}/v2/deployments/{deployment_id}/events",
                    headers=self._headers(),
                    timeout=15.0,
                )
            if res.status_code == 200:
                events = res.json()
                # Extract error lines
                error_lines = []
                for ev in events:
                    text = ev.get("text", ev.get("payload", {}).get("text", ""))
                    if text and ("error" in text.lower() or "failed" in text.lower()):
                        error_lines.append(text.strip())
                if error_lines:
                    return " | ".join(error_lines[:5])
                return "Build failed — check the Vercel dashboard for full logs."
            return f"Could not fetch logs: {res.status_code}"
        except Exception as e:
            return f"Log fetch error: {e}"
