"""
Phase 3 — CRM cockpit support endpoint.

Tells the frontend whether to show the "CRM" nav item for this user and where to embed
their white-labeled Jarvis CRM. Resolves the SAME per-user workspace the agent uses
(Phase 2 routing), so the cockpit shows exactly the tenant Jarvis writes to.
"""
from fastapi import APIRouter

from backend.lib.business.twenty import workspaces
from backend.lib.business.twenty.client import TwentyClient

router = APIRouter()


@router.get("/business/crm/workspace")
async def crm_workspace(user_id: str):
    """Resolve the user's CRM workspace for the cockpit.

    Returns:
      provisioned  — true if the user has their own workspace (show the CRM nav item)
      embed_url    — the white-labeled CRM URL to embed (their subdomain), or None
      display_name — client-facing workspace name
      shared       — true if falling back to the Phase-1 shared instance
    """
    ws = await workspaces.get_workspace(user_id)
    if ws and ws.get("base_url"):
        return {
            "provisioned": True,
            "shared": False,
            "embed_url": ws["base_url"],
            "display_name": ws.get("display_name") or "Jarvis CRM",
            "subdomain": ws.get("subdomain"),
        }

    # Fallback: a single shared instance (Phase 1) — still embeddable, not per-client.
    if TwentyClient.configured():
        import os
        return {
            "provisioned": True,
            "shared": True,
            "embed_url": os.getenv("TWENTY_API_URL", "").rstrip("/") or None,
            "display_name": "Jarvis CRM",
            "subdomain": None,
        }

    return {"provisioned": False, "shared": False, "embed_url": None, "display_name": "Jarvis CRM", "subdomain": None}
