"""
Stripe financial data connector.

Reads: transactions, customers, revenue, balance.
Writes: products + prices (create_product / create_price / create_subscription_product)
— used to set up pricing tiers / subscription plans on Stripe. Writes are gated by
hold-to-confirm in the chat flow (WRITE_ACTIONS) before they ever run, and only
real Stripe-confirmed IDs are returned (never invented).
"""
import httpx

from backend.lib.business.connectors.base import BaseConnector, ConnectorResult


class StripeConnector(BaseConnector):
    CONNECTOR_TYPE = "stripe"
    DISPLAY_NAME = "Stripe"
    DESCRIPTION = "Read revenue and transactions, and create products / pricing tiers."
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

    def _mode(self) -> str:
        """'live' or 'test', inferred from the connected secret key prefix."""
        key = self.credentials.get("secret_key", "") or ""
        return "live" if key.startswith("sk_live_") else "test"

    @staticmethod
    def _flatten(prefix: str, mapping: dict | None) -> dict:
        """Flatten a dict into Stripe's bracketed form-encoding (metadata[key]=val)."""
        out: dict = {}
        for k, v in (mapping or {}).items():
            if v is not None:
                out[f"{prefix}[{k}]"] = str(v)
        return out

    @staticmethod
    def _stripe_error(resp) -> str:
        try:
            return resp.json().get("error", {}).get("message") or f"Stripe {resp.status_code}"
        except Exception:
            return f"Stripe {resp.status_code}: {resp.text[:200]}"

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
            if resp.status_code == 401:
                return ConnectorResult(ok=False, error="Invalid Stripe secret key — check your key in Stripe Dashboard → Developers → API keys.")
            if resp.status_code == 403:
                return ConnectorResult(ok=False, error="This key has restricted permissions and can't read balance. Use an unrestricted secret key, or add the 'Balance' read permission in Stripe Dashboard → Developers → API keys → Restrictions.")
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

    # ─── Writes: products + prices ──────────────────────────────────────────
    async def create_product(
        self,
        name: str,
        description: str | None = None,
        metadata: dict | None = None,
    ) -> ConnectorResult:
        """Create a Stripe Product. Returns the real prod_… id on a 2xx; never invents one."""
        if not name:
            return ConnectorResult(ok=False, error="Product name is required.")
        data = {"name": name}
        if description:
            data["description"] = description
        data.update(self._flatten("metadata", metadata))
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(f"{self.BASE}/products", auth=self._auth(), data=data, timeout=15.0)
            if resp.status_code != 200:
                return ConnectorResult(ok=False, error=self._stripe_error(resp))
            p = resp.json()
            return ConnectorResult(ok=True, data={
                "product_id": p.get("id"),
                "name": p.get("name"),
                "livemode": p.get("livemode"),
                "mode": self._mode(),
            })
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Create product exception: {e}")

    async def create_price(
        self,
        product_id: str,
        unit_amount: int,
        currency: str = "usd",
        interval: str | None = None,
        nickname: str | None = None,
        metadata: dict | None = None,
    ) -> ConnectorResult:
        """Create a Stripe Price for a product. `unit_amount` is in the minor unit
        (cents). Pass `interval` ('day'|'week'|'month'|'year') for a recurring
        subscription price; omit it for a one-time price. Returns the real price_… id."""
        if not product_id:
            return ConnectorResult(ok=False, error="product_id is required to create a price.")
        try:
            amount = int(unit_amount)
        except (TypeError, ValueError):
            return ConnectorResult(ok=False, error="unit_amount must be an integer number of cents.")
        if amount <= 0:
            return ConnectorResult(ok=False, error="unit_amount must be greater than 0 (in cents).")

        data: dict = {"product": product_id, "unit_amount": amount, "currency": (currency or "usd").lower()}
        if interval:
            data["recurring[interval]"] = interval
        if nickname:
            data["nickname"] = nickname
        data.update(self._flatten("metadata", metadata))
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(f"{self.BASE}/prices", auth=self._auth(), data=data, timeout=15.0)
            if resp.status_code != 200:
                return ConnectorResult(ok=False, error=self._stripe_error(resp))
            pr = resp.json()
            return ConnectorResult(ok=True, data={
                "price_id": pr.get("id"),
                "product_id": pr.get("product"),
                "unit_amount": pr.get("unit_amount"),
                "currency": pr.get("currency"),
                "interval": (pr.get("recurring") or {}).get("interval"),
                "livemode": pr.get("livemode"),
                "mode": self._mode(),
            })
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Create price exception: {e}")

    async def create_subscription_product(
        self,
        name: str,
        amount_cents: int,
        description: str | None = None,
        interval: str = "month",
        currency: str = "usd",
        metadata: dict | None = None,
    ) -> ConnectorResult:
        """Convenience: create a Product AND a recurring Price in one call — i.e. a
        full subscription pricing tier. Returns both real IDs (prod_…/price_…)."""
        prod = await self.create_product(name=name, description=description, metadata=metadata)
        if not prod.ok:
            return prod
        product_id = prod.data["product_id"]
        price = await self.create_price(
            product_id=product_id,
            unit_amount=amount_cents,
            currency=currency,
            interval=interval,
            nickname=name,
            metadata=metadata,
        )
        if not price.ok:
            # Product was created but the price failed — report honestly with the real
            # product id so nothing is silently orphaned or misrepresented as complete.
            return ConnectorResult(
                ok=False,
                error=f"Created product {product_id} but the price failed: {price.error}",
                data={"product_id": product_id, "mode": self._mode()},
            )
        return ConnectorResult(ok=True, data={
            "product_id": product_id,
            "price_id": price.data["price_id"],
            "name": name,
            "amount_cents": int(amount_cents),
            "currency": (currency or "usd").lower(),
            "interval": interval,
            "mode": self._mode(),
        })
