"""
Notion connector. Uses an Internal Integration Token (simple API key approach —
no OAuth callback needed). Users create the token at notion.so/my-integrations
and share their pages/databases with it.
"""
import asyncio

import httpx

from backend.lib.business.connectors.base import BaseConnector, ConnectorResult

NOTION_VERSION = "2022-06-28"
BASE = "https://api.notion.com/v1"

# Hard ceiling on bulk row inserts per call — protects both us and Notion's rate limit.
ROW_INSERT_CAP = 100


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
        try:
            async with httpx.AsyncClient() as client:
                # Flat column→value maps are accepted too — convert them against the
                # live database schema so the model doesn't have to hand-build
                # Notion's raw property JSON (a frequent source of silent 400s).
                if properties and not all(isinstance(v, dict) for v in properties.values()):
                    schema_types = await self._fetch_schema_types(client, database_id)
                    properties, skipped = self._row_to_properties(schema_types, properties)
                    if not properties:
                        return ConnectorResult(ok=False, error=(
                            f"No columns matched the database schema (skipped: {', '.join(skipped)}). "
                            f"Database columns are: {', '.join(schema_types)}"
                        ))
                body = {
                    "parent": {"database_id": database_id},
                    "properties": properties,
                }
                if children:
                    body["children"] = children
                resp = await client.post(f"{BASE}/pages", headers=self._headers(), json=body, timeout=15.0)
            resp.raise_for_status()
            data = resp.json()
            return ConnectorResult(ok=True, data={"page_id": data["id"], "url": data.get("url")})
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Create page failed: {e}")

    async def create_pages_bulk(self, database_id: str, rows: list) -> ConnectorResult:
        """Insert many rows into an existing database in one call. Each row is a flat
        {column name: value} map converted against the live database schema."""
        if not database_id:
            return ConnectorResult(ok=False, error="`database_id` is required")
        if not rows or not isinstance(rows, list):
            return ConnectorResult(ok=False, error="`rows` must be a non-empty list of column→value objects")
        try:
            async with httpx.AsyncClient() as client:
                db_resp = await client.get(f"{BASE}/databases/{database_id}", headers=self._headers(), timeout=10.0)
                db_resp.raise_for_status()
                db = db_resp.json()
                schema_types = {name: prop.get("type", "rich_text") for name, prop in db.get("properties", {}).items()}
                accounting = await self._insert_rows(client, database_id, schema_types, rows)
            data = {"database_id": database_id, "url": db.get("url", ""), "status": "rows_added", **accounting}
            if accounting["rows_created"] == 0:
                return ConnectorResult(ok=False, error=(
                    f"0 of {len(rows)} rows were inserted. First error: "
                    f"{(accounting.get('failures') or [{}])[0].get('error', 'unknown')}"
                ))
            return ConnectorResult(ok=True, data=data)
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Bulk insert failed: {e}")

    async def _fetch_schema_types(self, client: httpx.AsyncClient, database_id: str) -> dict:
        resp = await client.get(f"{BASE}/databases/{database_id}", headers=self._headers(), timeout=10.0)
        resp.raise_for_status()
        return {name: prop.get("type", "rich_text") for name, prop in resp.json().get("properties", {}).items()}

    async def _insert_rows(self, client: httpx.AsyncClient, database_id: str, schema_types: dict, rows: list) -> dict:
        """Sequentially insert flat rows, returning honest accounting — never claim
        success for rows that didn't land."""
        created = 0
        failures: list[dict] = []
        for i, row in enumerate(rows[:ROW_INSERT_CAP]):
            if not isinstance(row, dict) or not row:
                failures.append({"row": i + 1, "error": "row is not a column→value object"})
                continue
            props, skipped = self._row_to_properties(schema_types, row)
            if not props:
                failures.append({"row": i + 1, "error": f"no columns matched the schema (got: {', '.join(list(row)[:6])})"})
                continue
            try:
                resp = await client.post(
                    f"{BASE}/pages",
                    headers=self._headers(),
                    json={"parent": {"database_id": database_id}, "properties": props},
                    timeout=15.0,
                )
                if resp.status_code >= 400:
                    try:
                        detail = resp.json().get("message", "")
                    except Exception:
                        detail = ""
                    failures.append({"row": i + 1, "error": (detail or f"HTTP {resp.status_code}")[:200]})
                else:
                    created += 1
            except Exception as e:
                failures.append({"row": i + 1, "error": str(e)[:200]})
            await asyncio.sleep(0.12)  # stay under Notion's ~3 req/s rate limit
        result: dict = {"rows_created": created, "rows_failed": len(failures)}
        if len(rows) > ROW_INSERT_CAP:
            result["rows_skipped_over_cap"] = len(rows) - ROW_INSERT_CAP
        if failures:
            result["failures"] = failures[:5]
        return result

    def _row_to_properties(self, schema_types: dict, row: dict) -> tuple[dict, list[str]]:
        """Convert a flat {column: value} row into Notion property payloads.
        Column matching is case-insensitive. Returns (properties, skipped_columns)."""
        lower_map = {name.lower(): name for name in schema_types}
        props: dict = {}
        skipped: list[str] = []
        for key, value in (row or {}).items():
            col = key if key in schema_types else lower_map.get(str(key).strip().lower())
            if not col:
                skipped.append(str(key))
                continue
            payload = self._prop_payload(schema_types[col], value)
            if payload is None:
                skipped.append(str(key))
                continue
            props[col] = payload
        return props, skipped

    @staticmethod
    def _prop_payload(prop_type: str, value) -> dict | None:
        """One flat value → the Notion property payload for its column type.
        Returns None for empty values or types we can't safely write (formula etc.)."""
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        if prop_type == "title":
            return {"title": [{"type": "text", "text": {"content": str(value)[:2000]}}]}
        if prop_type == "rich_text":
            return {"rich_text": [{"type": "text", "text": {"content": str(value)[:2000]}}]}
        if prop_type == "number":
            try:
                num = float(str(value).replace(",", "").replace("$", "").replace("%", "").strip())
            except (TypeError, ValueError):
                return None
            return {"number": num}
        if prop_type == "select":
            return {"select": {"name": str(value)[:100]}}
        if prop_type == "multi_select":
            items = value if isinstance(value, list) else [v.strip() for v in str(value).split(",")]
            return {"multi_select": [{"name": str(v)[:100]} for v in items if v]}
        if prop_type == "status":
            return {"status": {"name": str(value)[:100]}}
        if prop_type == "date":
            return {"date": {"start": str(value)}}
        if prop_type == "checkbox":
            if isinstance(value, str):
                return {"checkbox": value.strip().lower() in ("true", "yes", "1", "checked", "done")}
            return {"checkbox": bool(value)}
        if prop_type == "url":
            return {"url": str(value)}
        if prop_type == "email":
            return {"email": str(value)}
        if prop_type == "phone_number":
            return {"phone_number": str(value)}
        return None

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
        rows: list | None = None,
    ) -> ConnectorResult:
        """Create a new database under a parent page with optional custom column schema,
        then insert `rows` (flat column→value maps) in the same call. Row insertion
        happens here because the chat loop ends at the confirm card — a separate
        row-insert round would never run."""
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
                data = {
                    "database_id": result["id"],
                    "title": title,
                    "url": result.get("url", ""),
                    "status": "created",
                }
                if rows:
                    schema_types = {name: next(iter(payload)) for name, payload in properties.items()}
                    data.update(await self._insert_rows(client, result["id"], schema_types, rows))
            return ConnectorResult(ok=True, data=data)
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
