#!/usr/bin/env python3
"""One-time Stripe setup for the Jarvis OS1 paywall (CAD).

Creates two products (Jarvis OS1 Pro, Jarvis OS1 Emperor) and four recurring CAD prices:
  Pro     — $49/mo   and  $490/yr  (2 months free)
  Emperor — $199/mo  and  $1,990/yr (2 months free)

Then prints the env vars to paste into Render. Idempotent-ish: it searches for existing
products by name and reuses them, but always creates fresh prices (Stripe prices are
immutable) — so run it once. Uses the same httpx + Basic-auth style as the rest of the app;
no stripe SDK required.

Usage (PowerShell):
  $env:STRIPE_SECRET_KEY = "sk_live_or_test_..."
  python scripts/stripe_setup.py
"""
import os
import sys

import httpx

BASE = "https://api.stripe.com/v1"
CURRENCY = "cad"

PLANS = [
    {"key": "PRO", "name": "Jarvis OS1 Pro",
     "desc": "Jarvis chat, autonomous sessions, 9 industry bibles, MCP Creation 1.0, basic CRM.",
     "monthly": 4900, "yearly": 49000},
    {"key": "EMPEROR", "name": "Jarvis OS1 Emperor",
     "desc": "Everything in Pro + 5x usage, unlimited Buffer, white-label CRM, Jarvis Leads, custom UI.",
     "monthly": 19900, "yearly": 199000},
]


def _auth():
    key = os.getenv("STRIPE_SECRET_KEY", "")
    if not key:
        print("ERROR: set STRIPE_SECRET_KEY first.", file=sys.stderr)
        sys.exit(1)
    return (key, "")


def _find_product(client, name):
    r = client.get(f"{BASE}/products/search", auth=_auth(),
                   params={"query": f"name:'{name}'"}, timeout=20)
    r.raise_for_status()
    data = r.json().get("data", [])
    return data[0]["id"] if data else None


def _create_product(client, name, desc):
    r = client.post(f"{BASE}/products", auth=_auth(),
                    data={"name": name, "description": desc}, timeout=20)
    r.raise_for_status()
    return r.json()["id"]


def _create_price(client, product, amount, interval):
    r = client.post(f"{BASE}/prices", auth=_auth(), data={
        "product": product,
        "currency": CURRENCY,
        "unit_amount": str(amount),
        "recurring[interval]": interval,
    }, timeout=20)
    r.raise_for_status()
    return r.json()["id"]


def main():
    env_out = []
    with httpx.Client() as client:
        for plan in PLANS:
            pid = _find_product(client, plan["name"]) or _create_product(client, plan["name"], plan["desc"])
            print(f"product {plan['name']}: {pid}")
            monthly = _create_price(client, pid, plan["monthly"], "month")
            yearly = _create_price(client, pid, plan["yearly"], "year")
            env_out.append(f"STRIPE_PRICE_{plan['key']}_MONTHLY={monthly}")
            env_out.append(f"STRIPE_PRICE_{plan['key']}_YEARLY={yearly}")

    print("\n=== Paste these into Render (backend) env ===")
    print("\n".join(env_out))
    print("\nAlso set: STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET (from the webhook endpoint),")
    print("OS1_SITE_URL=https://www.jarvismgco.com, RESEND_API_KEY (optional, for Contact form).")


if __name__ == "__main__":
    main()
