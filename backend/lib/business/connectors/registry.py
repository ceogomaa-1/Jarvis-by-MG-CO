"""
Connector registry + per-user lookup.

Frontend uses `list_available_connectors()` to render the Connections panel.
Sub-agents use `get_connector_for_user(user_id, type)` to act on the user's behalf.
"""
import os

import httpx

from backend.lib.business.connectors.base import BaseConnector, ConnectorResult
from backend.lib.business.connectors.twilio_conn import TwilioConnector
from backend.lib.business.connectors.stripe_conn import StripeConnector
from backend.lib.business.connectors.smtp_conn import SMTPConnector
from backend.lib.business.connectors.elevenlabs_conn import ElevenLabsConnector
from backend.lib.business.connectors.notion_conn import NotionConnector
from backend.lib.business.connectors.google_conn import GoogleConnector
from backend.lib.business.connectors.canva_conn import CanvaConnector
from backend.lib.business.connectors.gohighlevel_conn import GoHighLevelConnector
from backend.lib.business.connectors.github_connector import GitHubConnector
from backend.lib.business.connectors.vercel_connector import VercelConnector
from backend.lib.business.connectors.supabase_project_connector import SupabaseProjectConnector
from backend.lib.business.connectors.metricool_conn import MetricoolConnector


SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")


def _user_id_to_uuid(user_id: str) -> str:
    """Strip 'user_' prefix and reformat 32-char hex as a proper UUID."""
    hex_id = user_id.removeprefix("user_")
    if len(hex_id) == 32 and all(c in "0123456789abcdef" for c in hex_id.lower()):
        return f"{hex_id[:8]}-{hex_id[8:12]}-{hex_id[12:16]}-{hex_id[16:20]}-{hex_id[20:]}"
    return user_id


# Add new connector classes here — that's the only registration step needed.
_CONNECTOR_REGISTRY: dict[str, type[BaseConnector]] = {
    TwilioConnector.CONNECTOR_TYPE: TwilioConnector,
    StripeConnector.CONNECTOR_TYPE: StripeConnector,
    SMTPConnector.CONNECTOR_TYPE: SMTPConnector,
    ElevenLabsConnector.CONNECTOR_TYPE: ElevenLabsConnector,
    NotionConnector.CONNECTOR_TYPE: NotionConnector,
    GoogleConnector.CONNECTOR_TYPE: GoogleConnector,
    CanvaConnector.CONNECTOR_TYPE: CanvaConnector,
    GoHighLevelConnector.CONNECTOR_TYPE: GoHighLevelConnector,
    GitHubConnector.CONNECTOR_TYPE: GitHubConnector,
    VercelConnector.CONNECTOR_TYPE: VercelConnector,
    SupabaseProjectConnector.CONNECTOR_TYPE: SupabaseProjectConnector,
    MetricoolConnector.CONNECTOR_TYPE: MetricoolConnector,
}


def list_available_connectors() -> list[dict]:
    """Return the manifest for every registered connector — used by frontend."""
    return [cls.manifest() for cls in _CONNECTOR_REGISTRY.values()]


def connector_class(connector_type: str) -> type[BaseConnector] | None:
    """Get the connector class for a type string, or None."""
    return _CONNECTOR_REGISTRY.get(connector_type)


async def _fetch_user_connection_row(user_id: str, connector_type: str) -> dict | None:
    """Fetch the raw business_connections row for a user + type. None if missing."""
    user_id = _user_id_to_uuid(user_id)
    if not user_id or not connector_type or not SUPABASE_URL or not SUPABASE_KEY:
        return None
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/business_connections",
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                },
                params={
                    "select": "id,connector_type,credentials,status,display_name,last_tested_at,last_test_result",
                    "user_id": f"eq.{user_id}",
                    "connector_type": f"eq.{connector_type}",
                    "limit": "1",
                },
                timeout=10.0,
            )
        if resp.status_code == 200:
            rows = resp.json()
            return rows[0] if rows else None
    except Exception as e:
        print(f"REGISTRY: fetch failed: {e}")
    return None


async def list_user_connections(user_id: str) -> list[dict]:
    """List all connections for a user — used by Connections page."""
    user_id = _user_id_to_uuid(user_id)
    if not user_id or not SUPABASE_URL or not SUPABASE_KEY:
        return []
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/business_connections",
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                },
                params={
                    "select": "id,connector_type,display_name,status,last_tested_at,last_test_result,created_at",
                    "user_id": f"eq.{user_id}",
                    "order": "created_at.desc",
                },
                timeout=10.0,
            )
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print(f"REGISTRY: list_user_connections failed: {e}")
    return []


async def get_connector_for_user(user_id: str, connector_type: str) -> BaseConnector | None:
    """
    Returns an authenticated BaseConnector instance for the user, or None if
    the user hasn't connected this type (or it's disabled / invalid).
    """
    row = await _fetch_user_connection_row(user_id, connector_type)
    if not row or row.get("status") != "active":
        return None

    cls = connector_class(connector_type)
    if not cls:
        return None

    creds = row.get("credentials") or {}
    return cls(credentials=creds)


async def upsert_user_connection(
    user_id: str,
    connector_type: str,
    credentials: dict,
    display_name: str = "",
) -> dict | None:
    """Insert or update a user connection. Returns the row, or None on failure."""
    user_id = _user_id_to_uuid(user_id)
    if not user_id or not connector_type or not SUPABASE_URL or not SUPABASE_KEY:
        return None
    payload = {
        "user_id": user_id,
        "connector_type": connector_type,
        "credentials": credentials,
        "display_name": display_name or connector_type,
        "status": "active",
        "updated_at": "now()",
    }
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{SUPABASE_URL}/rest/v1/business_connections",
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                    "Content-Type": "application/json",
                    "Prefer": "resolution=merge-duplicates,return=representation",
                },
                json=payload,
                timeout=10.0,
            )
        if resp.status_code in (200, 201):
            data = resp.json()
            return data[0] if isinstance(data, list) and data else data
        print(f"REGISTRY: upsert failed {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"REGISTRY: upsert exception: {e}")
    return None


async def delete_user_connection(user_id: str, connector_type: str) -> bool:
    user_id = _user_id_to_uuid(user_id)
    if not user_id or not connector_type or not SUPABASE_URL or not SUPABASE_KEY:
        return False
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.delete(
                f"{SUPABASE_URL}/rest/v1/business_connections"
                f"?user_id=eq.{user_id}&connector_type=eq.{connector_type}",
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                    "Prefer": "return=minimal",
                },
                timeout=10.0,
            )
        return resp.status_code in (200, 204)
    except Exception as e:
        print(f"REGISTRY: delete exception: {e}")
        return False


async def update_test_result(
    user_id: str,
    connector_type: str,
    result: ConnectorResult,
) -> None:
    """Record a test result against a connection row."""
    user_id = _user_id_to_uuid(user_id)
    if not user_id or not connector_type or not SUPABASE_URL or not SUPABASE_KEY:
        return
    payload = {
        "last_tested_at": "now()",
        "last_test_result": "ok" if result.ok else f"failed: {result.error or 'unknown'}"[:300],
        "status": "active" if result.ok else "invalid",
    }
    try:
        async with httpx.AsyncClient() as client:
            await client.patch(
                f"{SUPABASE_URL}/rest/v1/business_connections"
                f"?user_id=eq.{user_id}&connector_type=eq.{connector_type}",
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal",
                },
                json=payload,
                timeout=10.0,
            )
    except Exception as e:
        print(f"REGISTRY: update_test_result exception: {e}")


_CONNECTOR_ACTIONS: dict[str, list[str]] = {
    "twilio": ["send_sms"],
    "stripe": ["list_recent_charges", "revenue_summary_last_30_days"],
    "smtp": ["send_email"],
    "elevenlabs": ["list_voices", "text_to_speech", "list_agents", "get_agent", "create_agent", "update_agent", "delete_agent"],
    "notion": ["search", "read_page", "query_database", "create_page", "list_pages", "create_database"],
    "google": ["list_calendar_events", "create_calendar_event", "list_emails", "send_email"],
    "canva": ["list_designs", "create_design"],
    "gohighlevel": ["list_contacts", "search_contacts", "create_contact", "list_pipelines", "list_opportunities", "list_appointments"],
    "github": ["list_repos", "create_repo", "push_files"],
    "vercel": ["list_projects", "create_project", "trigger_deploy", "get_deployment"],
    "supabase_project": ["list_projects", "get_project_keys", "run_sql"],
    "metricool": [
        "list_brands", "get_profile", "get_recent_posts", "get_scheduled_posts",
        "get_available_metrics", "get_metrics", "get_best_time_to_post",
        "schedule_post", "update_scheduled_post",
    ],
}

_CONNECTOR_LABELS: dict[str, str] = {
    "twilio": "Twilio (SMS)",
    "stripe": "Stripe (financial data)",
    "smtp": "Email via SMTP",
    "elevenlabs": "ElevenLabs (AI voice)",
    "notion": "Notion (workspace)",
    "google": "Google Calendar + Gmail",
    "canva": "Canva (design)",
    "gohighlevel": "GoHighLevel (CRM)",
    "github": "GitHub (code repos)",
    "vercel": "Vercel (deployments)",
    "supabase_project": "Supabase (user projects)",
    "metricool": "Metricool (social media agency)",
}


async def available_connectors_summary(user_id: str) -> str:
    """
    Returns a human-readable list of connected tools with their available actions.
    Injected into the system prompt so Jarvis knows what it can execute.
    """
    user_id = _user_id_to_uuid(user_id)
    rows = await list_user_connections(user_id)
    active = [r for r in rows if r.get("status") == "active"]
    if not active:
        return "No connectors wired — produce drafts only (cannot send/publish/execute)."

    lines = []
    for row in active:
        t = row["connector_type"]
        label = _CONNECTOR_LABELS.get(t, t)
        actions = _CONNECTOR_ACTIONS.get(t, [])
        action_str = ", ".join(actions) if actions else "connected"
        lines.append(f"- **{label}**: {action_str}")

    block = "\n".join(lines)
    return (
        "## Connected Tools\n"
        "The user has authorized the following services. You may use these to take real actions:\n\n"
        f"{block}\n\n"
        "Always produce a clear draft or summary for user review before executing irreversible actions "
        "(sending messages, creating records, charging customers)."
    )
