"""OS1 paywall configuration — all env-driven so nothing is hard-coded to one Stripe account.

Price IDs are produced by scripts/stripe_setup.py (creates the CAD products/prices and prints
the IDs to paste into Render env). Until they're set, checkout is disabled gracefully and the
rest of the app is untouched (same env-gated pattern as Leads / waitlist).
"""
import os

# Currency for all OS1 plans.
CURRENCY = "cad"

# 7-day trial, card required up front (Checkout in subscription+trial mode).
TRIAL_DAYS = int(os.getenv("OS1_TRIAL_DAYS", "7"))


def stripe_secret() -> str:
    return os.getenv("STRIPE_SECRET_KEY", "")


def stripe_webhook_secret() -> str:
    return os.getenv("STRIPE_WEBHOOK_SECRET", "")


def billing_enabled() -> bool:
    """Checkout/portal are live only once the platform Stripe key is configured."""
    return bool(stripe_secret())


# price_id lookup: plan ('pro'|'emperor') + interval ('month'|'year') → Stripe price id
def price_id(plan: str, interval: str) -> str:
    key = {
        ("pro", "month"): "STRIPE_PRICE_PRO_MONTHLY",
        ("pro", "year"): "STRIPE_PRICE_PRO_YEARLY",
        ("emperor", "month"): "STRIPE_PRICE_EMPEROR_MONTHLY",
        ("emperor", "year"): "STRIPE_PRICE_EMPEROR_YEARLY",
    }.get((plan, interval))
    return os.getenv(key, "") if key else ""


def plan_for_price(pid: str) -> tuple:
    """Reverse map a Stripe price id back to (plan, interval). Used by the webhook."""
    for plan in ("pro", "emperor"):
        for interval in ("month", "year"):
            if pid and price_id(plan, interval) == pid:
                return plan, interval
    return None, None


# Where Stripe Checkout / Portal send the user back. Defaults to prod OS1 site.
def site_url() -> str:
    return os.getenv("OS1_SITE_URL", "https://www.jarvismgco.com").rstrip("/")


# Jarvis Leads metered allowance (Emperor only). Lookups past this in a billing month are
# billed as overage. Trial users get ZERO leads regardless.
EMPEROR_LEADS_ALLOWANCE = int(os.getenv("OS1_EMPEROR_LEADS_ALLOWANCE", "500"))

# Tiny taste during trial — a very low message allowance so serial free accounts can't farm.
TRIAL_MESSAGE_ALLOWANCE = int(os.getenv("OS1_TRIAL_MESSAGE_ALLOWANCE", "25"))
