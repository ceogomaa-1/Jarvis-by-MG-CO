"""OS1 messaging channels API — Telegram (live) + WhatsApp (phase 2, flag-gated).

Endpoints (mounted under /api):
  POST /channels/link/create        web app mints a one-time link code (has_access required)
  GET  /channels/links              list a user's linked channels + channel availability
  POST /channels/unlink             remove a link
  POST /channels/telegram/webhook   inbound Telegram updates
  POST /channels/telegram/set-webhook  one-time webhook registration (admin)
  GET  /channels/whatsapp/webhook   Meta verification challenge
  POST /channels/whatsapp/webhook   inbound WhatsApp messages

Gating mirrors the web app exactly: only users with has_access (active OR grandfathered) can
link, so grandfathered users get this free immediately and only new users are gated. The brain
is the SAME OS1 business agent (see lib/channels/agent.run_channel_turn). Personal untouched.
"""
import asyncio
import re

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from backend.lib.billing import entitlements, store as billing_store
from backend.lib.channels import config, store, telegram, whatsapp
from backend.lib.channels.agent import run_channel_turn
from backend.usage_limits import is_admin

router = APIRouter()

_CODE_RE = re.compile(r"^[A-Z0-9]{6,10}$")

LINK_PROMPT = (
    "👋 I'm Rue. To chat with me here, link your OS1 account: open jarvismgco.com/os1 → "
    "Connections → Rue on Telegram, generate a link code, and send it to me. "
    "(Only OS1 subscribers can link.)"
)
HELP_TEXT = (
    "You're linked to Rue OS1 ✅ Just message me normally — ask questions, send photos or "
    "documents, and I'll help. For actions that change your data (and your CRM cockpit), use "
    "the web app at jarvismgco.com/os1."
)
INACTIVE_TEXT = (
    "Your OS1 subscription isn't active right now. Reactivate at jarvismgco.com/os1 to keep "
    "chatting here."
)


# ── web-app linking endpoints ─────────────────────────────────────────────────────────────
class LinkCreateRequest(BaseModel):
    user_id: str
    email: str = ""
    channel: str = "telegram"


@router.post("/channels/link/create")
async def link_create(body: LinkCreateRequest):
    channel = body.channel if body.channel in ("telegram", "whatsapp") else "telegram"
    sub = await asyncio.to_thread(billing_store.ensure_subscription, body.user_id, body.email or None)
    if not entitlements.has_access(sub):
        return {"ok": False, "error": "Linking is for active OS1 subscribers. Subscribe to enable it."}
    if not config.channel_enabled(channel):
        return {"ok": False, "error": f"The {channel} channel isn't configured yet."}

    code_row = await asyncio.to_thread(store.create_link_code, body.user_id, channel)
    out = {"ok": True, "channel": channel, "code": code_row["code"], "expires_at": code_row["expires_at"]}
    if channel == "telegram":
        bot = config.telegram_bot_username()
        out["bot_username"] = bot
        out["deep_link"] = f"https://t.me/{bot}?start={code_row['code']}" if bot else None
    return out


@router.get("/channels/links")
async def link_list(user_id: str = "", email: str = ""):
    if not user_id:
        return {"links": [], "has_access": False}
    sub = await asyncio.to_thread(billing_store.ensure_subscription, user_id, email or None)
    links = await asyncio.to_thread(store.list_links_for_user, user_id)
    return {
        "has_access": entitlements.has_access(sub),
        "telegram_enabled": config.telegram_enabled(),
        "whatsapp_enabled": config.whatsapp_enabled(),
        "bot_username": config.telegram_bot_username(),
        "links": [{"channel": l["channel"], "channel_username": l.get("channel_username"),
                   "created_at": l.get("created_at")} for l in links],
    }


class UnlinkRequest(BaseModel):
    user_id: str
    channel: str = "telegram"


@router.post("/channels/unlink")
async def link_unlink(body: UnlinkRequest):
    await asyncio.to_thread(store.delete_link, body.user_id, body.channel)
    return {"ok": True}


# ── shared inbound handler ─────────────────────────────────────────────────────────────────
def _extract_code(text: str) -> str:
    stripped = (text or "").strip()
    if stripped.lower().startswith("/start"):
        parts = stripped.split(maxsplit=1)
        token = parts[1].strip().upper() if len(parts) > 1 else ""
        return token if _CODE_RE.match(token) else ""
    token = stripped.upper()
    return token if _CODE_RE.match(token) else ""


async def _handle_inbound(channel, channel_user_id, username, text, message,
                          send_fn, extract_fn, typing_fn=None):
    """Route one inbound channel message: link redemption, gating, or an OS1 turn."""
    link = await asyncio.to_thread(store.get_link, channel, channel_user_id)

    if not link:
        code = _extract_code(text)
        explicit = (text or "").strip().lower().startswith("/start")
        if code:
            ok, res = await asyncio.to_thread(
                store.redeem_link_code, code, channel, str(channel_user_id), username)
            if ok:
                await send_fn(channel_user_id, "✅ Linked! You're connected to Rue OS1. "
                                               "Just message me normally — text, photos, or files.")
            elif explicit:
                # They deliberately followed a link / typed /start <code>, so tell them it failed.
                await send_fn(channel_user_id, "That link code is invalid or expired. Generate a "
                                               "fresh one in the web app (Connections → Rue on "
                                               "Telegram) and send it here.")
            else:
                # A bare word that merely looked like a code — guide them to link instead.
                await send_fn(channel_user_id, LINK_PROMPT)
            return
        await send_fn(channel_user_id, LINK_PROMPT)
        return

    user_id = link["user_id"]
    sub = await asyncio.to_thread(billing_store.ensure_subscription, user_id)
    if not entitlements.has_access(sub):
        await send_fn(channel_user_id, INACTIVE_TEXT)
        return

    await asyncio.to_thread(store.touch_link, link["id"])

    stripped = (text or "").strip().lower()
    if stripped in ("/start", "/help"):
        await send_fn(channel_user_id, HELP_TEXT)
        return

    if typing_fn:
        await typing_fn(channel_user_id)
    attachments = await extract_fn(message) if message else []
    history = await asyncio.to_thread(store.recent_history, link["id"])
    result = await run_channel_turn(user_id, text, attachments, history)

    await asyncio.to_thread(store.add_message, link["id"], "user", text or "(media)")
    await asyncio.to_thread(store.add_message, link["id"], "assistant", result["reply"])
    await send_fn(channel_user_id, result["reply"])


async def _safe(coro):
    try:
        await coro
    except Exception as e:
        import traceback
        print(f"[CHANNELS] background handler error: {e}")
        traceback.print_exc()


# ── Telegram ────────────────────────────────────────────────────────────────────────────
@router.post("/channels/telegram/webhook")
async def telegram_webhook(request: Request):
    # Verify Telegram's secret header (if we configured one) before doing any work.
    secret = config.telegram_webhook_secret()
    if secret and request.headers.get("X-Telegram-Bot-Api-Secret-Token") != secret:
        return {"ok": False}
    if not config.telegram_enabled():
        return {"ok": True}
    try:
        update = await request.json()
    except Exception:
        return {"ok": True}

    parsed = telegram.parse_message(update)
    if not parsed or not parsed.get("chat_id"):
        return {"ok": True}

    # Process in the background so we ACK Telegram fast (no webhook retries / double-sends).
    asyncio.create_task(_safe(_handle_inbound(
        "telegram", parsed["chat_id"], parsed["username"], parsed["text"], parsed["message"],
        send_fn=telegram.send_message,
        extract_fn=telegram.extract_attachments,
        typing_fn=telegram.send_typing,
    )))
    return {"ok": True}


class SetWebhookRequest(BaseModel):
    user_id: str
    url: str


@router.post("/channels/telegram/set-webhook")
async def telegram_set_webhook(body: SetWebhookRequest):
    """One-time helper to register the Telegram webhook (admin only)."""
    if not is_admin(body.user_id):
        return {"ok": False, "error": "admin only"}
    if not config.telegram_enabled():
        return {"ok": False, "error": "TELEGRAM_BOT_TOKEN not set"}
    res = await telegram.set_webhook(body.url, config.telegram_webhook_secret())
    return {"ok": bool(res.get("ok")), "telegram": res}


# ── WhatsApp (phase 2) ──────────────────────────────────────────────────────────────────
@router.get("/channels/whatsapp/webhook")
async def whatsapp_verify(request: Request):
    """Meta webhook verification handshake."""
    params = request.query_params
    if (params.get("hub.mode") == "subscribe"
            and params.get("hub.verify_token") == config.whatsapp_verify_token()
            and config.whatsapp_verify_token()):
        return PlainTextResponse(params.get("hub.challenge", ""))
    return PlainTextResponse("forbidden", status_code=403)


@router.post("/channels/whatsapp/webhook")
async def whatsapp_webhook(request: Request):
    if not config.whatsapp_enabled():
        return {"ok": True}
    try:
        payload = await request.json()
    except Exception:
        return {"ok": True}
    for msg in whatsapp.parse_inbound(payload):
        if not msg.get("from"):
            continue
        asyncio.create_task(_safe(_handle_inbound(
            "whatsapp", msg["from"], msg["username"], msg["text"], msg["message"],
            send_fn=whatsapp.send_message,
            extract_fn=whatsapp.extract_attachments,
        )))
    return {"ok": True}
