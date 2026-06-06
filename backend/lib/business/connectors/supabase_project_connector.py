"""
Supabase Connector for Jarvis OS1 — for USER projects, not Jarvis's own DB.
Auth: Access Token from supabase.com/dashboard/account/tokens.
"""
import httpx

from backend.lib.business.connectors.base import BaseConnector, ConnectorResult

SUPABASE_MGMT_API = "https://api.supabase.com/v1"


class SupabaseProjectConnector(BaseConnector):
    CONNECTOR_TYPE = "supabase_project"
    DISPLAY_NAME = "Supabase"
    DESCRIPTION = "Manage your Supabase projects — list projects, run SQL, inspect tables."
    DOCS_URL = "https://supabase.com/dashboard/account/tokens"
    REQUIRED_FIELDS = {
        "api_key": {
            "label": "Access Token (from supabase.com/dashboard/account/tokens)",
            "type": "password",
            "placeholder": "sbp_...",
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
                res = await client.get(f"{SUPABASE_MGMT_API}/projects", headers=self._headers(), timeout=10.0)
            if res.status_code == 200:
                projects = res.json()
                return ConnectorResult(ok=True, data={"project_count": len(projects)})
            if res.status_code == 401:
                return ConnectorResult(ok=False, error="Invalid Supabase token — check your token at supabase.com/dashboard/account/tokens.")
            return ConnectorResult(ok=False, error=f"Supabase auth failed: {res.status_code}")
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Supabase connection failed: {e}")

    async def list_projects(self) -> ConnectorResult:
        try:
            async with httpx.AsyncClient() as client:
                res = await client.get(f"{SUPABASE_MGMT_API}/projects", headers=self._headers(), timeout=15.0)
            if res.status_code == 200:
                projects = res.json()
                return ConnectorResult(ok=True, data={
                    "projects": [
                        {
                            "id": p["id"],
                            "name": p["name"],
                            "region": p.get("region"),
                            "status": p.get("status"),
                            "url": f"https://{p['id']}.supabase.co",
                        }
                        for p in projects
                    ]
                })
            return ConnectorResult(ok=False, error=f"Failed to list projects: {res.status_code}")
        except Exception as e:
            return ConnectorResult(ok=False, error=f"List projects failed: {e}")

    async def get_project_keys(self, project_id: str) -> ConnectorResult:
        """Get API keys (anon + service_role) for a project — truncated for security."""
        try:
            async with httpx.AsyncClient() as client:
                res = await client.get(
                    f"{SUPABASE_MGMT_API}/projects/{project_id}/api-keys",
                    headers=self._headers(),
                    timeout=10.0,
                )
            if res.status_code == 200:
                keys = res.json()
                return ConnectorResult(ok=True, data={
                    "keys": [
                        {"name": k["name"], "api_key": k["api_key"][:20] + "..."}
                        for k in keys
                    ],
                    "note": "Full keys visible in Supabase dashboard. Jarvis shows truncated versions for security.",
                })
            return ConnectorResult(ok=False, error=f"Failed to get keys: {res.status_code}")
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Get project keys failed: {e}")

    async def run_sql(self, project_id: str, sql: str) -> ConnectorResult:
        """Execute SQL on a Supabase project via the Management API."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await client.post(
                    f"{SUPABASE_MGMT_API}/projects/{project_id}/database/query",
                    headers=self._headers(),
                    json={"query": sql},
                )
            if res.status_code == 200:
                return ConnectorResult(ok=True, data={"result": res.json()})
            return ConnectorResult(ok=False, error=f"SQL failed: {res.status_code} — {res.text[:200]}")
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Run SQL failed: {e}")
