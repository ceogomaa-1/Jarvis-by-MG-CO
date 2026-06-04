"""
Google connector — Calendar + Gmail via OAuth 2.0.

AUTH_TYPE = "oauth" signals the frontend to show an OAuth button instead of
credential input fields.

Flow:
  1. Frontend hits  GET /api/business/connections/google/auth?user_id=<uid>
     → backend redirects to Google consent screen
  2. Google redirects back to GOOGLE_REDIRECT_URI_BUSINESS
     → backend exchanges code for tokens, stores in business_connections, redirects to frontend
  3. test() uses refresh_token to get a fresh access_token each call,
     then verifies via Google userinfo API.

All API calls use httpx — no google-auth SDK needed.
"""
import os
from urllib.parse import urlencode

import httpx

from backend.lib.business.connectors.base import BaseConnector, ConnectorResult

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID") or os.getenv("GOOGLE_AUTH_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET") or os.getenv("GOOGLE_AUTH_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv(
    "GOOGLE_REDIRECT_URI_BUSINESS",
    "https://jarvis-backend-4oz6.onrender.com/api/business/connections/google/callback",
)
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://jarvis-by-mg-co.vercel.app")

SCOPES = " ".join([
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
])


class GoogleConnector(BaseConnector):
    CONNECTOR_TYPE = "google"
    DISPLAY_NAME = "Google (Calendar + Gmail)"
    DESCRIPTION = "Access Google Calendar events and Gmail — read, create events, read and send emails."
    DOCS_URL = "https://console.cloud.google.com/"
    AUTH_TYPE = "oauth"
    REQUIRED_FIELDS = {}  # no user-filled fields for OAuth

    # ─── OAuth helpers (called by route handlers, not by the framework) ──────

    @staticmethod
    def get_auth_url(user_id: str) -> str:
        params = {
            "client_id": GOOGLE_CLIENT_ID,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "response_type": "code",
            "scope": SCOPES,
            "access_type": "offline",
            "prompt": "consent",
            "state": user_id,
        }
        return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)

    @staticmethod
    async def handle_callback(code: str) -> dict:
        """Exchange auth code for access + refresh tokens. Returns token dict."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "redirect_uri": GOOGLE_REDIRECT_URI,
                    "grant_type": "authorization_code",
                },
                timeout=15.0,
            )
        tokens = resp.json()
        return {
            "access_token": tokens.get("access_token", ""),
            "refresh_token": tokens.get("refresh_token", ""),
            "token_type": tokens.get("token_type", "Bearer"),
            "expires_in": tokens.get("expires_in"),
            "scope": tokens.get("scope", ""),
        }

    # ─── BaseConnector interface ──────────────────────────────────────────────

    async def _get_fresh_access_token(self) -> str | None:
        """Use stored refresh_token to get a fresh access_token."""
        refresh_token = self.credentials.get("refresh_token", "")
        if not refresh_token:
            return None
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "refresh_token": refresh_token,
                        "client_id": GOOGLE_CLIENT_ID,
                        "client_secret": GOOGLE_CLIENT_SECRET,
                        "grant_type": "refresh_token",
                    },
                    timeout=15.0,
                )
            if resp.status_code == 200:
                return resp.json().get("access_token")
        except Exception:
            pass
        return None

    async def test(self) -> ConnectorResult:
        if not self.credentials.get("refresh_token"):
            return ConnectorResult(ok=False, error="Not connected — click 'Connect with Google' to authorize.")
        access_token = await self._get_fresh_access_token()
        if not access_token:
            return ConnectorResult(ok=False, error="Failed to refresh Google token — try reconnecting.")
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://www.googleapis.com/oauth2/v2/userinfo",
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=10.0,
                )
            resp.raise_for_status()
            info = resp.json()
            return ConnectorResult(ok=True, data={"email": info.get("email"), "name": info.get("name")})
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Google connection failed: {e}")

    async def list_calendar_events(self, max_results: int = 10) -> ConnectorResult:
        from datetime import datetime, timezone
        access_token = await self._get_fresh_access_token()
        if not access_token:
            return ConnectorResult(ok=False, error="Could not get Google access token.")
        now = datetime.now(timezone.utc).isoformat()
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://www.googleapis.com/calendar/v3/calendars/primary/events",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params={
                        "timeMin": now,
                        "maxResults": max_results,
                        "singleEvents": "true",
                        "orderBy": "startTime",
                    },
                    timeout=15.0,
                )
            resp.raise_for_status()
            items = resp.json().get("items", [])
            events = [
                {
                    "id": e["id"],
                    "summary": e.get("summary", "(no title)"),
                    "start": e.get("start", {}),
                    "end": e.get("end", {}),
                    "location": e.get("location"),
                    "description": e.get("description"),
                }
                for e in items
            ]
            return ConnectorResult(ok=True, data={"events": events})
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Calendar list failed: {e}")

    async def create_calendar_event(self, event_body: dict) -> ConnectorResult:
        access_token = await self._get_fresh_access_token()
        if not access_token:
            return ConnectorResult(ok=False, error="Could not get Google access token.")
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://www.googleapis.com/calendar/v3/calendars/primary/events",
                    headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                    json=event_body,
                    timeout=15.0,
                )
            resp.raise_for_status()
            data = resp.json()
            return ConnectorResult(ok=True, data={"event_id": data["id"], "link": data.get("htmlLink")})
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Create event failed: {e}")

    async def list_emails(self, max_results: int = 10, query: str = "") -> ConnectorResult:
        access_token = await self._get_fresh_access_token()
        if not access_token:
            return ConnectorResult(ok=False, error="Could not get Google access token.")
        try:
            async with httpx.AsyncClient() as client:
                params: dict = {"maxResults": max_results, "userId": "me"}
                if query:
                    params["q"] = query
                list_resp = await client.get(
                    "https://gmail.googleapis.com/gmail/v1/users/me/messages",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params=params,
                    timeout=15.0,
                )
                list_resp.raise_for_status()
                messages = list_resp.json().get("messages", [])

                emails = []
                for msg in messages[:max_results]:
                    detail = await client.get(
                        f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg['id']}",
                        headers={"Authorization": f"Bearer {access_token}"},
                        params={"format": "metadata", "metadataHeaders": ["Subject", "From", "Date"]},
                        timeout=10.0,
                    )
                    if detail.status_code == 200:
                        d = detail.json()
                        headers = {h["name"]: h["value"] for h in d.get("payload", {}).get("headers", [])}
                        emails.append({
                            "id": msg["id"],
                            "subject": headers.get("Subject", ""),
                            "from": headers.get("From", ""),
                            "date": headers.get("Date", ""),
                            "snippet": d.get("snippet", ""),
                        })
            return ConnectorResult(ok=True, data={"emails": emails})
        except Exception as e:
            return ConnectorResult(ok=False, error=f"List emails failed: {e}")

    async def send_email(self, to: str, subject: str, body: str) -> ConnectorResult:
        import base64
        from email.mime.text import MIMEText
        access_token = await self._get_fresh_access_token()
        if not access_token:
            return ConnectorResult(ok=False, error="Could not get Google access token.")
        msg = MIMEText(body)
        msg["to"] = to
        msg["subject"] = subject
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                    headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                    json={"raw": raw},
                    timeout=15.0,
                )
            resp.raise_for_status()
            return ConnectorResult(ok=True, data={"message_id": resp.json()["id"], "status": "sent"})
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Send email failed: {e}")
