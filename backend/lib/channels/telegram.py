"""Telegram Bot API adapter — send/receive text + media for the OS1 channel.

Thin wrapper over the HTTP Bot API. No global state; the bot token is read per call so a
missing token simply makes the channel inert.
"""
import base64

import httpx

from backend.lib.channels import config

API = "https://api.telegram.org"
TELEGRAM_MAX_LEN = 4096


def _base() -> str:
    return f"{API}/bot{config.telegram_bot_token()}"


async def send_message(chat_id, text: str) -> None:
    """Send text, chunked to Telegram's 4096-char limit."""
    if not text:
        return
    token = config.telegram_bot_token()
    if not token:
        return
    chunks = _chunk(text, TELEGRAM_MAX_LEN)
    async with httpx.AsyncClient(timeout=30.0) as client:
        for chunk in chunks:
            try:
                await client.post(f"{_base()}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": chunk,
                    "disable_web_page_preview": True,
                })
            except Exception as e:
                print(f"[TELEGRAM] sendMessage error: {e}")


async def send_typing(chat_id) -> None:
    if not config.telegram_bot_token():
        return
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(f"{_base()}/sendChatAction", json={"chat_id": chat_id, "action": "typing"})
    except Exception:
        pass


async def download_attachment(file_id: str, media_type: str, name: str = "") -> dict | None:
    """getFile → download bytes → return a base64 attachment dict the agent understands."""
    token = config.telegram_bot_token()
    if not token or not file_id:
        return None
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            meta = await client.get(f"{_base()}/getFile", params={"file_id": file_id})
            if meta.status_code != 200:
                return None
            file_path = (meta.json().get("result") or {}).get("file_path")
            if not file_path:
                return None
            blob = await client.get(f"{API}/file/bot{token}/{file_path}")
            if blob.status_code != 200:
                return None
            data = base64.b64encode(blob.content).decode("ascii")
    except Exception as e:
        print(f"[TELEGRAM] download error: {e}")
        return None

    kind = "image" if media_type.startswith("image/") else (
        "document" if media_type == "application/pdf" else "text_file")
    return {"type": kind, "media_type": media_type, "data": data, "name": name}


async def extract_attachments(message: dict) -> list:
    """Pull downloadable media out of a Telegram message → agent attachment dicts."""
    out: list = []
    # Photo: array of sizes, largest last.
    photos = message.get("photo") or []
    if photos:
        largest = photos[-1]
        att = await download_attachment(largest.get("file_id"), "image/jpeg", "photo.jpg")
        if att:
            out.append(att)
    # Document (pdf, csv, txt, images sent as files…).
    doc = message.get("document")
    if doc:
        att = await download_attachment(
            doc.get("file_id"), doc.get("mime_type") or "application/octet-stream",
            doc.get("file_name") or "file")
        if att:
            out.append(att)
    return out


def parse_message(update: dict) -> dict | None:
    """Normalize an inbound update into {chat_id, username, text, message}.

    Returns None for updates we don't handle (edited messages, channel posts, etc.)."""
    message = update.get("message") or update.get("edited_message")
    if not message:
        return None
    chat = message.get("chat") or {}
    frm = message.get("from") or {}
    return {
        "chat_id": chat.get("id"),
        "username": frm.get("username") or frm.get("first_name") or "",
        "text": message.get("text") or message.get("caption") or "",
        "message": message,
    }


async def set_webhook(url: str, secret: str = "") -> dict:
    """Register the webhook with Telegram (one-time setup helper)."""
    payload = {"url": url, "allowed_updates": ["message", "edited_message"]}
    if secret:
        payload["secret_token"] = secret
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(f"{_base()}/setWebhook", json=payload)
        try:
            return resp.json()
        except Exception:
            return {"ok": False, "status": resp.status_code}


def _chunk(text: str, size: int) -> list:
    if len(text) <= size:
        return [text]
    chunks, buf = [], ""
    for line in text.split("\n"):
        if len(buf) + len(line) + 1 > size:
            if buf:
                chunks.append(buf)
            # A single very long line must still be hard-split.
            while len(line) > size:
                chunks.append(line[:size])
                line = line[size:]
            buf = line
        else:
            buf = f"{buf}\n{line}" if buf else line
    if buf:
        chunks.append(buf)
    return chunks
