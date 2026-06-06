"""
Vercel Connector for Jarvis OS1.
Auth: API Token from vercel.com/account/tokens.
"""
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
        """Create a new Vercel project, optionally linked to a GitHub repo."""
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
            return ConnectorResult(ok=False, error=f"Project creation failed: {res.status_code} — {res.text[:200]}")
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Create project failed: {e}")

    async def trigger_deploy(self, project_name: str, github_repo: str = "", branch: str = "main") -> ConnectorResult:
        """Trigger a production deployment for a Vercel project."""
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
                return ConnectorResult(ok=True, data={
                    "deployment_id": dep.get("id"),
                    "url": dep.get("url"),
                    "status": dep.get("readyState", dep.get("status")),
                })
            return ConnectorResult(ok=False, error=f"Deploy failed: {res.status_code} — {res.text[:200]}")
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Trigger deploy failed: {e}")

    async def get_deployment(self, deployment_id: str) -> ConnectorResult:
        """Check the status of a Vercel deployment."""
        try:
            async with httpx.AsyncClient() as client:
                res = await client.get(
                    f"{VERCEL_API}/v13/deployments/{deployment_id}",
                    headers=self._headers(),
                    timeout=10.0,
                )
            if res.status_code == 200:
                dep = res.json()
                return ConnectorResult(ok=True, data={
                    "status": dep.get("readyState"),
                    "url": dep.get("url"),
                    "created": dep.get("createdAt"),
                })
            return ConnectorResult(ok=False, error=f"Deployment lookup failed: {res.status_code}")
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Get deployment failed: {e}")
