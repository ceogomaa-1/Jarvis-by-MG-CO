"""Supabase auth-token layer — Batch 74.

The frontend authenticates with Supabase and derives the app user_id as
'user_' + hex(auth uuid). This module lets the backend read and (when enforced)
verify the Supabase access token, deriving the SAME user_id from the token's
`sub` claim — so we can trust the caller instead of a client-supplied user_id,
WITHOUT changing any login / redirect / session behavior.

Rollout is staged and reversible:
  * Phase A/B ship with REQUIRE_AUTH off → this layer only OBSERVES (counts
    whether each request carries a valid token). It never blocks a request.
  * Phase C flips REQUIRE_AUTH on (one env var) → missing/invalid tokens get a
    401 on protected routes. Flip it back off to roll back instantly, no deploy.

Nothing here touches the OAuth redirect, the apex/www session cookie, or the
OS1 entry gate — those are a separate layer and stay exactly as they are.
"""
import base64
import json
import os
import time

import httpx
from fastapi import HTTPException, Request

_SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
# /auth/v1/user accepts the user's JWT as Bearer plus any project apikey.
_APIKEY = os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

# Master enforcement switch. OFF by default. Flip to "true" (Phase C) ONLY after
# observe stats show ~100% of real traffic on protected routes carries a valid,
# matching token. Setting it back to anything falsy is an instant rollback.
REQUIRE_AUTH = os.getenv("REQUIRE_AUTH", "").strip().lower() in ("1", "true", "yes", "on")

# Routes that legitimately carry NO user JWT and must never be gated: third-party
# webhooks (their own signature auth), the OAuth initiator/callback (they travel
# as browser redirects, so no Authorization header is possible), and the external
# cron pingers. Non-/api paths (/, /health, the /ws socket) are exempt by default
# because the middleware only inspects /api/*.
_EXEMPT_PREFIXES = (
    "/api/_authobs",  # the observe readout itself
    "/api/_chatdiag",  # the error-capture readout
    "/api/os1/webhook",
    "/api/os1/contact",
    "/api/google/auth",
    "/api/google/callback",
    "/api/channels/telegram/webhook",
    "/api/channels/whatsapp/webhook",
    "/api/notes/_dispatch",
    "/api/business/email/_dispatch",
)


def is_auth_exempt(path: str) -> bool:
    if not path.startswith("/api/"):
        return True
    return path.startswith(_EXEMPT_PREFIXES)


def canonical_user_id(sub: str) -> str:
    """The app user_id form used everywhere: 'user_' + hex(auth uuid), dashes stripped."""
    return "user_" + str(sub or "").replace("-", "")


def bearer_token(authorization: str | None) -> str | None:
    """Pull the token out of an 'Authorization: Bearer <token>' header."""
    if not authorization:
        return None
    parts = authorization.split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer" and parts[1].strip():
        return parts[1].strip()
    return None


def decode_unverified(token: str) -> dict | None:
    """Read a JWT payload WITHOUT verifying the signature. Observe-only — used to
    check whether the token's sub matches the claimed user_id. Never an access
    decision; enforcement uses verify_token()."""
    try:
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)  # base64url padding
        return json.loads(base64.urlsafe_b64decode(payload_b64))
    except Exception:
        return None


# Small TTL cache so enforcement doesn't call Supabase on every request.
_VERIFY_CACHE: dict[str, tuple[dict, float]] = {}
_VERIFY_TTL = 90.0


async def verify_token(token: str) -> dict | None:
    """Authoritatively verify a Supabase access token by asking Supabase who owns
    it. Returns the user dict ({'id', 'email', ...}) if valid, else None."""
    if not token or not _SUPABASE_URL or not _APIKEY:
        return None
    now = time.time()
    hit = _VERIFY_CACHE.get(token)
    if hit and hit[1] > now:
        return hit[0]
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                f"{_SUPABASE_URL}/auth/v1/user",
                headers={"Authorization": f"Bearer {token}", "apikey": _APIKEY},
            )
        if resp.status_code == 200:
            user = resp.json()
            _VERIFY_CACHE[token] = (user, now + _VERIFY_TTL)
            if len(_VERIFY_CACHE) > 2000:  # bound memory
                for k in [k for k, (_, exp) in _VERIFY_CACHE.items() if exp <= now]:
                    _VERIFY_CACHE.pop(k, None)
            return user
    except Exception:
        return None
    return None


# ── Observe counters (Phase A/B) ──────────────────────────────────────────────
# In-memory, best-effort; reset on restart. Measures token coverage on protected
# routes so we can confirm the frontend attaches a valid token everywhere BEFORE
# enforcement is switched on.
_OBS = {"total": 0, "with_token": 0, "sub_match": 0, "missing": {}}


def record_observation(path: str, token: str | None, claimed_user_id: str | None) -> None:
    _OBS["total"] += 1
    if token:
        _OBS["with_token"] += 1
        payload = decode_unverified(token)
        sub = payload.get("sub") if payload else None
        if sub and claimed_user_id and canonical_user_id(sub) == claimed_user_id:
            _OBS["sub_match"] += 1
    else:
        # Bucket by route so we can see exactly which callers still need the token.
        _OBS["missing"][path] = _OBS["missing"].get(path, 0) + 1


def observation_stats() -> dict:
    total = _OBS["total"] or 1
    top_missing = sorted(_OBS["missing"].items(), key=lambda kv: kv[1], reverse=True)[:20]
    return {
        "enforcing": REQUIRE_AUTH,
        "total": _OBS["total"],
        "with_token": _OBS["with_token"],
        "with_token_pct": round(100 * _OBS["with_token"] / total, 1),
        "sub_match": _OBS["sub_match"],
        "top_missing_paths": [{"path": p, "count": c} for p, c in top_missing],
    }


async def auth_dependency(request: Request) -> None:
    """Global FastAPI dependency (Batch 74). Runs before every route.

    Observe-only until REQUIRE_AUTH is switched on; then it 401s protected routes
    that lack a valid Supabase token. Deliberately a dependency, NOT a
    BaseHTTPMiddleware — so it never buffers or interferes with the SSE streaming
    chat responses. Never blocks in observe mode; any observe error is swallowed.
    """
    # Preflight carries no Authorization header — CORS handles it. Never gate it.
    if request.method == "OPTIONS":
        return
    path = request.url.path
    if is_auth_exempt(path):
        return
    token = bearer_token(request.headers.get("authorization"))
    try:
        record_observation(path, token, request.query_params.get("user_id"))
    except Exception:
        pass
    if REQUIRE_AUTH:
        user = await verify_token(token) if token else None
        if not user:
            raise HTTPException(status_code=401, detail="Please sign in again.")
        request.state.auth_user_id = canonical_user_id(user.get("id"))
