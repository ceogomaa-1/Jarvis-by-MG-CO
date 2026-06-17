"""
GoHighLevel CRM connector.

Everything goes through the v2 (LeadConnector) API at
services.leadconnectorhq.com, authenticated with a Private Integration token
(Version 2021-07-28) + Location ID. The legacy v1 API (rest.gohighlevel.com)
does not accept Private Integration tokens, so there is no v1 path here.

Get a Private Integration token: GHL -> Settings -> Private Integrations.
Get the Location ID: GHL -> Settings -> Business Profile.
"""
import time

import httpx

from backend.lib.business.connectors.base import BaseConnector, ConnectorResult

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

    def _v2_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.credentials.get('api_key', '').strip()}",
            "Version": V2_VERSION,
            "Content-Type": "application/json",
        }

    def _location_id(self) -> str:
        return self.credentials.get("location_id", "").strip()

    @staticmethod
    def _api_error(action: str, resp: httpx.Response) -> str:
        """Error message that reports the real HTTP status without assuming
        the token is invalid — a 401/403 here means *this call* was rejected,
        not that the Private Integration token needs to be reconnected."""
        detail = resp.text.strip()
        if len(detail) > 300:
            detail = detail[:300] + "..."
        suffix = f" — {detail}" if detail else ""
        return f"{action} failed: GoHighLevel returned HTTP {resp.status_code}{suffix}"

    async def _request(
        self,
        method: str,
        path: str,
        action: str,
        *,
        params: dict | None = None,
        json: dict | None = None,
        timeout: float = 15.0,
    ) -> ConnectorResult:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.request(
                    method,
                    f"{V2_BASE}{path}",
                    headers=self._v2_headers(),
                    params=params,
                    json=json,
                    timeout=timeout,
                )
            if resp.status_code >= 400:
                return ConnectorResult(ok=False, error=self._api_error(action, resp))
            return ConnectorResult(ok=True, data=resp.json())
        except Exception as e:
            return ConnectorResult(ok=False, error=f"{action} failed: {e}")

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
        params = {"locationId": self._location_id(), "limit": limit}
        if start_after_id:
            params["startAfterId"] = start_after_id
        if start_after:
            params["startAfter"] = start_after
        return await self._request("GET", "/contacts/", "List contacts", params=params, timeout=20.0)

    async def search_contacts_v2(self, query: str, limit: int = 10) -> ConnectorResult:
        params = {"locationId": self._location_id(), "query": query, "limit": limit}
        return await self._request("GET", "/contacts/", "Search contacts", params=params)

    async def get_contact_notes(self, contact_id: str) -> ConnectorResult:
        return await self._request("GET", f"/contacts/{contact_id}/notes", "Get contact notes")

    async def get_contact_tasks(self, contact_id: str) -> ConnectorResult:
        """List tasks for a contact (v2). Task objects include dueDate + completed."""
        return await self._request("GET", f"/contacts/{contact_id}/tasks", "Get contact tasks")

    async def add_note(self, contact_id: str, note: str) -> ConnectorResult:
        return await self._request("POST", f"/contacts/{contact_id}/notes", "Add note", json={"body": note})

    # ─── Generic gohighlevel__* tools (all v2) ─────────────────
    async def create_contact(self, contact_data: dict) -> ConnectorResult:
        payload = {**contact_data, "locationId": self._location_id()}
        return await self._request("POST", "/contacts/", "Create contact", json=payload)

    async def list_pipelines(self) -> ConnectorResult:
        params = {"locationId": self._location_id()}
        return await self._request("GET", "/opportunities/pipelines", "List pipelines", params=params)

    async def list_opportunities(self, pipeline_id: str) -> ConnectorResult:
        params = {"location_id": self._location_id(), "pipeline_id": pipeline_id}
        return await self._request("GET", "/opportunities/search", "List opportunities", params=params)

    async def list_appointments(self) -> ConnectorResult:
        cal_result = await self._request("GET", "/calendars/", "List calendars", params={"locationId": self._location_id()})
        if not cal_result.ok:
            return cal_result

        calendars = (cal_result.data or {}).get("calendars", [])
        if not calendars:
            return ConnectorResult(
                ok=True,
                data={"events": [], "message": "No calendars are configured in GoHighLevel for this location."},
            )

        now_ms = int(time.time() * 1000)
        thirty_days_ms = 30 * 24 * 60 * 60 * 1000
        params = {
            "locationId": self._location_id(),
            "calendarId": calendars[0].get("id"),
            "startTime": str(now_ms),
            "endTime": str(now_ms + thirty_days_ms),
        }
        return await self._request("GET", "/calendars/events", "List appointments", params=params)
