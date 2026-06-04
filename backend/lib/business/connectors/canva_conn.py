"""
Canva connector — stub until partner API approval.
Canva's Connect API requires partner approval (~3 weeks). This connector appears
in the UI now and will be functional once the API key is issued.
"""
import httpx

from backend.lib.business.connectors.base import BaseConnector, ConnectorResult


class CanvaConnector(BaseConnector):
    CONNECTOR_TYPE = "canva"
    DISPLAY_NAME = "Canva"
    DESCRIPTION = "Create and edit designs — social posts, presentations, and marketing materials."
    DOCS_URL = "https://www.canva.com/developers/"
    STATUS_NOTE = "Canva API requires partner approval. Apply at canva.com/developers (approx. 3 weeks)."
    REQUIRED_FIELDS = {
        "api_key": {
            "label": "API Key",
            "type": "password",
            "placeholder": "your-canva-api-key",
            "secret": True,
            "required": True,
        },
    }

    async def test(self) -> ConnectorResult:
        missing = self._missing_fields()
        if missing:
            return ConnectorResult(ok=False, error=f"Missing required fields: {', '.join(missing)}")
        api_key = self.credentials.get("api_key", "").strip()
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://api.canva.com/rest/v1/users/me",
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=10.0,
                )
            if resp.status_code == 401:
                return ConnectorResult(ok=False, error="Invalid API key, or Canva partner access not yet approved.")
            if resp.status_code == 404:
                return ConnectorResult(ok=False, error="Canva API endpoint not found — partner approval may still be pending.")
            resp.raise_for_status()
            return ConnectorResult(ok=True, data={"message": "Connected to Canva"})
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Canva connection failed: {e}. Note: partner approval required.")
