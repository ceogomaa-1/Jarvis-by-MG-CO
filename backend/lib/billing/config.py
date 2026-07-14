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


# Origin Stripe Checkout / Portal send the user back to. We append paths like '/os1?...', so
# this must be the bare origin. OS1_SITE_URL is sometimes set to '.../os1' — tolerate that by
# stripping a trailing '/os1' so success/cancel URLs don't double up ('/os1/os1?...').
def site_url() -> str:
    base = os.getenv("OS1_SITE_URL", "https://www.jarvismgco.com").rstrip("/")
    if base.endswith("/os1"):
        base = base[: -len("/os1")]
    return base or "https://www.jarvismgco.com"


# Rue Leads metered allowance (Emperor only). Lookups past this in a billing month are
# billed as overage. Trial users get ZERO leads regardless.
EMPEROR_LEADS_ALLOWANCE = int(os.getenv("OS1_EMPEROR_LEADS_ALLOWANCE", "500"))

# Legacy: a message-count "taste" during trial. Superseded by the hard COST ceiling below
# (a single large message could blow far past the intended spend), but kept for back-compat
# reads. Gating is now by TRIAL_COST_CAP_USD, not this count.
TRIAL_MESSAGE_ALLOWANCE = int(os.getenv("OS1_TRIAL_MESSAGE_ALLOWANCE", "25"))

# ── Trial cost ceiling (the real gate) ───────────────────────────────────────────────────
# A trial user's cumulative estimated API cost (cache-net) is tracked in os1_subscriptions.
# Once it reaches this cap the trial is blocked until they pick a plan. Defaults are tuned so
# the taste feels generous yet the worst-case spend is bounded:
#   - TRIAL_COST_CAP_USD     hard cumulative ceiling per trial identity
#   - TRIAL_MAX_TOKENS       per-response output cap so no single turn can blow the ceiling
#   - TRIAL_CONTEXT_CHAR_CAP per-turn input cap (a huge paste can't spike one turn)
# Trials are additionally pinned to the cheapest model tier (see model_router HAIKU) so the
# same budget buys many more turns.
TRIAL_COST_CAP_USD = float(os.getenv("OS1_TRIAL_COST_CAP_USD", "2.50"))
TRIAL_MAX_TOKENS = int(os.getenv("OS1_TRIAL_MAX_TOKENS", "1024"))
TRIAL_CONTEXT_CHAR_CAP = int(os.getenv("OS1_TRIAL_CONTEXT_CHAR_CAP", "12000"))

# Autonomous Operator capacity is intentionally finite: users buy sustained
# progress, while Rue's model/tool spend and blast radius remain bounded.
PRO_AUTONOMOUS_RUNS_MONTHLY = int(os.getenv("OS1_PRO_AUTONOMOUS_RUNS_MONTHLY", "2"))
EMPEROR_AUTONOMOUS_RUNS_MONTHLY = int(os.getenv("OS1_EMPEROR_AUTONOMOUS_RUNS_MONTHLY", "15"))
