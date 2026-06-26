"""WhatsApp Business Cloud API adapter — PHASE 2, behind CHANNELS_WHATSAPP_ENABLED.

Mirrors the Telegram adapter (send text, download media, parse inbound) against Meta's Cloud
API so the same run_channel_turn brain serves WhatsApp. Inert unless explicitly enabled with
credentials. Telegram ships first; this is here so phase 2 is a flag flip, not a rebuild.
"""
import base64

import httpx

from backend.lib.channels import config

GRAPH = "https://graph.facebook.com/v18.0"
WHATSAPP_MAX_LEN = 4000


def _headers() -> dict:
    return {"Authorization": f"Bearer {config.whatsapp_token()}", "Content-Type": "application/json"}


async def send_message(to: str, text: str) -> None:
    if not text or not config.whatsapp_enabled():
        return
    phone_id = config.whatsapp_phone_number_id()
    async with httpx.AsyncClient(timeout=30.0) as client:
        for chunk in _chunk(text, WHATSAPP_MAX_LEN):
            try:
                await client.post(f"{GRAPH}/{phone_id}/messages", headers=_headers(), json={
                    "messaging_product": "whatsapp",
                    "to": to,
                    "type": "text",
                    "text": {"body": chunk, "preview_url": False},
                })
            except Exception as e:
                print(f"[WHATSAPP] send error: {e}")


async def _download_media(media_id: str, media_type: str, name: str = "") -> dict | None:
    if not media_id:
        return None
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            meta = await client.get(f"{GRAPH}/{media_id}", headers=_headers())
            url = (meta.json() or {}).get("url") if meta.status_code == 200 else None
            if not url:
                return None
            blob = await client.get(url, headers={"Authorization": f"Bearer {config.whatsapp_token()}"})
            if blob.status_code != 200:
                return None
            data = base64.b64encode(blob.content).decode("ascii")
    except Exception as e:
        print(f"[WHATSAPP] media error: {e}")
        return None
    kind = "image" if media_type.startswith("image/") else (
        "document" if media_type == "application/pdf" else "text_file")
    return {"type": kind, "media_type": media_type, "data": data, "name": name}


async def extract_attachments(message: dict) -> list:
    out: list = []
    img = message.get("image")
    if img:
        att = await _download_media(img.get("id"), img.get("mime_type") or "image/jpeg", "photo.jpg")
        if att:
            out.append(att)
    doc = message.get("document")
    if doc:
        att = await _download_media(doc.get("id"), doc.get("mime_type") or "application/octet-stream",
                                    doc.get("filename") or "file")
        if att:
            out.append(att)
    return out


def parse_inbound(payload: dict) -> list:
    """Normalize a Cloud API webhook payload into a list of {from, username, text, message}."""
    out: list = []
    for entry in payload.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            value = change.get("value") or {}
            contacts = {c.get("wa_id"): (c.get("profile") or {}).get("name", "")
                        for c in (value.get("contacts") or [])}
            for msg in value.get("messages", []) or []:
                frm = msg.get("from")
                text = ""
                if msg.get("type") == "text":
                    text = (msg.get("text") or {}).get("body", "")
                else:
                    text = (msg.get(msg.get("type"), {}) or {}).get("caption", "")
                out.append({
                    "from": frm,
                    "username": contacts.get(frm, ""),
                    "text": text,
                    "message": msg,
                })
    return out


def _chunk(text: str, size: int) -> list:
    return [text[i:i + size] for i in range(0, len(text), size)] or [text]
