import logging
import os
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter
from fastapi.responses import RedirectResponse

logger = logging.getLogger(__name__)

router = APIRouter()

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID") or os.getenv("GOOGLE_AUTH_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET") or os.getenv("GOOGLE_AUTH_SECRET", "")
REDIRECT_URI = os.getenv(
    "GOOGLE_REDIRECT_URI",
    "https://jarvis-backend-4oz6.onrender.com/api/google/callback",
)


@router.get("/google/auth/{user_id}")
async def google_auth(user_id: str):
    """Redirect user to Google OAuth consent screen."""
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": (
            "https://www.googleapis.com/auth/calendar "
            "https://www.googleapis.com/auth/gmail.modify"
        ),
        "access_type": "offline",
        "prompt": "consent",
        "state": user_id,
    }
    return RedirectResponse("https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params))


@router.get("/google/callback")
async def google_callback(code: str, state: str):
    """Handle Google OAuth callback and store refresh token in Supabase."""
    user_id = state

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )

    tokens = resp.json()
    refresh_token = tokens.get("refresh_token", "")
    access_token = tokens.get("access_token", "")

    if refresh_token:
        print(f"GCAL: Attempting token store for user_id='{user_id}'")
        supabase_url = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
        supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        async with httpx.AsyncClient() as client:
            upsert_resp = await client.post(
                f"{supabase_url}/rest/v1/user_google_tokens",
                headers={
                    "apikey": supabase_key,
                    "Authorization": f"Bearer {supabase_key}",
                    "Content-Type": "application/json",
                    "Prefer": "resolution=merge-duplicates",
                },
                json={
                    "user_id": user_id,
                    "refresh_token": refresh_token,
                    "access_token": access_token,
                },
            )
        print(f"GCAL: Upsert response: status={upsert_resp.status_code} body={upsert_resp.text[:200]!r}")

        # Verify write succeeded by immediately re-reading
        from backend.tools.google_calendar import get_user_refresh_token
        verified = await get_user_refresh_token(user_id)
        if verified:
            logger.info(f"GCAL: Token verified for user_id={user_id!r}")
        else:
            logger.error(f"GCAL: Token write FAILED for user_id={user_id!r} — stored but not readable")

        return RedirectResponse("https://jarvis-by-mg-co.vercel.app/?calendar=connected")

    return {"error": "No refresh token received", "tokens": tokens}


@router.get("/google/status/{user_id}")
async def google_status(user_id: str):
    from backend.tools.google_calendar import get_user_refresh_token
    token = await get_user_refresh_token(user_id)
    return {"connected": bool(token)}
