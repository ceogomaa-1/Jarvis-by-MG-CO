import base64
from email.mime.text import MIMEText

import httpx

from backend.tools.registry import register_tool
from backend.tools.google_calendar import get_access_token, get_user_refresh_token


def _extract_body(payload: dict) -> str:
    """Recursively extract plain-text body from a Gmail message payload."""
    if not payload:
        return ""
    mime_type = payload.get("mimeType", "")
    if mime_type == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="ignore")
    for part in payload.get("parts", []):
        result = _extract_body(part)
        if result:
            return result
    return ""


@register_tool(
    name="get_emails",
    description="Read recent emails from the user's Gmail inbox. Use when asked about emails, messages, what came in, or checking inbox.",
    parameters={
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "The user's ID",
            },
            "max_results": {
                "type": "integer",
                "description": "Max emails to return",
                "default": 5,
            },
            "query": {
                "type": "string",
                "description": "Search query e.g. 'from:boss@company.com' or 'subject:invoice'",
                "default": "",
            },
        },
        "required": ["user_id"],
    },
)
async def get_emails(user_id: str, max_results: int = 5, query: str = "") -> str:
    refresh_token = await get_user_refresh_token(user_id)
    if not refresh_token:
        return "No Gmail connected."

    access_token = await get_access_token(refresh_token)

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"maxResults": max_results, "q": query if query else "in:inbox"},
        )

    messages = resp.json().get("messages", [])
    if not messages:
        return "No emails found."

    results = []
    async with httpx.AsyncClient() as client:
        for msg in messages[:max_results]:
            detail = await client.get(
                f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg['id']}",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"format": "full"},
            )
            msg_data = detail.json()
            payload = msg_data.get("payload", {})
            raw_headers = payload.get("headers", [])
            hd = {h["name"]: h["value"] for h in raw_headers}
            body = _extract_body(payload)
            body_preview = body[:500].strip() if body else "No body content"
            results.append(
                f"From: {hd.get('From', 'Unknown')}\n"
                f"Subject: {hd.get('Subject', 'No subject')}\n"
                f"Date: {hd.get('Date', '')}\n"
                f"Message: {body_preview}"
            )

    return "Recent emails:\n\n" + "\n\n---\n\n".join(results)


@register_tool(
    name="send_email",
    description="Send an email on behalf of the user. Use when asked to send, reply, or draft and send an email.",
    parameters={
        "type": "object",
        "properties": {
            "user_id": {"type": "string"},
            "to": {
                "type": "string",
                "description": "Recipient email address",
            },
            "subject": {
                "type": "string",
                "description": "Email subject line",
            },
            "body": {
                "type": "string",
                "description": "Email body content",
            },
        },
        "required": ["user_id", "to", "subject", "body"],
    },
)
async def send_email(user_id: str, to: str, subject: str, body: str) -> str:
    refresh_token = await get_user_refresh_token(user_id)
    if not refresh_token:
        return "No Gmail connected."

    access_token = await get_access_token(refresh_token)

    message = MIMEText(body)
    message["to"] = to
    message["subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json={"raw": raw},
        )

    if resp.status_code in (200, 201):
        return f"Email sent to {to} with subject '{subject}'"
    return f"Failed to send email: {resp.text}"
