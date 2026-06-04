"""
GoHighLevel CRM connector. Uses GHL REST API v1 with a Bearer API key.
API key is found in GHL → Settings → API Keys.
"""
import httpx

from backend.lib.business.connectors.base import BaseConnector, ConnectorResult

BASE = "https://rest.gohighlevel.com/v1"


class GoHighLevelConnector(BaseConnector):
    CONNECTOR_TYPE = "gohighlevel"
    DISPLAY_NAME = "GoHighLevel"
    DESCRIPTION = "Manage CRM contacts, pipelines, opportunities, and appointments."
    DOCS_URL = "https://highlevel.stoplight.io/"
    REQUIRED_FIELDS = {
        "api_key": {
            "label": "API Key",
            "type": "password",
            "placeholder": "your-ghl-api-key",
            "secret": True,
            "required": True,
        },
    }

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.credentials.get('api_key', '').strip()}",
            "Content-Type": "application/json",
        }

    async def test(self) -> ConnectorResult:
        missing = self._missing_fields()
        if missing:
            return ConnectorResult(ok=False, error=f"Missing required fields: {', '.join(missing)}")
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{BASE}/contacts/", headers=self._headers(), params={"limit": "1"}, timeout=10.0)
            if resp.status_code == 401:
                return ConnectorResult(ok=False, error="Invalid API key — find yours in GoHighLevel → Settings → API Keys.")
            resp.raise_for_status()
            return ConnectorResult(ok=True, data={"message": "Connected to GoHighLevel"})
        except Exception as e:
            return ConnectorResult(ok=False, error=f"GoHighLevel connection failed: {e}")

    async def list_contacts(self, limit: int = 20) -> ConnectorResult:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{BASE}/contacts/", headers=self._headers(), params={"limit": limit}, timeout=15.0)
            resp.raise_for_status()
            return ConnectorResult(ok=True, data=resp.json())
        except Exception as e:
            return ConnectorResult(ok=False, error=f"List contacts failed: {e}")

    async def search_contacts(self, query: str) -> ConnectorResult:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{BASE}/contacts/search/", headers=self._headers(), params={"query": query}, timeout=15.0)
            resp.raise_for_status()
            return ConnectorResult(ok=True, data=resp.json())
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Search contacts failed: {e}")

    async def create_contact(self, contact_data: dict) -> ConnectorResult:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(f"{BASE}/contacts/", headers=self._headers(), json=contact_data, timeout=15.0)
            resp.raise_for_status()
            return ConnectorResult(ok=True, data=resp.json())
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Create contact failed: {e}")

    async def list_pipelines(self) -> ConnectorResult:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{BASE}/pipelines/", headers=self._headers(), timeout=15.0)
            resp.raise_for_status()
            return ConnectorResult(ok=True, data=resp.json())
        except Exception as e:
            return ConnectorResult(ok=False, error=f"List pipelines failed: {e}")

    async def list_opportunities(self, pipeline_id: str) -> ConnectorResult:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{BASE}/pipelines/{pipeline_id}/opportunities",
                    headers=self._headers(), timeout=15.0,
                )
            resp.raise_for_status()
            return ConnectorResult(ok=True, data=resp.json())
        except Exception as e:
            return ConnectorResult(ok=False, error=f"List opportunities failed: {e}")

    async def list_appointments(self) -> ConnectorResult:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{BASE}/appointments/", headers=self._headers(), timeout=15.0)
            resp.raise_for_status()
            return ConnectorResult(ok=True, data=resp.json())
        except Exception as e:
            return ConnectorResult(ok=False, error=f"List appointments failed: {e}")
