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

    async def list_pages(self) -> ConnectorResult:
        """List top-level pages shared with the integration — useful for finding parent IDs."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{BASE}/search",
                    headers=self._headers(),
                    json={"filter": {"value": "page", "property": "object"}, "page_size": 25},
                    timeout=15.0,
                )
            resp.raise_for_status()
            pages = [
                {"id": r["id"], "title": self._extract_title(r), "url": r.get("url", "")}
                for r in resp.json().get("results", [])
            ]
            return ConnectorResult(ok=True, data={"pages": pages, "count": len(pages)})
        except Exception as e:
            return ConnectorResult(ok=False, error=f"List pages failed: {e}")

    async def create_database(
        self,
        parent_page_id: str,
        title: str,
        columns: list | None = None,
    ) -> ConnectorResult:
        """Create a new database under a parent page with optional custom column schema."""
        if not parent_page_id:
            return ConnectorResult(ok=False, error="`parent_page_id` is required — use list_pages to find available parent pages")
        if not title:
            return ConnectorResult(ok=False, error="`title` is required")

        properties: dict = {"Name": {"title": {}}}
        for col in (columns or []):
            col_name = col.get("name", "").strip()
            col_type = col.get("type", "rich_text")
            if not col_name or col_name == "Name":
                continue
            if col_type == "select":
                properties[col_name] = {"select": {"options": [{"name": opt} for opt in col.get("options", [])]}}
            elif col_type == "number":
                properties[col_name] = {"number": {"format": col.get("format", "number")}}
            elif col_type == "date":
                properties[col_name] = {"date": {}}
            elif col_type == "checkbox":
                properties[col_name] = {"checkbox": {}}
            elif col_type == "url":
                properties[col_name] = {"url": {}}
            elif col_type == "email":
                properties[col_name] = {"email": {}}
            elif col_type == "phone_number":
                properties[col_name] = {"phone_number": {}}
            else:
                properties[col_name] = {"rich_text": {}}

        body = {
            "parent": {"page_id": parent_page_id},
            "title": [{"type": "text", "text": {"content": title}}],
            "properties": properties,
        }
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(f"{BASE}/databases", headers=self._headers(), json=body, timeout=20.0)
            resp.raise_for_status()
            result = resp.json()
            return ConnectorResult(ok=True, data={
                "database_id": result["id"],
                "title": title,
                "url": result.get("url", ""),
                "status": "created",
            })
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Create database failed: {e}")

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
