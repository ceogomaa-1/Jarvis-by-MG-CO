"""
TwentyClient — thin async GraphQL client for a self-hosted Twenty instance.

Twenty exposes TWO GraphQL endpoints off the same base URL:
  - Core / data API:  POST {base}/graphql      (people, companies, opportunities, notes, tasks)
  - Metadata API:     POST {base}/metadata      (create/modify objects, fields, relations, views)

Auth is a Bearer API key (Settings -> API & Webhooks). Both share the same key.

Two ways to build a client:
  - Phase 1 (single shared instance, from env):
      TWENTY_API_URL  — base URL, e.g. https://crm.yourdomain.com  (no trailing /graphql)
      TWENTY_API_KEY  — the API key
  - Phase 2 (per-client workspace, from the workspace registry):
      TwentyClient.for_user(user_id) resolves the client's OWN workspace base_url +
      api_key (crm_client_workspaces), falling back to env if they have none. This is
      how data isolation is enforced: each user_id resolves to its own tenant's key,
      and a key only ever sees its own workspace's records.

Returns ConnectorResult to match the rest of the business layer (see connectors/base.py).
"""
import os

import httpx

from backend.lib.business.connectors.base import ConnectorResult
from backend.lib.business.twenty import workspaces


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
        """True iff both env vars are set — the single shared instance (Phase 1)."""
        return bool(os.getenv("TWENTY_API_URL", "").strip() and os.getenv("TWENTY_API_KEY", "").strip())

    @classmethod
    async def for_user(cls, user_id: str) -> "TwentyClient | None":
        """Resolve the Twenty client for a specific user (Phase 2 multi-tenant).

        Order:
          1. The user's OWN provisioned workspace (crm_client_workspaces) — its
             base_url + workspace-scoped api_key. This is the isolation boundary:
             one client's key never resolves another client's records.
          2. Fall back to the single shared instance from env (Phase 1) so existing
             single-workspace deployments keep working unchanged.
          3. None if neither is configured.
        """
        ws = await workspaces.get_workspace(user_id)
        if ws and ws.get("base_url") and ws.get("api_key"):
            return cls(ws["base_url"], ws["api_key"])
        return cls.from_env()

    @staticmethod
    async def configured_for_user(user_id: str) -> bool:
        """True iff this user can reach a CRM — their own workspace OR the shared env instance."""
        if TwentyClient.configured():
            return True
        return await workspaces.has_workspace(user_id)

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
