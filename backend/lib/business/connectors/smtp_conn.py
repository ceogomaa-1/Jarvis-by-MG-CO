"""
Universal SMTP email connector. Works with any provider — Gmail (via App Password),
Outlook, Yahoo, custom SMTP. Uses Python's stdlib smtplib + email.message.
"""
import asyncio
import smtplib
from email.message import EmailMessage

from backend.lib.business.connectors.base import BaseConnector, ConnectorResult


class SMTPConnector(BaseConnector):
    CONNECTOR_TYPE = "smtp"
    DISPLAY_NAME = "Email (SMTP)"
    DESCRIPTION = "Send email from your existing provider (Gmail, Outlook, custom server)."
    DOCS_URL = "https://support.google.com/accounts/answer/185833"
    REQUIRED_FIELDS = {
        "host": {
            "label": "SMTP Host",
            "type": "text",
            "placeholder": "smtp.gmail.com",
            "secret": False,
            "required": True,
        },
        "port": {
            "label": "Port",
            "type": "number",
            "placeholder": "587",
            "secret": False,
            "required": True,
        },
        "username": {
            "label": "Username / Email",
            "type": "text",
            "placeholder": "you@example.com",
            "secret": False,
            "required": True,
        },
        "password": {
            "label": "Password / App Password",
            "type": "password",
            "placeholder": "Use an App Password (not your regular password)",
            "secret": True,
            "required": True,
        },
        "from_email": {
            "label": "From Email",
            "type": "text",
            "placeholder": "you@example.com",
            "secret": False,
            "required": True,
        },
        "from_name": {
            "label": "From Name (optional)",
            "type": "text",
            "placeholder": "Your Business Name",
            "secret": False,
            "required": False,
        },
    }

    def _port(self) -> int:
        try:
            return int(self.credentials.get("port", 587))
        except (ValueError, TypeError):
            return 587

    def _connect_sync(self) -> smtplib.SMTP:
        """Returns an authenticated SMTP connection. Caller must close it."""
        host = self.credentials["host"]
        port = self._port()
        username = self.credentials["username"]
        password = self.credentials["password"]

        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=15)
        else:
            server = smtplib.SMTP(host, port, timeout=15)
            server.ehlo()
            server.starttls()
            server.ehlo()
        server.login(username, password)
        return server

    async def test(self) -> ConnectorResult:
        missing = self._missing_fields()
        if missing:
            return ConnectorResult(ok=False, error=f"Missing required fields: {', '.join(missing)}")

        def _test_blocking() -> ConnectorResult:
            try:
                server = self._connect_sync()
                server.quit()
                return ConnectorResult(ok=True, data={"host": self.credentials["host"]})
            except smtplib.SMTPAuthenticationError:
                return ConnectorResult(
                    ok=False,
                    error="Authentication failed — for Gmail/Outlook, you must use an App Password, not your regular password.",
                )
            except smtplib.SMTPException as e:
                return ConnectorResult(ok=False, error=f"SMTP error: {e}")
            except (TimeoutError, OSError) as e:
                return ConnectorResult(ok=False, error=f"Connection failed: {e}")
            except Exception as e:
                return ConnectorResult(ok=False, error=f"Unexpected error: {e}")

        return await asyncio.to_thread(_test_blocking)

    async def send_email(
        self,
        to: str | list[str],
        subject: str,
        body_text: str,
        body_html: str | None = None,
    ) -> ConnectorResult:
        """Send an email. `to` can be a single address or a list."""
        missing = self._missing_fields()
        if missing:
            return ConnectorResult(ok=False, error=f"Missing: {', '.join(missing)}")

        to_list = [to] if isinstance(to, str) else list(to)
        if not to_list:
            return ConnectorResult(ok=False, error="`to` is empty")

        from_email = self.credentials["from_email"]
        from_name = self.credentials.get("from_name", "").strip()
        from_header = f"{from_name} <{from_email}>" if from_name else from_email

        msg = EmailMessage()
        msg["Subject"] = subject or "(no subject)"
        msg["From"] = from_header
        msg["To"] = ", ".join(to_list)
        msg.set_content(body_text or "")
        if body_html:
            msg.add_alternative(body_html, subtype="html")

        def _send_blocking() -> ConnectorResult:
            try:
                server = self._connect_sync()
                server.send_message(msg, from_addr=from_email, to_addrs=to_list)
                server.quit()
                return ConnectorResult(ok=True, data={"sent_to": to_list})
            except smtplib.SMTPAuthenticationError:
                return ConnectorResult(ok=False, error="SMTP auth failed — check App Password.")
            except smtplib.SMTPException as e:
                return ConnectorResult(ok=False, error=f"SMTP send error: {e}")
            except Exception as e:
                return ConnectorResult(ok=False, error=f"Send exception: {e}")

        return await asyncio.to_thread(_send_blocking)
