"""
TwentyClient — thin async GraphQL client for a self-hosted Twenty instance.

Twenty exposes TWO GraphQL endpoints off the same base URL:
  - Core / data API:  POST {base}/graphql      (people, companies, opportunities, notes, tasks)
  - Metadata API:     POST {base}/metadata      (create/modify objects, fields, relations, views)

Auth is a Bearer API key (Settings -> API & Webhooks). Both share the same key.

Configured purely from env so the feature is a single shared instance in Phase 1:
  TWENTY_API_URL  — base URL, e.g. https://crm.yourdomain.com  (no trailing /graphql)
  TWENTY_API_KEY  — the API key

Returns ConnectorResult to match the rest of the business layer (see connectors/base.py).
"""
import os

import httpx

from backend.lib.business.connectors.base import ConnectorResult


class TwentyClient:
    def __init__(self, base_url: str, api_key: str, *, timeout: float = 30.0):
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = (api_key or "").strip()
        self.timeout = timeout

    # ── construction / gating ────────────────────────────────────────────────
    @classmethod
    def from_env(cls) -> "TwentyClient | None":
        """Build from TWENTY_API_URL + TWENTY_API_KEY, or None if not configured."""
        base = os.getenv("TWENTY_API_URL", "").strip()
        key = os.getenv("TWENTY_API_KEY", "").strip()
        if not base or not key:
            return None
        return cls(base, key)

    @staticmethod
    def configured() -> bool:
        """True iff both env vars are set — used to gate tools without building a client."""
        return bool(os.getenv("TWENTY_API_URL", "").strip() and os.getenv("TWENTY_API_KEY", "").strip())

    # ── low-level GraphQL ────────────────────────────────────────────────────
    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def _post(self, path: str, query: str, variables: dict | None, action: str) -> ConnectorResult:
        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    url,
                    headers=self._headers(),
                    json={"query": query, "variables": variables or {}},
                    timeout=self.timeout,
                )
        except Exception as e:
            return ConnectorResult(ok=False, error=f"{action} failed: {e}")

        if resp.status_code >= 400:
            detail = resp.text.strip()
            if len(detail) > 400:
                detail = detail[:400] + "..."
            return ConnectorResult(ok=False, error=f"{action} failed: Twenty returned HTTP {resp.status_code} — {detail}")

        try:
            body = resp.json()
        except Exception:
            return ConnectorResult(ok=False, error=f"{action} failed: non-JSON response from Twenty")

        # GraphQL puts errors in a top-level "errors" array even on HTTP 200.
        if body.get("errors"):
            messages = "; ".join(
                (e.get("message") or str(e)) for e in body["errors"][:5]
            )
            return ConnectorResult(ok=False, error=f"{action} failed: {messages}")

        return ConnectorResult(ok=True, data=body.get("data") or {})

    async def query_data(self, query: str, variables: dict | None = None, *, action: str = "Core query") -> ConnectorResult:
        """Run a query/mutation against the Core (data) API: {base}/graphql."""
        return await self._post("/graphql", query, variables, action)

    async def query_meta(self, query: str, variables: dict | None = None, *, action: str = "Metadata query") -> ConnectorResult:
        """Run a query/mutation against the Metadata API: {base}/metadata."""
        return await self._post("/metadata", query, variables, action)

    # ── connectivity check ───────────────────────────────────────────────────
    async def ping(self) -> ConnectorResult:
        """Cheap liveness/auth check — a minimal data-API introspection query."""
        return await self.query_data(
            "query Ping { __typename }",
            action="Twenty ping",
        )
