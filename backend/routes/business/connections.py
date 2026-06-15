"""
API for connector management.

  GET    /business/connections/manifests          → list of available connector types + their required fields
  GET    /business/connections                    → list of user's connections (with status)
  POST   /business/connections                    → upsert credentials + run test immediately
  POST   /business/connections/test               → test an existing connection
  DELETE /business/connections                    → remove a connection
  GET    /business/connections/google/auth        → redirect to Google OAuth consent screen
  GET    /business/connections/google/callback    → handle Google OAuth callback
"""
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from backend.lib.business.connectors.registry import (
    DEFAULT_ACCOUNT_LABEL,
    MAX_ACCOUNTS_PER_TYPE,
    list_available_connectors,
    list_user_connections,
    list_user_connections_for_type,
    upsert_user_connection,
    get_connector_for_user,
    delete_user_connection,
    update_test_result,
    connector_class,
)

FRONTEND_URL = os.getenv("FRONTEND_URL", "https://jarvis-by-mg-co.vercel.app")

router = APIRouter()


@router.get("/business/connections/manifests")
async def get_manifests():
    return {"connectors": list_available_connectors()}


@router.get("/business/connections")
async def get_user_connections(user_id: str = ""):
    if not user_id:
        return {"connections": []}
    rows = await list_user_connections(user_id)
    return {"connections": rows}


@router.get("/business/connections/{connector_type}/accounts")
async def get_connector_accounts(connector_type: str, user_id: str = ""):
    """List every account (any label) a user has for one connector type —
    used by the multi-account UI (e.g. up to 3 GoHighLevel accounts)."""
    if not user_id:
        return {"accounts": []}
    rows = await list_user_connections_for_type(user_id, connector_type)
    return {"accounts": rows, "max_accounts": MAX_ACCOUNTS_PER_TYPE}


class UpsertConnectionRequest(BaseModel):
    user_id: str
    connector_type: str
    credentials: dict
    display_name: str = ""
    account_label: str = DEFAULT_ACCOUNT_LABEL


@router.post("/business/connections")
async def upsert_connection(request: UpsertConnectionRequest):
    if not request.user_id or not request.connector_type:
        raise HTTPException(status_code=400, detail="user_id and connector_type required")
    cls = connector_class(request.connector_type)
    if not cls:
        raise HTTPException(status_code=400, detail=f"Unknown connector_type: {request.connector_type}")

    # New account labels are capped at MAX_ACCOUNTS_PER_TYPE per user+type
    existing = await list_user_connections_for_type(request.user_id, request.connector_type)
    existing_labels = {a["account_label"] for a in existing}
    if request.account_label not in existing_labels and len(existing_labels) >= MAX_ACCOUNTS_PER_TYPE:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum of {MAX_ACCOUNTS_PER_TYPE} {cls.DISPLAY_NAME} accounts per user.",
        )

    # Save first (so even if test fails, credentials are stored — user can retry)
    row = await upsert_user_connection(
        user_id=request.user_id,
        connector_type=request.connector_type,
        credentials=request.credentials,
        display_name=request.display_name or cls.DISPLAY_NAME,
        account_label=request.account_label,
    )
    if not row:
        raise HTTPException(status_code=500, detail="Failed to save connection")

    # Now test
    instance = cls(credentials=request.credentials)
    result = await instance.test()
    await update_test_result(request.user_id, request.connector_type, result, account_label=request.account_label)

    return {
        "ok": result.ok,
        "error": result.error,
        "data": result.data,
        "connection_id": row.get("id"),
    }


class TestConnectionRequest(BaseModel):
    user_id: str
    connector_type: str
    account_label: str = DEFAULT_ACCOUNT_LABEL


@router.post("/business/connections/test")
async def test_connection(request: TestConnectionRequest):
    if not request.user_id or not request.connector_type:
        raise HTTPException(status_code=400, detail="user_id and connector_type required")
    instance = await get_connector_for_user(request.user_id, request.connector_type, request.account_label)
    if not instance:
        raise HTTPException(status_code=404, detail="Connection not found or inactive")
    result = await instance.test()
    await update_test_result(request.user_id, request.connector_type, result, account_label=request.account_label)
    return {"ok": result.ok, "error": result.error, "data": result.data}


class DeleteConnectionRequest(BaseModel):
    user_id: str
    connector_type: str
    account_label: str = DEFAULT_ACCOUNT_LABEL


@router.delete("/business/connections")
async def delete_connection(request: DeleteConnectionRequest):
    ok = await delete_user_connection(request.user_id, request.connector_type, request.account_label)
    return {"ok": ok}


# ─── Google OAuth endpoints ────────────────────────────────────────────────────

@router.get("/business/connections/google/auth")
async def google_auth_redirect(user_id: str = ""):
    """Redirect user to Google OAuth consent screen."""
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id required")
    from backend.lib.business.connectors.google_conn import GoogleConnector
    url = GoogleConnector.get_auth_url(user_id)
    return RedirectResponse(url)


@router.get("/business/connections/google/callback")
async def google_oauth_callback(code: str = "", state: str = "", error: str = ""):
    """Handle Google OAuth callback — exchange code for tokens, store, redirect to frontend."""
    if error:
        return RedirectResponse(f"{FRONTEND_URL}/business/chat?connector_error={error}")

    if not code or not state:
        return RedirectResponse(f"{FRONTEND_URL}/business/chat?connector_error=missing_code")

    user_id = state

    from backend.lib.business.connectors.google_conn import GoogleConnector
    tokens = await GoogleConnector.handle_callback(code=code)

    if not tokens.get("refresh_token"):
        return RedirectResponse(
            f"{FRONTEND_URL}/business/chat?connector_error=no_refresh_token"
        )

    # Store tokens in business_connections
    await upsert_user_connection(
        user_id=user_id,
        connector_type="google",
        credentials=tokens,
        display_name="Google (Calendar + Gmail)",
    )

    # Verify by running test
    g = GoogleConnector(credentials=tokens)
    result = await g.test()
    await update_test_result(user_id, "google", result)

    return RedirectResponse(f"{FRONTEND_URL}/business/chat?connector_connected=google")
