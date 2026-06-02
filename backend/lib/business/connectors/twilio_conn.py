"""
Twilio SMS connector. Uses Twilio's REST API directly via httpx — no SDK needed.
"""
import httpx

from backend.lib.business.connectors.base import BaseConnector, ConnectorResult


class TwilioConnector(BaseConnector):
    CONNECTOR_TYPE = "twilio"
    DISPLAY_NAME = "Twilio SMS"
    DESCRIPTION = "Send SMS to your customers via your Twilio account."
    DOCS_URL = "https://console.twilio.com/"
    REQUIRED_FIELDS = {
        "account_sid": {
            "label": "Account SID",
            "type": "text",
            "placeholder": "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            "secret": False,
            "required": True,
        },
        "auth_token": {
            "label": "Auth Token",
            "type": "password",
            "placeholder": "Your Twilio Auth Token",
            "secret": True,
            "required": True,
        },
        "from_number": {
            "label": "From Number (E.164 format)",
            "type": "text",
            "placeholder": "+14165550199",
            "secret": False,
            "required": True,
        },
    }

    async def test(self) -> ConnectorResult:
        missing = self._missing_fields()
        if missing:
            return ConnectorResult(ok=False, error=f"Missing required fields: {', '.join(missing)}")

        sid = self.credentials["account_sid"]
        token = self.credentials["auth_token"]

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"https://api.twilio.com/2010-04-01/Accounts/{sid}.json",
                    auth=(sid, token),
                    timeout=10.0,
                )
            if resp.status_code == 200:
                friendly = resp.json().get("friendly_name", "")
                return ConnectorResult(ok=True, data={"account_friendly_name": friendly})
            if resp.status_code in (401, 403):
                return ConnectorResult(ok=False, error="Invalid Account SID or Auth Token")
            return ConnectorResult(ok=False, error=f"Twilio returned {resp.status_code}")
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Twilio connection failed: {e}")

    async def send_sms(self, to: str, body: str) -> ConnectorResult:
        """Send an SMS. `to` must be E.164 (+14165550199)."""
        missing = self._missing_fields()
        if missing:
            return ConnectorResult(ok=False, error=f"Missing: {', '.join(missing)}")
        if not to or not body:
            return ConnectorResult(ok=False, error="`to` and `body` required")

        sid = self.credentials["account_sid"]
        token = self.credentials["auth_token"]
        from_number = self.credentials["from_number"]

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
                    auth=(sid, token),
                    data={"To": to, "From": from_number, "Body": body},
                    timeout=15.0,
                )
            if resp.status_code in (200, 201):
                msg = resp.json()
                return ConnectorResult(
                    ok=True,
                    data={"sid": msg.get("sid"), "status": msg.get("status")},
                )
            return ConnectorResult(
                ok=False,
                error=f"Twilio send failed {resp.status_code}: {resp.text[:200]}",
            )
        except Exception as e:
            return ConnectorResult(ok=False, error=f"SMS send exception: {e}")
