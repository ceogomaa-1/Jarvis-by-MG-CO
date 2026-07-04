"""Batch 74 — auth layer (observe + flag-gated enforcement)."""
import asyncio
import base64
import json

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from backend.lib import auth


def _b64(d: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()


def make_jwt(payload: dict) -> str:
    return f"{_b64({'alg': 'HS256', 'typ': 'JWT'})}.{_b64(payload)}.sig"


def make_request(method="GET", path="/api/x", headers=None, query=""):
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "query_string": query.encode(),
    }
    return Request(scope)


# ── helpers ───────────────────────────────────────────────────────────────────

def test_canonical_user_id_matches_frontend_formula():
    # frontend: 'user_' + hex(uuid with dashes stripped)
    assert auth.canonical_user_id("a1b2c3d4-e5f6-7890-abcd-ef0123456789") == "user_a1b2c3d4e5f67890abcdef0123456789"
    assert auth.canonical_user_id("") == "user_"


def test_bearer_token_parsing():
    assert auth.bearer_token("Bearer abc.def.ghi") == "abc.def.ghi"
    assert auth.bearer_token("bearer xyz") == "xyz"
    assert auth.bearer_token("Basic abc") is None
    assert auth.bearer_token("") is None
    assert auth.bearer_token(None) is None
    assert auth.bearer_token("Bearer   ") is None


def test_decode_unverified_reads_sub_without_verifying():
    tok = make_jwt({"sub": "uuid-1", "email": "x@y.com"})
    assert auth.decode_unverified(tok)["sub"] == "uuid-1"
    assert auth.decode_unverified("not-a-jwt") is None
    assert auth.decode_unverified("a.b") is None or isinstance(auth.decode_unverified("a.b"), (dict, type(None)))


def test_exempt_paths():
    assert auth.is_auth_exempt("/health") is True
    assert auth.is_auth_exempt("/") is True
    assert auth.is_auth_exempt("/api/os1/webhook") is True
    assert auth.is_auth_exempt("/api/google/callback") is True
    assert auth.is_auth_exempt("/api/channels/telegram/webhook") is True
    assert auth.is_auth_exempt("/api/_authobs") is True
    # protected
    assert auth.is_auth_exempt("/api/os1/status") is False
    assert auth.is_auth_exempt("/api/business/chat") is False


# ── observe mode (default: REQUIRE_AUTH off) never blocks ──────────────────────

def test_observe_mode_never_blocks_even_without_token():
    assert auth.REQUIRE_AUTH is False  # default posture
    req = make_request(path="/api/os1/status", query="user_id=user_abc")
    # No token, protected route — must NOT raise in observe mode.
    assert asyncio.run(auth.auth_dependency(req)) is None


def test_observe_records_token_and_sub_match(monkeypatch):
    # isolate counters
    monkeypatch.setattr(auth, "_OBS", {"total": 0, "with_token": 0, "sub_match": 0, "missing": {}})
    tok = make_jwt({"sub": "abc"})
    req = make_request(
        path="/api/os1/status",
        headers={"authorization": f"Bearer {tok}"},
        query="user_id=user_abc",
    )
    asyncio.run(auth.auth_dependency(req))
    stats = auth.observation_stats()
    assert stats["total"] == 1
    assert stats["with_token"] == 1
    assert stats["sub_match"] == 1  # canonical_user_id('abc') == 'user_abc'


def test_observe_buckets_missing_token_by_path(monkeypatch):
    monkeypatch.setattr(auth, "_OBS", {"total": 0, "with_token": 0, "sub_match": 0, "missing": {}})
    asyncio.run(auth.auth_dependency(make_request(path="/api/business/home", query="user_id=user_x")))
    stats = auth.observation_stats()
    assert stats["with_token"] == 0
    assert any(p["path"] == "/api/business/home" for p in stats["top_missing_paths"])


# ── enforcement mode (REQUIRE_AUTH on) ─────────────────────────────────────────

def test_enforce_blocks_missing_token(monkeypatch):
    monkeypatch.setattr(auth, "REQUIRE_AUTH", True)
    req = make_request(path="/api/os1/status", query="user_id=user_abc")
    with pytest.raises(HTTPException) as ei:
        asyncio.run(auth.auth_dependency(req))
    assert ei.value.status_code == 401


def test_enforce_allows_valid_token(monkeypatch):
    monkeypatch.setattr(auth, "REQUIRE_AUTH", True)

    async def fake_verify(token):
        return {"id": "uuid-9", "email": "a@b.com"}

    monkeypatch.setattr(auth, "verify_token", fake_verify)
    tok = make_jwt({"sub": "uuid-9"})
    req = make_request(path="/api/os1/status", headers={"authorization": f"Bearer {tok}"}, query="user_id=user_uuid9")
    assert asyncio.run(auth.auth_dependency(req)) is None
    assert req.state.auth_user_id == "user_uuid9"


def test_enforce_rejects_invalid_token(monkeypatch):
    monkeypatch.setattr(auth, "REQUIRE_AUTH", True)

    async def fake_verify(token):
        return None  # Supabase says invalid

    monkeypatch.setattr(auth, "verify_token", fake_verify)
    req = make_request(path="/api/os1/status", headers={"authorization": "Bearer bad"}, query="user_id=user_abc")
    with pytest.raises(HTTPException) as ei:
        asyncio.run(auth.auth_dependency(req))
    assert ei.value.status_code == 401


def test_enforce_skips_exempt_and_options(monkeypatch):
    monkeypatch.setattr(auth, "REQUIRE_AUTH", True)
    # exempt webhook — no token, must pass
    assert asyncio.run(auth.auth_dependency(make_request(path="/api/os1/webhook"))) is None
    # OPTIONS preflight — must pass
    assert asyncio.run(auth.auth_dependency(make_request(method="OPTIONS", path="/api/os1/status"))) is None
