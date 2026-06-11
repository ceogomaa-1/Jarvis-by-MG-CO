"""
GoHighLevel CRM connector.

Supports two API generations:
  - v1 (rest.gohighlevel.com) — legacy API key, used by the original
    contacts/pipelines/opportunities/appointments actions.
  - v2 (services.leadconnectorhq.com) — Private Integration token + Location ID,
    required for the Real Estate Operator Suite (stale-lead scanner, notes, etc).

Get a Private Integration token: GHL → Settings → Private Integrations.
Get the Location ID: GHL → Settings → Business Profile.
"""
import httpx

from backend.lib.business.connectors.base import BaseConnector, ConnectorResult

V1_BASE = "https://rest.gohighlevel.com/v1"
V2_BASE = "https://services.leadconnectorhq.com"
V2_VERSION = "2021-07-28"


class GoHighLevelConnector(BaseConnector):
    CONNECTOR_TYPE = "gohighlevel"
    DISPLAY_NAME = "GoHighLevel"
    DESCRIPTION = "CRM contacts, pipelines, opportunities, appointments, and the Real Estate stale-lead scanner."
    DOCS_URL = "https://highlevel.stoplight.io/"
    STATUS_NOTE = (
        "Use a Private Integration token (Settings -> Private Integrations) "
        "and your Location ID (Settings -> Business Profile)."
    )
    REQUIRED_FIELDS = {
        "api_key": {
            "label": "Private Integration Token",
            "type": "password",
            "placeholder": "pit-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
            "secret": True,
            "required": True,
        },
        "location_id": {
            "label": "Location ID",
            "type": "text",
            "placeholder": "e.g. ve9EPM428h8vShlRW1KT",
            "secret": False,
            "required": True,
        },
    }

    # ─── v1 (legacy) ────────────────────────────────────────────
    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.credentials.get('api_key', '').strip()}",
            "Content-Type": "application/json",
        }

    # ─── v2 (Real Estate Operator Suite) ───────────────────────
    def _v2_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.credentials.get('api_key', '').strip()}",
            "Version": V2_VERSION,
            "Content-Type": "application/json",
        }

    def _location_id(self) -> str:
        return self.credentials.get("location_id", "").strip()

    async def test(self) -> ConnectorResult:
        missing = self._missing_fields()
        if missing:
            return ConnectorResult(ok=False, error=f"Missing required fields: {', '.join(missing)}")
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{V2_BASE}/locations/{self._location_id()}",
                    headers=self._v2_headers(),
                    timeout=10.0,
                )
            if resp.status_code in (401, 403):
                return ConnectorResult(
                    ok=False,
                    error="Invalid Private Integration token — check Settings -> Private Integrations in GoHighLevel.",
                )
            if resp.status_code == 404:
                return ConnectorResult(
                    ok=False,
                    error="Location ID not found — check Settings -> Business Profile in GoHighLevel.",
                )
            resp.raise_for_status()
            return ConnectorResult(ok=True, data={"message": "Connected to GoHighLevel"})
        except Exception as e:
            return ConnectorResult(ok=False, error=f"GoHighLevel connection failed: {e}")

    async def list_contacts_v2(self, limit: int = 100, start_after_id: str | None = None, start_after: str | None = None) -> ConnectorResult:
        try:
            params = {"locationId": self._location_id(), "limit": limit}
            if start_after_id:
                params["startAfterId"] = start_after_id
            if start_after:
                params["startAfter"] = start_after
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{V2_BASE}/contacts/", headers=self._v2_headers(), params=params, timeout=20.0)
            if resp.status_code in (401, 403):
                return ConnectorResult(ok=False, error="GoHighLevel rejected the request — reconnect with a valid Private Integration token.")
            resp.raise_for_status()
            return ConnectorResult(ok=True, data=resp.json())
        except Exception as e:
            return ConnectorResult(ok=False, error=f"List contacts failed: {e}")

    async def search_contacts_v2(self, query: str, limit: int = 10) -> ConnectorResult:
        try:
            params = {"locationId": self._location_id(), "query": query, "limit": limit}
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{V2_BASE}/contacts/", headers=self._v2_headers(), params=params, timeout=15.0)
            resp.raise_for_status()
            return ConnectorResult(ok=True, data=resp.json())
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Search contacts failed: {e}")

    async def get_contact_notes(self, contact_id: str) -> ConnectorResult:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{V2_BASE}/contacts/{contact_id}/notes", headers=self._v2_headers(), timeout=15.0)
            resp.raise_for_status()
            return ConnectorResult(ok=True, data=resp.json())
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Get contact notes failed: {e}")

    async def add_note(self, contact_id: str, note: str) -> ConnectorResult:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{V2_BASE}/contacts/{contact_id}/notes",
                    headers=self._v2_headers(),
                    json={"body": note},
                    timeout=15.0,
                )
            resp.raise_for_status()
            return ConnectorResult(ok=True, data=resp.json())
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Add note failed: {e}")

    # ─── v1 (legacy, still used by existing tool registrations) ──
    async def list_contacts(self, limit: int = 20) -> ConnectorResult:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{V1_BASE}/contacts/", headers=self._headers(), params={"limit": limit}, timeout=15.0)
            resp.raise_for_status()
            return ConnectorResult(ok=True, data=resp.json())
        except Exception as e:
            return ConnectorResult(ok=False, error=f"List contacts failed: {e}")

    async def search_contacts(self, query: str) -> ConnectorResult:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{V1_BASE}/contacts/search/", headers=self._headers(), params={"query": query}, timeout=15.0)
            resp.raise_for_status()
            return ConnectorResult(ok=True, data=resp.json())
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Search contacts failed: {e}")

    async def create_contact(self, contact_data: dict) -> ConnectorResult:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(f"{V1_BASE}/contacts/", headers=self._headers(), json=contact_data, timeout=15.0)
            resp.raise_for_status()
            return ConnectorResult(ok=True, data=resp.json())
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Create contact failed: {e}")

    async def list_pipelines(self) -> ConnectorResult:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{V1_BASE}/pipelines/", headers=self._headers(), timeout=15.0)
            resp.raise_for_status()
            return ConnectorResult(ok=True, data=resp.json())
        except Exception as e:
            return ConnectorResult(ok=False, error=f"List pipelines failed: {e}")

    async def list_opportunities(self, pipeline_id: str) -> ConnectorResult:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{V1_BASE}/pipelines/{pipeline_id}/opportunities",
                    headers=self._headers(), timeout=15.0,
                )
            resp.raise_for_status()
            return ConnectorResult(ok=True, data=resp.json())
        except Exception as e:
            return ConnectorResult(ok=False, error=f"List opportunities failed: {e}")

    async def list_appointments(self) -> ConnectorResult:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{V1_BASE}/appointments/", headers=self._headers(), timeout=15.0)
            resp.raise_for_status()
            return ConnectorResult(ok=True, data=resp.json())
        except Exception as e:
            return ConnectorResult(ok=False, error=f"List appointments failed: {e}")
