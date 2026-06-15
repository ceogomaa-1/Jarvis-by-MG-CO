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
import base64
import os
import re
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib.parse import urlencode

import httpx

from backend.lib.business.connectors.base import BaseConnector, ConnectorResult

GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


def _b64url_decode(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")


def _extract_body_text(payload: dict) -> str:
    """Recursively find the best text body (text/plain preferred, text/html stripped) in a Gmail message payload."""
    mime_type = payload.get("mimeType", "")
    body = payload.get("body", {})
    if mime_type == "text/plain" and body.get("data"):
        return _b64url_decode(body["data"])
    if mime_type == "text/html" and body.get("data") and not payload.get("parts"):
        return re.sub(r"<[^>]+>", " ", _b64url_decode(body["data"]))

    for part in payload.get("parts", []) or []:
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            return _b64url_decode(part["body"]["data"])
    for part in payload.get("parts", []) or []:
        if part.get("mimeType") == "text/html" and part.get("body", {}).get("data"):
            return re.sub(r"<[^>]+>", " ", _b64url_decode(part["body"]["data"]))
        if part.get("parts"):
            nested = _extract_body_text(part)
            if nested:
                return nested
    return ""


def _build_mime_message(to: str, subject: str, body: str, cc: str = "", attachments: list[dict] | None = None) -> str:
    """Build a base64url-encoded RFC 2822 message, optionally multipart with attachments.

    Each attachment dict: {"filename": str, "content_type": str, "content_b64": str}.
    """
    attachments = attachments or []
    if attachments:
        msg = MIMEMultipart("mixed")
        msg.attach(MIMEText(body, "plain", "utf-8"))
    else:
        msg = MIMEText(body, "plain", "utf-8")

    msg["To"] = to
    msg["Subject"] = subject
    if cc:
        msg["Cc"] = cc

    for att in attachments:
        content_type = att.get("content_type") or "application/octet-stream"
        maintype, _, subtype = content_type.partition("/")
        part = MIMEBase(maintype or "application", subtype or "octet-stream")
        part.set_payload(base64.b64decode(att["content_b64"]))
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment", filename=att.get("filename") or "attachment")
        msg.attach(part)

    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


def _ensure_timezone(d: dict | None, default_tz: str = "America/Toronto") -> dict | None:
    if d and "dateTime" in d and "timeZone" not in d:
        return {**d, "timeZone": default_tz}
    return d

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
        event_body = dict(event_body)
        event_body["start"] = _ensure_timezone(event_body.get("start"))
        event_body["end"] = _ensure_timezone(event_body.get("end"))
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

    async def update_calendar_event(
        self, event_id: str, summary: str | None = None, description: str | None = None,
        start: dict | None = None, end: dict | None = None, location: str | None = None,
    ) -> ConnectorResult:
        access_token = await self._get_fresh_access_token()
        if not access_token:
            return ConnectorResult(ok=False, error="Could not get Google access token.")
        try:
            async with httpx.AsyncClient() as client:
                # Fetch existing event
                get_resp = await client.get(
                    f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{event_id}",
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=15.0,
                )
                get_resp.raise_for_status()
                event = get_resp.json()
                # Apply only the provided fields
                if summary is not None:
                    event["summary"] = summary
                if description is not None:
                    event["description"] = description
                if start is not None:
                    event["start"] = _ensure_timezone(start)
                if end is not None:
                    event["end"] = _ensure_timezone(end)
                if location is not None:
                    event["location"] = location
                put_resp = await client.put(
                    f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{event_id}",
                    headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                    json=event,
                    timeout=15.0,
                )
                put_resp.raise_for_status()
                updated = put_resp.json()
            return ConnectorResult(ok=True, data={
                "event_id": updated["id"],
                "summary": updated.get("summary"),
                "start": updated.get("start"),
                "end": updated.get("end"),
                "link": updated.get("htmlLink"),
                "status": "updated",
            })
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Update event failed: {e}")

    async def delete_calendar_event(self, event_id: str) -> ConnectorResult:
        access_token = await self._get_fresh_access_token()
        if not access_token:
            return ConnectorResult(ok=False, error="Could not get Google access token.")
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.delete(
                    f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{event_id}",
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=15.0,
                )
                resp.raise_for_status()
            return ConnectorResult(ok=True, data={"event_id": event_id, "status": "deleted"})
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Delete event failed: {e}")

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
                        f"{GMAIL_BASE}/messages/{msg['id']}",
                        headers={"Authorization": f"Bearer {access_token}"},
                        params={"format": "metadata", "metadataHeaders": ["Subject", "From", "Date"]},
                        timeout=10.0,
                    )
                    if detail.status_code == 200:
                        d = detail.json()
                        headers = {h["name"]: h["value"] for h in d.get("payload", {}).get("headers", [])}
                        label_ids = d.get("labelIds", [])
                        emails.append({
                            "id": msg["id"],
                            "subject": headers.get("Subject", ""),
                            "from": headers.get("From", ""),
                            "date": headers.get("Date", ""),
                            "snippet": d.get("snippet", ""),
                            "unread": "UNREAD" in label_ids,
                            "label_ids": label_ids,
                        })
            return ConnectorResult(ok=True, data={"emails": emails})
        except Exception as e:
            return ConnectorResult(ok=False, error=f"List emails failed: {e}")

    async def send_email(
        self, to: str, subject: str, body: str, cc: str = "", attachments: list[dict] | None = None,
    ) -> ConnectorResult:
        access_token = await self._get_fresh_access_token()
        if not access_token:
            return ConnectorResult(ok=False, error="Could not get Google access token.")
        try:
            raw = _build_mime_message(to, subject, body, cc=cc, attachments=attachments)
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Could not build message: {e}")
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{GMAIL_BASE}/messages/send",
                    headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                    json={"raw": raw},
                    timeout=30.0,
                )
            resp.raise_for_status()
            return ConnectorResult(ok=True, data={"message_id": resp.json()["id"], "status": "sent"})
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Send email failed: {e}")

    # ─── Drafts ────────────────────────────────────────────────────────────────

    async def create_draft(
        self, to: str, subject: str, body: str, cc: str = "", attachments: list[dict] | None = None,
    ) -> ConnectorResult:
        access_token = await self._get_fresh_access_token()
        if not access_token:
            return ConnectorResult(ok=False, error="Could not get Google access token.")
        try:
            raw = _build_mime_message(to, subject, body, cc=cc, attachments=attachments)
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Could not build message: {e}")
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{GMAIL_BASE}/drafts",
                    headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                    json={"message": {"raw": raw}},
                    timeout=30.0,
                )
            resp.raise_for_status()
            data = resp.json()
            return ConnectorResult(ok=True, data={
                "draft_id": data["id"],
                "message_id": data.get("message", {}).get("id"),
                "status": "draft_created",
            })
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Create draft failed: {e}")

    async def list_drafts(self, max_results: int = 10) -> ConnectorResult:
        access_token = await self._get_fresh_access_token()
        if not access_token:
            return ConnectorResult(ok=False, error="Could not get Google access token.")
        try:
            async with httpx.AsyncClient() as client:
                list_resp = await client.get(
                    f"{GMAIL_BASE}/drafts",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params={"maxResults": max_results},
                    timeout=15.0,
                )
                list_resp.raise_for_status()
                drafts = list_resp.json().get("drafts", [])

                results = []
                for d in drafts[:max_results]:
                    detail = await client.get(
                        f"{GMAIL_BASE}/drafts/{d['id']}",
                        headers={"Authorization": f"Bearer {access_token}"},
                        params={"format": "metadata", "metadataHeaders": ["Subject", "To", "Date"]},
                        timeout=10.0,
                    )
                    if detail.status_code == 200:
                        dd = detail.json()
                        msg = dd.get("message", {})
                        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
                        results.append({
                            "draft_id": dd["id"],
                            "message_id": msg.get("id"),
                            "to": headers.get("To", ""),
                            "subject": headers.get("Subject", ""),
                            "date": headers.get("Date", ""),
                            "snippet": msg.get("snippet", ""),
                        })
            return ConnectorResult(ok=True, data={"drafts": results})
        except Exception as e:
            return ConnectorResult(ok=False, error=f"List drafts failed: {e}")

    async def get_draft(self, draft_id: str) -> ConnectorResult:
        access_token = await self._get_fresh_access_token()
        if not access_token:
            return ConnectorResult(ok=False, error="Could not get Google access token.")
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{GMAIL_BASE}/drafts/{draft_id}",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params={"format": "full"},
                    timeout=15.0,
                )
            resp.raise_for_status()
            data = resp.json()
            msg = data.get("message", {})
            headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
            return ConnectorResult(ok=True, data={
                "draft_id": data["id"],
                "message_id": msg.get("id"),
                "to": headers.get("To", ""),
                "cc": headers.get("Cc", ""),
                "subject": headers.get("Subject", ""),
                "body": _extract_body_text(msg.get("payload", {}))[:5000],
            })
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Get draft failed: {e}")

    # ─── Messages ──────────────────────────────────────────────────────────────

    async def get_message(self, message_id: str) -> ConnectorResult:
        access_token = await self._get_fresh_access_token()
        if not access_token:
            return ConnectorResult(ok=False, error="Could not get Google access token.")
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{GMAIL_BASE}/messages/{message_id}",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params={"format": "full"},
                    timeout=15.0,
                )
            resp.raise_for_status()
            d = resp.json()
            headers = {h["name"]: h["value"] for h in d.get("payload", {}).get("headers", [])}
            label_ids = d.get("labelIds", [])
            return ConnectorResult(ok=True, data={
                "id": d["id"],
                "thread_id": d.get("threadId"),
                "subject": headers.get("Subject", ""),
                "from": headers.get("From", ""),
                "to": headers.get("To", ""),
                "date": headers.get("Date", ""),
                "snippet": d.get("snippet", ""),
                "body": _extract_body_text(d.get("payload", {}))[:5000],
                "label_ids": label_ids,
                "unread": "UNREAD" in label_ids,
            })
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Get message failed: {e}")

    async def modify_labels(
        self, message_id: str, add_labels: list[str] | None = None, remove_labels: list[str] | None = None,
    ) -> ConnectorResult:
        access_token = await self._get_fresh_access_token()
        if not access_token:
            return ConnectorResult(ok=False, error="Could not get Google access token.")
        body: dict = {}
        if add_labels:
            body["addLabelIds"] = add_labels
        if remove_labels:
            body["removeLabelIds"] = remove_labels
        if not body:
            return ConnectorResult(ok=False, error="add_labels or remove_labels is required.")
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{GMAIL_BASE}/messages/{message_id}/modify",
                    headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                    json=body,
                    timeout=15.0,
                )
            resp.raise_for_status()
            data = resp.json()
            return ConnectorResult(ok=True, data={"id": data["id"], "label_ids": data.get("labelIds", [])})
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Modify labels failed: {e}")

    async def mark_read(self, message_id: str, read: bool = True) -> ConnectorResult:
        if read:
            return await self.modify_labels(message_id, remove_labels=["UNREAD"])
        return await self.modify_labels(message_id, add_labels=["UNREAD"])

    # ─── Calendar free/busy ──────────────────────────────────────────────────────

    async def freebusy(self, time_min: str, time_max: str, calendar_ids: list[str] | None = None) -> ConnectorResult:
        access_token = await self._get_fresh_access_token()
        if not access_token:
            return ConnectorResult(ok=False, error="Could not get Google access token.")
        calendar_ids = calendar_ids or ["primary"]
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://www.googleapis.com/calendar/v3/freeBusy",
                    headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                    json={"timeMin": time_min, "timeMax": time_max, "items": [{"id": c} for c in calendar_ids]},
                    timeout=15.0,
                )
            resp.raise_for_status()
            data = resp.json()
            busy = []
            for cal_id, info in data.get("calendars", {}).items():
                for period in info.get("busy", []):
                    busy.append({"calendar": cal_id, "start": period["start"], "end": period["end"]})
            return ConnectorResult(ok=True, data={"busy": busy, "time_min": time_min, "time_max": time_max})
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Free/busy lookup failed: {e}")

    async def find_free_slot(
        self,
        duration_min: int,
        time_min: str | None = None,
        time_max: str | None = None,
        work_start_hour: int = 9,
        work_end_hour: int = 17,
        timezone_name: str = "America/Toronto",
    ) -> ConnectorResult:
        """Find the next free slot of `duration_min` minutes within working hours,
        using the primary calendar's free/busy data."""
        from datetime import datetime, timedelta

        import pytz

        tz = pytz.timezone(timezone_name)
        now = datetime.now(tz)

        if time_min:
            start_dt = datetime.fromisoformat(time_min)
            start_dt = tz.localize(start_dt) if start_dt.tzinfo is None else start_dt.astimezone(tz)
        else:
            start_dt = now

        if time_max:
            end_dt = datetime.fromisoformat(time_max)
            end_dt = tz.localize(end_dt) if end_dt.tzinfo is None else end_dt.astimezone(tz)
        else:
            end_dt = start_dt + timedelta(days=7)

        fb = await self.freebusy(
            start_dt.astimezone(pytz.utc).isoformat(), end_dt.astimezone(pytz.utc).isoformat(),
        )
        if not fb.ok:
            return fb

        busy_periods = []
        for b in fb.data["busy"]:
            bs = datetime.fromisoformat(b["start"].replace("Z", "+00:00")).astimezone(tz)
            be = datetime.fromisoformat(b["end"].replace("Z", "+00:00")).astimezone(tz)
            busy_periods.append((bs, be))
        busy_periods.sort()

        duration = timedelta(minutes=duration_min)
        cursor = start_dt

        # Cap iterations so a misconfigured range can't loop forever.
        for _ in range(2000):
            if cursor >= end_dt:
                break

            day_start = cursor.replace(hour=work_start_hour, minute=0, second=0, microsecond=0)
            day_end = cursor.replace(hour=work_end_hour, minute=0, second=0, microsecond=0)

            if cursor < day_start:
                cursor = day_start
            if cursor >= day_end or cursor.weekday() >= 5:
                cursor = (cursor + timedelta(days=1)).replace(hour=work_start_hour, minute=0, second=0, microsecond=0)
                continue

            slot_end = cursor + duration
            if slot_end > day_end:
                cursor = (cursor + timedelta(days=1)).replace(hour=work_start_hour, minute=0, second=0, microsecond=0)
                continue

            overlap = next((b for b in busy_periods if b[0] < slot_end and b[1] > cursor), None)
            if overlap:
                cursor = overlap[1]
                continue

            return ConnectorResult(ok=True, data={
                "start": cursor.isoformat(),
                "end": slot_end.isoformat(),
                "timezone": timezone_name,
            })

        return ConnectorResult(ok=False, error="No free slot found in the given range.")
