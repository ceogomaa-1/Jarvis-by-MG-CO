# Adding a New Connector

Adding a connector takes **3 steps** and no changes outside the `connectors/` directory (except `registry.py`).

## Step 1 — Create `your_connector.py`

```python
from backend.lib.business.connectors.base import BaseConnector, ConnectorResult

class YourConnector(BaseConnector):
    CONNECTOR_TYPE = "your_type"          # lowercase, used as DB key
    DISPLAY_NAME = "Your Service"
    DESCRIPTION = "One-sentence description shown in the UI."
    DOCS_URL = "https://..."              # Link to where users get credentials

    REQUIRED_FIELDS = {
        "api_key": {
            "label": "API Key",
            "type": "password",
            "placeholder": "sk_...",
            "secret": True,
            "required": True,
        },
        # Add more fields as needed
    }

    async def test(self) -> ConnectorResult:
        missing = self._missing_fields()
        if missing:
            return ConnectorResult(ok=False, error=f"Missing: {', '.join(missing)}")
        try:
            # Make a lightweight read call to verify credentials
            ...
            return ConnectorResult(ok=True, data={"verified": True})
        except Exception as e:
            return ConnectorResult(ok=False, error=str(e))

    # Add action methods as needed:
    async def do_something(self, ...) -> ConnectorResult:
        ...
```

## Step 2 — Register in `registry.py`

```python
from backend.lib.business.connectors.your_connector import YourConnector

_CONNECTOR_REGISTRY: dict[str, type[BaseConnector]] = {
    ...
    YourConnector.CONNECTOR_TYPE: YourConnector,   # ← add this line
}
```

Also add a pretty name in `available_connectors_summary()`:

```python
pretty = {
    ...
    "your_type": "Your Service (description)",
}
```

## Step 3 — Done

The frontend Connections panel auto-discovers the new connector from the manifest endpoint. No frontend changes required.

## Field types

| `type` value | Rendered as |
|---|---|
| `text` | Plain text input |
| `password` | Masked password input (monospace) |
| `number` | Number input |

## ConnectorResult

All connector methods return `ConnectorResult(ok, data, error, meta)`.

- `ok=True` → success; put useful data in `data`
- `ok=False` → failure; put the error message in `error`

## Credential storage

Credentials are stored as a `jsonb` column in `business_connections`. Supabase encrypts at rest. RLS prevents cross-user access. The service role key is only used server-side.
