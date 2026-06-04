"""
Notion connector. Uses an Internal Integration Token (simple API key approach —
no OAuth callback needed). Users create the token at notion.so/my-integrations
and share their pages/databases with it.
"""
import httpx

from backend.lib.business.connectors.base import BaseConnector, ConnectorResult

NOTION_VERSION = "2022-06-28"
BASE = "https://api.notion.com/v1"


class NotionConnector(BaseConnector):
    CONNECTOR_TYPE = "notion"
    DISPLAY_NAME = "Notion"
    DESCRIPTION = "Read and write to your Notion workspace — pages, databases, and tasks."
    DOCS_URL = "https://www.notion.so/my-integrations"
    REQUIRED_FIELDS = {
        "api_key": {
            "label": "Integration Token",
            "type": "password",
            "placeholder": "ntn_...",
            "secret": True,
            "required": True,
        },
    }

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.credentials.get('api_key', '').strip()}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }

    async def test(self) -> ConnectorResult:
        missing = self._missing_fields()
        if missing:
            return ConnectorResult(ok=False, error=f"Missing required fields: {', '.join(missing)}")
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{BASE}/users/me", headers=self._headers(), timeout=10.0)
            if resp.status_code == 401:
                return ConnectorResult(ok=False, error="Invalid integration token — create one at notion.so/my-integrations, then share your pages with it.")
            resp.raise_for_status()
            user = resp.json()
            return ConnectorResult(ok=True, data={"name": user.get("name", "Notion bot")})
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Notion connection failed: {e}")

    async def search(self, query: str = "", filter_type: str | None = None) -> ConnectorResult:
        body: dict = {"query": query, "page_size": 20}
        if filter_type in ("page", "database"):
            body["filter"] = {"value": filter_type, "property": "object"}
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(f"{BASE}/search", headers=self._headers(), json=body, timeout=15.0)
            resp.raise_for_status()
            results = [
                {"id": r["id"], "title": self._extract_title(r), "type": r["object"]}
                for r in resp.json().get("results", [])
            ]
            return ConnectorResult(ok=True, data={"results": results})
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Notion search failed: {e}")

    async def read_page(self, page_id: str) -> ConnectorResult:
        try:
            async with httpx.AsyncClient() as client:
                page_resp = await client.get(f"{BASE}/pages/{page_id}", headers=self._headers(), timeout=10.0)
                page_resp.raise_for_status()
                blocks_resp = await client.get(f"{BASE}/blocks/{page_id}/children", headers=self._headers(), timeout=10.0)
                blocks_resp.raise_for_status()
            return ConnectorResult(ok=True, data={
                "page": page_resp.json(),
                "content_blocks": blocks_resp.json().get("results", []),
            })
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Read page failed: {e}")

    async def query_database(self, database_id: str, filter_obj: dict | None = None) -> ConnectorResult:
        body = {}
        if filter_obj:
            body["filter"] = filter_obj
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{BASE}/databases/{database_id}/query",
                    headers=self._headers(), json=body, timeout=15.0,
                )
            resp.raise_for_status()
            return ConnectorResult(ok=True, data=resp.json())
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Query database failed: {e}")

    async def create_page(self, database_id: str, properties: dict, children: list | None = None) -> ConnectorResult:
        body = {
            "parent": {"database_id": database_id},
            "properties": properties,
        }
        if children:
            body["children"] = children
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(f"{BASE}/pages", headers=self._headers(), json=body, timeout=15.0)
            resp.raise_for_status()
            data = resp.json()
            return ConnectorResult(ok=True, data={"page_id": data["id"], "url": data.get("url")})
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Create page failed: {e}")

    @staticmethod
    def _extract_title(obj: dict) -> str:
        if obj["object"] == "database":
            parts = obj.get("title", [])
        else:
            props = obj.get("properties", {})
            parts = []
            for prop in props.values():
                if prop.get("type") == "title":
                    parts = prop.get("title", [])
                    break
        return "".join(t.get("plain_text", "") for t in parts) or "Untitled"
