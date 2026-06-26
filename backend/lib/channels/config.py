"""Channel configuration — all env-driven, same gated pattern as Leads / OS1 billing.

Telegram is the shipped channel; WhatsApp is phase 2 and stays OFF unless explicitly enabled.
Nothing here is active until the relevant credentials are set, so the feature is inert on any
deployment that hasn't configured it.
"""
import os

# Where we tell unlinked users to go, and the base for deep links.
SITE_URL = os.getenv("OS1_SITE_URL", "https://www.jarvismgco.com").rstrip("/")

# How long a one-time link code is valid, and how many recent channel turns to load as context.
LINK_CODE_TTL_MINUTES = int(os.getenv("CHANNELS_LINK_CODE_TTL_MIN", "15"))
HISTORY_TURNS = int(os.getenv("CHANNELS_HISTORY_TURNS", "10"))


# ── Telegram ─────────────────────────────────────────────────────────────────────────────
def telegram_bot_token() -> str:
    return os.getenv("TELEGRAM_BOT_TOKEN", "")


def telegram_bot_username() -> str:
    """Bot @username (without @) — used to build t.me deep links in the web app."""
    return os.getenv("TELEGRAM_BOT_USERNAME", "").lstrip("@")


def telegram_webhook_secret() -> str:
    """Shared secret echoed by Telegram in the X-Telegram-Bot-Api-Secret-Token header."""
    return os.getenv("TELEGRAM_WEBHOOK_SECRET", "")


def telegram_enabled() -> bool:
    return bool(telegram_bot_token())


# ── WhatsApp (phase 2, behind a flag) ────────────────────────────────────────────────────
def whatsapp_enabled() -> bool:
    return os.getenv("CHANNELS_WHATSAPP_ENABLED", "0") == "1" and bool(whatsapp_token())


def whatsapp_token() -> str:
    return os.getenv("WHATSAPP_ACCESS_TOKEN", "")


def whatsapp_phone_number_id() -> str:
    return os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")


def whatsapp_verify_token() -> str:
    return os.getenv("WHATSAPP_VERIFY_TOKEN", "")


def channel_enabled(channel: str) -> bool:
    return {"telegram": telegram_enabled(), "whatsapp": whatsapp_enabled()}.get(channel, False)
