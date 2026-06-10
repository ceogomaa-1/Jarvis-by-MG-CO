"""
Phase 0 smoke suite (Batch 42).

Hits every GET route in the app (Personal + Business) against `.env.test`
config (no Supabase/Anthropic/connector credentials) with a dummy user_id,
and asserts the status code + response shape documented in
STABILITY-AUDIT.md (sections 1 and 2).

This is the regression baseline for every later phase: a route dropping out
of this list, returning an unexpected status, or losing an expected key
should fail this suite.
"""

import pytest

DUMMY_USER = "smoke_test_user_phase0"
DUMMY_UUID = "00000000-0000-0000-0000-000000000000"


# Each entry: (path, params, expected_status, required_keys_or_None)
# required_keys_or_None: list of top-level keys that must be present in the
# JSON response, or None to skip the shape check (e.g. for list responses).
PERSONAL_GET_ROUTES = [
    ("/", {}, 200, ["status"]),
    (f"/api/usage", {"user_id": DUMMY_USER}, 200,
     ["used", "limit", "remaining", "is_admin", "resets_in"]),
    ("/api/debug/last-error", {}, 200, None),  # list response
    (f"/api/history/{DUMMY_USER}", {}, 200, ["messages"]),
    (f"/api/memory/{DUMMY_USER}", {}, 200, ["user_id", "count", "memories"]),
    (f"/api/notes/{DUMMY_USER}", {}, 200, ["user_id", "count", "notes"]),
    (f"/api/proactive/{DUMMY_USER}", {}, 200, ["messages"]),
    (f"/api/proactive/check/{DUMMY_USER}", {}, 200,
     ["has_message", "message", "trigger_type"]),
    (f"/api/user-preferences/{DUMMY_USER}", {}, 200, ["jarvis_mode"]),
    (f"/api/google/status/{DUMMY_USER}", {}, 200, ["connected"]),
    (f"/api/user/onboarding-status/{DUMMY_USER}", {}, 200,
     ["user_id", "onboarding_complete", "interaction_count", "trust_level"]),
    (f"/api/user/model/{DUMMY_USER}", {}, 200, None),  # full internal model dict
]

BUSINESS_GET_ROUTES = [
    ("/api/business/usage", {"user_id": DUMMY_USER}, 200,
     ["used", "limit", "remaining", "is_admin", "resets_in", "window_minutes"]),
    ("/api/business/connections/manifests", {}, 200, ["connectors"]),
    ("/api/business/connections", {"user_id": DUMMY_USER}, 200, ["connections"]),
    ("/api/business/connections", {}, 200, ["connections"]),
    ("/api/business/conversations", {"user_id": DUMMY_USER}, 200, ["conversations"]),
    (f"/api/business/conversations/{DUMMY_UUID}", {"user_id": DUMMY_USER}, 200,
     ["conversation", "messages"]),
    ("/api/business/agents/activity", {"user_id": DUMMY_USER}, 200, ["agents"]),
    ("/api/business/memories/count", {"user_id": DUMMY_USER}, 200, ["count"]),
    ("/api/business/operator/pending", {"user_id": DUMMY_USER}, 200, ["actions"]),
    ("/api/business/operator/runs", {"user_id": DUMMY_USER}, 200, ["runs"]),
    ("/api/business/proactive/latest", {"user_id": DUMMY_USER}, 200, ["briefing"]),
    ("/api/business/metrics", {"user_id": DUMMY_USER}, 200, ["metrics_text", "updated_at"]),
    ("/api/business/readiness", {"user_id": DUMMY_USER}, 200,
     ["score", "checkpoints", "memory_count", "connector_count", "is_ready", "next_milestone"]),
    ("/api/business/proactive/unread", {"user_id": DUMMY_USER}, 200, ["messages"]),
    ("/api/business/brand", {"user_id": DUMMY_USER}, 200, ["brand"]),
    ("/api/business/deploy-status", {}, 200, ["state", "url", "error", "logs"]),
]


@pytest.mark.parametrize("path,params,expected_status,keys", PERSONAL_GET_ROUTES)
def test_personal_get_route(client, path, params, expected_status, keys):
    resp = client.get(path, params=params)
    assert resp.status_code == expected_status, resp.text
    if keys is not None:
        body = resp.json()
        assert isinstance(body, dict)
        for key in keys:
            assert key in body, f"missing key {key!r} in {body}"


@pytest.mark.parametrize("path,params,expected_status,keys", BUSINESS_GET_ROUTES)
def test_business_get_route(client, path, params, expected_status, keys):
    resp = client.get(path, params=params)
    assert resp.status_code == expected_status, resp.text
    if keys is not None:
        body = resp.json()
        assert isinstance(body, dict)
        for key in keys:
            assert key in body, f"missing key {key!r} in {body}"


# ─── Validation / error-path routes ────────────────────────────────────────

def test_personal_usage_requires_user_id(client):
    resp = client.get("/api/usage")
    assert resp.status_code == 400


def test_business_usage_missing_user_id_returns_error_in_200(client):
    """Documented inconsistency (defect #17): unlike /api/usage (400), the
    Business equivalent returns HTTP 200 with an {"error": ...} body."""
    resp = client.get("/api/business/usage")
    assert resp.status_code == 200
    assert resp.json() == {"error": "user_id required"}


def test_business_readiness_requires_user_id(client):
    resp = client.get("/api/business/readiness")
    assert resp.status_code == 400


def test_business_brand_requires_user_id(client):
    resp = client.get("/api/business/brand")
    assert resp.status_code == 400


def test_business_proxy_image_requires_url(client):
    resp = client.get("/api/business/proxy-image")
    assert resp.status_code == 422


def test_business_operator_status_stream_requires_run_id(client):
    resp = client.get("/api/business/operator/status/stream")
    assert resp.status_code == 422


def test_business_create_pdf_unknown_id_is_404(client):
    resp = client.get("/api/business/create/not-a-real-id/pdf")
    assert resp.status_code == 404


# ─── Voice routes (CARTESIA_API_KEY unset in .env.test → 503) ─────────────

@pytest.mark.parametrize("path", [
    "/api/voice/list-voices",
    "/api/voice/test-tags",
    "/api/voice/test",
])
def test_voice_routes_503_without_cartesia_key(client, path):
    resp = client.get(path)
    assert resp.status_code == 503


# ─── OAuth redirects (must NOT follow — would hit real Google) ─────────────

def test_personal_google_auth_redirects_to_google(client):
    resp = client.get(f"/api/google/auth/{DUMMY_USER}", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert "accounts.google.com" in resp.headers["location"]


def test_business_google_auth_redirects_to_google(client):
    resp = client.get(
        "/api/business/connections/google/auth",
        params={"user_id": DUMMY_USER},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 307)
    assert "accounts.google.com" in resp.headers["location"]


def test_business_google_auth_requires_user_id(client):
    resp = client.get("/api/business/connections/google/auth", follow_redirects=False)
    assert resp.status_code == 400
