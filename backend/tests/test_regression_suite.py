"""
Phase 5 — live regression suite for JARVIS-BRAIN-MAP.md section D.

These tests hit a REAL running local server (`uvicorn backend.main:app
--host 127.0.0.1 --port 8123`) with real Anthropic/Supabase/Mem0 credentials.
They make real LLM calls — slow, non-free, and not bit-for-bit
deterministic (the assertions are deliberately loose: they check for the
*shape* of correct behavior, not exact wording).

Skipped by default. Run explicitly with the local server up:

    RUN_LIVE_TESTS=1 python -m pytest backend/tests/test_regression_suite.py -v -s

See JARVIS-REGRESSION-CHECKLIST.md for the items this suite intentionally
does NOT automate (e.g. regression #4's real-time in-app reminder delivery,
and the full Business Creation -> Vercel deploy pipeline).
"""
import json
import os
import re
import uuid
from datetime import datetime, timezone

import httpx
import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LIVE_TESTS") != "1",
    reason="live regression suite — set RUN_LIVE_TESTS=1 and run a local server on :8123",
)

BASE = os.environ.get("JARVIS_LIVE_BASE_URL", "http://127.0.0.1:8123")

# Real, existing user with a seeded profile (identity.name == "Mohamed").
REAL_PERSONAL_USER = "user_d4533f296ca9410cb49c65feeed9978b"


def _new_user(label: str) -> str:
    return f"live-regression-{label}-{uuid.uuid4().hex[:8]}"


def _chat(message: str, user_id: str) -> str:
    r = httpx.post(f"{BASE}/api/chat", json={"user_id": user_id, "message": message}, timeout=60)
    r.raise_for_status()
    return r.json()["response"]


def _business_chat(message: str, user_id: str) -> str:
    """Collect the text chunks of /api/business/chat/stream's SSE response."""
    chunks: list[str] = []
    with httpx.stream(
        "POST", f"{BASE}/api/business/chat/stream",
        json={"user_id": user_id, "message": message}, timeout=60,
    ) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line.startswith("data: "):
                continue
            payload = line[len("data: "):]
            if payload == "[DONE]":
                break
            decoded = json.loads(payload)
            if isinstance(decoded, str):
                chunks.append(decoded)
    return "".join(chunks)


# ─── Regression 1: agent-edit phrasing routes to chat, not creation ────────

def test_regression_1_agent_edit_routes_to_chat():
    r = httpx.post(
        f"{BASE}/api/business/classify-intent",
        json={
            "message": "Adjust the agent's greeting to sound more human",
            "active_agent_id": "agent_abc123xyz0",
            "recent_assistant_texts": [
                "Your agent (agent_abc123xyz0) is live and ready to take calls."
            ],
            "has_attachments": False,
        },
        timeout=30,
    )
    r.raise_for_status()
    assert r.json()["intent"] == "chat"


# ─── Regression 2: dead restaurant URL — no invented facts ─────────────────

def test_regression_2_dead_restaurant_url_no_invented_facts():
    resp = _business_chat(
        "Here is my restaurant website: "
        "https://this-restaurant-domain-does-not-exist-zzzqq123.com -- "
        "whats on the menu and when was it founded?",
        _new_user("2"),
    )
    lowered = resp.lower()
    # Acknowledges the request couldn't be fulfilled from the (dead) site.
    assert any(kw in lowered for kw in ("error", "couldn't", "can't", "dead", "doesn't exist", "failed", "down"))
    # Never states a confident specific founding year as fact.
    assert not re.search(r"\b(founded|since|established)\b[^.]{0,20}(18|19|20)\d{2}", lowered)


# ─── Regression 3: profile recall (B4 grounding) ───────────────────────────

def test_regression_3_profile_recall_real_user():
    resp = _chat("What is my name?", REAL_PERSONAL_USER)
    assert "mohamed" in resp.lower()


# ─── Regression 4: "remind me in 1 min" saves a real ~60s reminder ────────

def test_regression_4_reminder_saved_with_correct_time():
    # A brand-new user_id's first message hits the onboarding gate (tools
    # suppressed) — use the real, already-onboarded user so tools are active,
    # same as regression 3.
    user_id = REAL_PERSONAL_USER
    before = datetime.now(timezone.utc)
    _chat("Remind me in 1 min (test) to check the oven", user_id)

    r = httpx.get(f"{BASE}/api/notes/{user_id}", timeout=30)
    r.raise_for_status()
    notes = r.json()["notes"]
    assert notes, "expected a note to be saved"

    # _load_notes orders by created_at.desc — newest note is first.
    note = notes[0]
    assert note["remind_at"], "expected remind_at to be set"
    remind_at = datetime.fromisoformat(note["remind_at"])
    delta_seconds = (remind_at - before).total_seconds()
    assert 20 <= delta_seconds <= 180, f"remind_at not ~1 minute out: {delta_seconds}s"

    httpx.delete(f"{BASE}/api/notes/{user_id}/{note['id']}", timeout=30)


# ─── Regression 5: plain note save, no unnecessary clarifying questions ────

def test_regression_5_plain_note_saved_without_unnecessary_questions():
    # Same as regression 4 — use the real, already-onboarded user so tools
    # (save_note) are actually active.
    user_id = REAL_PERSONAL_USER
    resp = _chat("Note this down (test): the supplier called, new lead time is 3 weeks", user_id)

    r = httpx.get(f"{BASE}/api/notes/{user_id}", timeout=30)
    r.raise_for_status()
    notes = r.json()["notes"]
    assert notes, "expected a note to be saved"

    # _load_notes orders by created_at.desc — newest note is first.
    note = notes[0]
    assert "lead time" in note["note"].lower() or "3 weeks" in note["note"]
    assert note["remind_at"] is None
    # Confirmation, not a clarifying question.
    assert not resp.strip().endswith("?")

    httpx.delete(f"{BASE}/api/notes/{user_id}/{note['id']}", timeout=30)


# ─── Regression 6: ambiguous "remember the thing we talked about" ──────────

def test_regression_6_ambiguous_remember_asks_clarifying_question():
    resp = _chat("can you remember the thing we talked about?", _new_user("6"))
    assert "?" in resp


# ─── Regression 7: tool failure reported honestly, never as success ───────

def test_regression_7_tool_failure_reported_honestly():
    r = httpx.post(
        f"{BASE}/api/business/chat/confirm-action",
        json={
            "user_id": _new_user("7"),
            "tool_name": "elevenlabs__update_agent",
            "tool_input": {"agent_id": "fake_agent_123", "first_message": "Hey there!"},
        },
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    assert "error" in data["tool_result"]

    lowered = data["response"].lower()
    assert any(kw in lowered for kw in ("fail", "not connected", "error", "couldn't", "can't"))
    assert "done" not in lowered and "updated" not in lowered
