"""
Phase 3 — CRM cockpit support endpoint.

Tells the frontend whether to show the "CRM" nav item for this user and where to embed
their white-labeled Rue CRM. Resolves the SAME per-user workspace the agent uses
(Phase 2 routing), so the cockpit shows exactly the tenant Rue writes to.
"""
import re

from fastapi import APIRouter, Response

from backend.lib.business.twenty import workspaces
from backend.lib.business.twenty.client import TwentyClient

router = APIRouter()

# The CRM root domain. The apex + any provisioned subdomain may get an on-demand cert.
CRM_ROOT = "crm.jarvismgco.com"
_HOST_RE = re.compile(r"^[a-z0-9-]+\.crm\.jarvismgco\.com$")


@router.get("/business/crm/tls-check")
async def tls_check(domain: str = ""):
    """Caddy on-demand-TLS `ask`: 200 = issue a cert, anything else = refuse.

    Allows the apex and any subdomain that maps to a provisioned workspace, so certs
    are only ever minted for real Rue CRM workspaces (prevents cert-abuse). Fast.
    """
    host = (domain or "").strip().lower().split(":")[0]
    if host == CRM_ROOT:
        return Response(status_code=200)
    if _HOST_RE.match(host) and await workspaces.domain_is_provisioned(host):
        return Response(status_code=200)
    return Response(status_code=403)


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
            "pending": False,
            "shared": False,
            "embed_url": ws["base_url"],
            "display_name": ws.get("display_name") or "Rue CRM",
            "subdomain": ws.get("subdomain"),
        }

    # Fallback: a single shared instance (Phase 1) — still embeddable, not per-client.
    if TwentyClient.configured():
        import os
        return {
            "provisioned": True,
            "pending": False,
            "shared": True,
            "embed_url": os.getenv("TWENTY_API_URL", "").rstrip("/") or None,
            "display_name": "Rue CRM",
            "subdomain": None,
        }

    # Not provisioned yet — distinguish "setting up your CRM…" from "never started".
    pending = await workspaces.is_pending(user_id)
    return {"provisioned": False, "pending": pending, "shared": False,
            "embed_url": None, "display_name": "Rue CRM", "subdomain": None}
