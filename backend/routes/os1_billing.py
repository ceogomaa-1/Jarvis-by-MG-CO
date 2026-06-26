"""OS1 paywall API — subscription status, tiered Stripe checkout/portal, webhooks, gating,
and the Contact Us form. Additive; mounted under /api.

Flow it serves:
  switch (Personal) → jarvismgco.com/os1 → auth → GET /os1/status
    has_access (active OR grandfathered) → enter OS1
    else → pricing screen → POST /os1/checkout → Stripe → webhook flips active_subscription
"""
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from pydantic import BaseModel

from backend.lib.billing import config, store, entitlements, stripe_api, notify
from backend.lib.billing.disposable_domains import is_disposable, normalize_email

router = APIRouter()


def _iso(unix) -> str:
    if not unix:
        return None
    return datetime.fromtimestamp(int(unix), tz=timezone.utc).isoformat()


# ── status / entitlements ───────────────────────────────────────────────────────────────
@router.get("/os1/status")
async def os1_status(user_id: str, email: str = ""):
    """The auth-gate read. Ensures a row (absence = new user) and reports access + tier.

    has_access = active_subscription OR grandfathered. Grandfathered users never see pricing.
    """
    sub = store.ensure_subscription(user_id, email or None)
    caps = entitlements.capabilities(sub)
    cost = entitlements.trial_cost_status(user_id, sub)
    return {
        "has_access": caps["has_access"],
        "grandfathered": caps["grandfathered"],
        "plan": caps["plan"],
        "trialing": caps["trialing"],
        "status": sub.get("status"),
        "trial_ends_at": sub.get("trial_ends_at"),
        "current_period_end": sub.get("current_period_end"),
        "billing_enabled": config.billing_enabled(),
        # Trial budget (hard API-cost ceiling). For non-trial plans cap is null.
        "trial_cost_cap": cost["cap"],
        "trial_cost_used": cost["used"],
        "trial_cost_remaining": cost["remaining"],
    }


@router.get("/os1/entitlements")
async def os1_entitlements(user_id: str, email: str = ""):
    """Capability flags for UI + server gating (Leads, white-label, Buffer cap, UI custom)."""
    return entitlements.for_user(user_id, email or None)


class EmailCheck(BaseModel):
    email: str


@router.post("/os1/email-check")
async def os1_email_check(body: EmailCheck):
    """Block disposable/temp-email domains at signup."""
    return {"disposable": is_disposable(body.email)}


# ── checkout ────────────────────────────────────────────────────────────────────────────
class CheckoutRequest(BaseModel):
    user_id: str
    email: str
    plan: str           # 'pro' | 'emperor'
    interval: str = "month"   # 'month' | 'year'
    trial: bool = False
    ip: str = ""


@router.post("/os1/checkout")
async def os1_checkout(body: CheckoutRequest):
    if not config.billing_enabled():
        return {"ok": False, "error": "Billing is not configured yet."}
    if body.plan not in ("pro", "emperor") or body.interval not in ("month", "year"):
        return {"ok": False, "error": "Invalid plan or interval."}
    if is_disposable(body.email):
        return {"ok": False, "error": "Please use a permanent email address."}

    price = config.price_id(body.plan, body.interval)
    if not price:
        return {"ok": False, "error": f"No price configured for {body.plan}/{body.interval}."}

    sub = store.ensure_subscription(body.user_id, body.email)

    # ── trial anti-abuse: one trial per identity ──────────────────────────────────────────
    want_trial = bool(body.trial)
    if want_trial:
        norm = normalize_email(body.email)
        already = sub.get("trial_used") or store.trial_seen(email_normalized=norm, ip=body.ip or None)
        if already:
            # Already-trialed identity → no trial, straight to pay.
            want_trial = False

    base = config.site_url()
    success = f"{base}/os1?checkout=success&session_id={{CHECKOUT_SESSION_ID}}"
    cancel = f"{base}/os1?checkout=cancel"

    try:
        session = await stripe_api.create_checkout_session(
            price_id=price,
            user_id=body.user_id,
            email=body.email,
            customer_id=sub.get("stripe_customer_id"),
            trial=want_trial,
            success_url=success,
            cancel_url=cancel,
        )
    except Exception as e:
        return {"ok": False, "error": str(e)}

    return {"ok": True, "url": session.get("url"), "trial": want_trial}


# ── customer portal (manage / cancel) ────────────────────────────────────────────────────
class PortalRequest(BaseModel):
    user_id: str


@router.post("/os1/portal")
async def os1_portal(body: PortalRequest):
    if not config.billing_enabled():
        return {"ok": False, "error": "Billing is not configured yet."}
    sub = store.get_subscription(body.user_id)
    customer = sub.get("stripe_customer_id") if sub else None
    if not customer:
        return {"ok": False, "error": "No billing account yet."}
    try:
        session = await stripe_api.create_portal_session(
            customer_id=customer, return_url=f"{config.site_url()}/os1",
        )
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "url": session.get("url")}


# ── webhook ──────────────────────────────────────────────────────────────────────────────
def _card_fingerprint(sub_obj: dict) -> str:
    pm = sub_obj.get("default_payment_method")
    if isinstance(pm, dict):
        return (pm.get("card") or {}).get("fingerprint")
    return None


async def _apply_subscription(sub_obj: dict):
    """Map a Stripe subscription object onto our row and flip access flags."""
    user_id = (sub_obj.get("metadata") or {}).get("user_id")
    customer = sub_obj.get("customer")
    row = store.get_subscription(user_id) if user_id else None
    if not row and customer:
        row = store.get_by_customer(customer)
        user_id = row.get("user_id") if row else user_id
    if not user_id:
        print("[OS1 WEBHOOK] subscription with no user_id; skipping", sub_obj.get("id"))
        return

    status = sub_obj.get("status")
    price = (((sub_obj.get("items") or {}).get("data") or [{}])[0].get("price") or {}).get("id")
    plan, interval = config.plan_for_price(price)
    active = status in ("trialing", "active")

    fields = {
        "stripe_customer_id": customer,
        "stripe_subscription_id": sub_obj.get("id"),
        "status": status,
        "active_subscription": active,
        "plan": plan,
        "billing_interval": interval,
        "current_period_end": _iso(sub_obj.get("current_period_end")),
        "trial_ends_at": _iso(sub_obj.get("trial_end")),
    }
    # never downgrade grandfathered access via webhook
    store.upsert_subscription(user_id, {k: v for k, v in fields.items()})

    # one-trial-per-identity: record the card fingerprint when a trial is live, and mark used
    if status == "trialing":
        fp = _card_fingerprint(sub_obj)
        norm = normalize_email(row.get("email")) if row and row.get("email") else None
        store.record_trial_fingerprint(user_id, email_normalized=norm, card_fingerprint=fp)
        store.upsert_subscription(user_id, {"trial_used": True})


@router.post("/os1/webhook")
async def os1_webhook(request: Request):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    secret = config.stripe_webhook_secret()

    # If a webhook secret is configured, enforce it. STRIPE_WEBHOOK_SECRET may hold several
    # comma-separated secrets (e.g. a snapshot + a thin endpoint pointing at the same URL) —
    # the event is valid if it verifies against ANY of them. (In dev with none, accept + parse.)
    if secret:
        secrets = [s.strip() for s in secret.split(",") if s.strip()]
        if not any(stripe_api.verify_webhook(payload, sig, s) for s in secrets):
            return {"ok": False, "error": "bad signature"}

    try:
        event = json.loads(payload)
    except Exception:
        return {"ok": False, "error": "bad payload"}

    etype = event.get("type")
    obj = (event.get("data") or {}).get("object") or {}

    try:
        if etype == "checkout.session.completed":
            sub_id = obj.get("subscription")
            if sub_id:
                full = await stripe_api.retrieve_subscription(sub_id)
                # carry user_id from the session if the subscription metadata missed it
                if not (full.get("metadata") or {}).get("user_id"):
                    full.setdefault("metadata", {})["user_id"] = obj.get("client_reference_id")
                await _apply_subscription(full)

        elif etype in ("customer.subscription.created", "customer.subscription.updated"):
            # re-fetch to expand the payment method (for fingerprint) if a trial is involved
            if obj.get("status") == "trialing" and not isinstance(obj.get("default_payment_method"), dict):
                obj = await stripe_api.retrieve_subscription(obj.get("id"))
            await _apply_subscription(obj)

        elif etype == "customer.subscription.deleted":
            row = store.get_by_customer(obj.get("customer"))
            if row:
                store.upsert_subscription(row["user_id"], {
                    "active_subscription": False, "status": "canceled", "plan": None,
                })

        elif etype == "invoice.payment_failed":
            row = store.get_by_customer(obj.get("customer"))
            if row:
                store.upsert_subscription(row["user_id"], {
                    "active_subscription": False, "status": "past_due",
                })
    except Exception as e:
        print("[OS1 WEBHOOK] handler error:", etype, e)
        return {"ok": False, "error": str(e)}

    return {"ok": True}


# ── contact us ───────────────────────────────────────────────────────────────────────────
class ContactRequest(BaseModel):
    name: str
    email: str
    company: str = ""
    phone: str = ""
    message: str = ""


@router.post("/os1/contact")
async def os1_contact(body: ContactRequest):
    if not body.name.strip() or not body.email.strip():
        return {"ok": False, "error": "Name and email are required."}
    res = await notify.send_contact(
        name=body.name.strip(), email=body.email.strip(),
        company=body.company.strip(), phone=body.phone.strip(),
        message=body.message.strip(),
    )
    return res
