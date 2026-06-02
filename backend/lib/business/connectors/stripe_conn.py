"""
Stripe financial data connector. Read-only for v1 — we read transactions,
customers, revenue, balance. Write operations (creating invoices, refunds)
deferred to Batch 21.
"""
import httpx

from backend.lib.business.connectors.base import BaseConnector, ConnectorResult


class StripeConnector(BaseConnector):
    CONNECTOR_TYPE = "stripe"
    DISPLAY_NAME = "Stripe"
    DESCRIPTION = "Read your real-time revenue, customers, and transactions."
    DOCS_URL = "https://dashboard.stripe.com/apikeys"
    REQUIRED_FIELDS = {
        "secret_key": {
            "label": "Secret Key (sk_live_… or sk_test_…)",
            "type": "password",
            "placeholder": "Your Stripe secret key (starts with sk_live_ or sk_test_)",
            "secret": True,
            "required": True,
        },
    }

    BASE = "https://api.stripe.com/v1"

    def _auth(self) -> tuple[str, str]:
        return (self.credentials["secret_key"], "")

    async def test(self) -> ConnectorResult:
        missing = self._missing_fields()
        if missing:
            return ConnectorResult(ok=False, error=f"Missing required fields: {', '.join(missing)}")

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.BASE}/balance",
                    auth=self._auth(),
                    timeout=10.0,
                )
            if resp.status_code == 200:
                data = resp.json()
                avail = data.get("available", [{}])
                first = avail[0] if avail else {}
                return ConnectorResult(
                    ok=True,
                    data={
                        "currency": first.get("currency", "usd"),
                        "available_minor": first.get("amount", 0),
                    },
                )
            if resp.status_code in (401, 403):
                return ConnectorResult(ok=False, error="Invalid Stripe secret key")
            return ConnectorResult(ok=False, error=f"Stripe returned {resp.status_code}")
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Stripe connection failed: {e}")

    async def list_recent_charges(self, limit: int = 10) -> ConnectorResult:
        """Return the most recent charges (used by Operator Agent for revenue analysis)."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.BASE}/charges",
                    auth=self._auth(),
                    params={"limit": min(max(limit, 1), 100)},
                    timeout=15.0,
                )
            if resp.status_code != 200:
                return ConnectorResult(ok=False, error=f"Stripe {resp.status_code}: {resp.text[:200]}")
            payload = resp.json()
            charges = [
                {
                    "id": c.get("id"),
                    "amount_minor": c.get("amount"),
                    "currency": c.get("currency"),
                    "status": c.get("status"),
                    "paid": c.get("paid"),
                    "customer": c.get("customer"),
                    "description": c.get("description"),
                    "created": c.get("created"),
                }
                for c in payload.get("data", [])
            ]
            return ConnectorResult(ok=True, data={"charges": charges})
        except Exception as e:
            return ConnectorResult(ok=False, error=f"List charges exception: {e}")

    async def revenue_summary_last_30_days(self) -> ConnectorResult:
        """
        Quick revenue summary: gross volume for the last 30 days.
        Paginates /charges with a created.gte filter (up to 500 charges).
        """
        import time
        thirty_days_ago = int(time.time()) - (30 * 86400)
        total_minor = 0
        count = 0
        currency = "usd"

        try:
            async with httpx.AsyncClient() as client:
                starting_after = None
                for _ in range(5):
                    params = {
                        "limit": 100,
                        "created[gte]": thirty_days_ago,
                    }
                    if starting_after:
                        params["starting_after"] = starting_after
                    resp = await client.get(
                        f"{self.BASE}/charges",
                        auth=self._auth(),
                        params=params,
                        timeout=20.0,
                    )
                    if resp.status_code != 200:
                        return ConnectorResult(ok=False, error=f"Stripe {resp.status_code}")
                    payload = resp.json()
                    rows = payload.get("data", [])
                    for c in rows:
                        if c.get("paid") and c.get("status") == "succeeded":
                            total_minor += c.get("amount", 0)
                            count += 1
                            currency = c.get("currency", currency)
                    if not payload.get("has_more"):
                        break
                    if rows:
                        starting_after = rows[-1].get("id")

            return ConnectorResult(
                ok=True,
                data={
                    "total_minor": total_minor,
                    "total_major": total_minor / 100.0,
                    "currency": currency,
                    "charge_count": count,
                    "window_days": 30,
                },
            )
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Revenue summary exception: {e}")
