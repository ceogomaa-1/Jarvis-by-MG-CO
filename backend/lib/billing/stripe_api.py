"""Platform-side Stripe REST wrapper (httpx, no SDK) for OS1 subscription billing.

Uses the PLATFORM secret key (STRIPE_SECRET_KEY) — distinct from the per-user Stripe
connector. Mirrors that connector's style: Basic auth (secret, ""), form-encoded body with
Stripe's bracket notation, async httpx. Includes manual webhook signature verification so we
don't add the stripe python dependency.
"""
import hashlib
import hmac
import time

import httpx

from . import config

BASE = "https://api.stripe.com/v1"


def _auth():
    return (config.stripe_secret(), "")


async def _post(path: str, data: dict) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{BASE}{path}", auth=_auth(), data=data, timeout=20.0)
    payload = resp.json()
    if resp.status_code >= 400:
        msg = payload.get("error", {}).get("message", f"Stripe {resp.status_code}")
        raise RuntimeError(msg)
    return payload


async def _get(path: str, params: dict = None) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{BASE}{path}", auth=_auth(), params=params or {}, timeout=20.0)
    payload = resp.json()
    if resp.status_code >= 400:
        msg = payload.get("error", {}).get("message", f"Stripe {resp.status_code}")
        raise RuntimeError(msg)
    return payload


async def create_checkout_session(*, price_id: str, user_id: str, email: str,
                                  customer_id: str = None, trial: bool = False,
                                  success_url: str, cancel_url: str) -> dict:
    """Create a subscription Checkout Session.

    Trial mode captures a valid card BEFORE the trial starts (payment_method_collection=always)
    and auto-converts at day-7 unless canceled. We always collect a card so we can read the
    card fingerprint in the webhook for one-trial-per-identity enforcement.
    """
    data = {
        "mode": "subscription",
        "line_items[0][price]": price_id,
        "line_items[0][quantity]": "1",
        "client_reference_id": user_id,
        "success_url": success_url,
        "cancel_url": cancel_url,
        "payment_method_collection": "always",
        "allow_promotion_codes": "true",
        "subscription_data[metadata][user_id]": user_id,
        "metadata[user_id]": user_id,
    }
    if customer_id:
        data["customer"] = customer_id
    else:
        data["customer_email"] = email
    if trial:
        data["subscription_data[trial_period_days]"] = str(config.TRIAL_DAYS)
        # If they cancel during trial and never pay, cancel the sub (no surprise charge edge).
        data["subscription_data[trial_settings][end_behavior][missing_payment_method]"] = "cancel"
    return await _post("/checkout/sessions", data)


async def create_portal_session(*, customer_id: str, return_url: str) -> dict:
    return await _post("/billing_portal/sessions", {
        "customer": customer_id,
        "return_url": return_url,
    })


async def retrieve_subscription(sub_id: str) -> dict:
    # expand the default payment method so we can read the card fingerprint for anti-abuse
    return await _get(f"/subscriptions/{sub_id}",
                      {"expand[]": "default_payment_method"})


def verify_webhook(payload: bytes, sig_header: str, secret: str, tolerance: int = 300) -> bool:
    """Verify a Stripe webhook signature (HMAC-SHA256 over 't.payload'), no SDK needed."""
    if not sig_header or not secret:
        return False
    try:
        parts = dict(p.split("=", 1) for p in sig_header.split(",") if "=" in p)
        ts = parts.get("t")
        v1 = parts.get("v1")
        if not ts or not v1:
            return False
        signed = f"{ts}.{payload.decode('utf-8')}".encode("utf-8")
        expected = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, v1):
            return False
        # replay protection
        if tolerance and abs(time.time() - int(ts)) > tolerance:
            return False
        return True
    except Exception:
        return False
