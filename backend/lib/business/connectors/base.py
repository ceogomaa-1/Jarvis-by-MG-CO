"""
Base connector class. Every concrete connector (Twilio, Stripe, SMTP, etc.)
inherits from BaseConnector and implements:

  - REQUIRED_FIELDS: dict of field_name -> {label, type, placeholder, required}
  - test(credentials) -> ConnectorResult: validate credentials work
  - Optional methods specific to the connector (send_sms, send_email, etc.)
"""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConnectorResult:
    """Standard result type from any connector action."""
    ok: bool
    data: Any = None
    error: str | None = None
    meta: dict = field(default_factory=dict)


class BaseConnector:
    """Subclass for each connector type."""

    # Override in subclass
    CONNECTOR_TYPE: str = ""             # e.g. "twilio"
    DISPLAY_NAME: str = ""               # e.g. "Twilio SMS"
    DESCRIPTION: str = ""                # Short user-facing description
    DOCS_URL: str = ""                   # Where users go to get credentials
    REQUIRED_FIELDS: dict = {}           # {field_name: {label, type, placeholder, secret}}
    AUTH_TYPE: str = "api_key"           # "api_key" or "oauth"
    STATUS_NOTE: str = ""                # Optional note shown in UI (e.g. "requires partner approval")

    def __init__(self, credentials: dict):
        self.credentials = credentials or {}

    # ─── Subclasses MUST implement test() ───────────────────
    async def test(self) -> ConnectorResult:
        """Validate that the credentials actually work. Returns ConnectorResult."""
        raise NotImplementedError(f"{self.__class__.__name__}.test() not implemented")

    # ─── Helpers ────────────────────────────────────────────
    @classmethod
    def manifest(cls) -> dict:
        """Frontend-friendly manifest describing this connector."""
        return {
            "type": cls.CONNECTOR_TYPE,
            "display_name": cls.DISPLAY_NAME,
            "description": cls.DESCRIPTION,
            "docs_url": cls.DOCS_URL,
            "auth_type": cls.AUTH_TYPE,
            "status_note": cls.STATUS_NOTE,
            "fields": [
                {"name": name, **meta}
                for name, meta in cls.REQUIRED_FIELDS.items()
            ],
        }

    def _missing_fields(self) -> list[str]:
        """Return list of REQUIRED_FIELDS not present in credentials."""
        missing = []
        for name, meta in self.REQUIRED_FIELDS.items():
            if meta.get("required", True) and not self.credentials.get(name):
                missing.append(name)
        return missing
