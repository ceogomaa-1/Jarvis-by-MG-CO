"""Batch 71 — Co-Founder Mode unit tests (no network)."""
from backend.lib.business.operator.analyst import build_digest
from backend.lib.business.operator.executor_agent import (
    _initiative_prompt,
    _summarize_tool_result,
)


def _snapshot(sections):
    return {"sections": sections, "scanned_at": "2026-07-02T00:00:00Z"}


def test_digest_renders_live_sections():
    digest = build_digest(_snapshot({
        "crm": {
            "ok": True, "open_opportunities": 7, "pipeline_value_usd": 42500.0,
            "pipeline_by_stage": {"NEW": 3, "PROPOSAL": 4},
            "stale_deals_14d": ["Acme Corp"], "stale_count": 1, "companies_note": "",
        },
        "leads": {"ok": True, "total_scored": 12, "by_grade": {"A": 3, "B": 9}, "top_a_leads": ["Bright Dental"]},
        "google": {"ok": True, "unread_count": 5, "unread_subjects": ["Re: proposal"], "upcoming_events": 2, "next_events": []},
        "stripe": {"ok": False, "note": "Stripe not connected"},
        "buffer": {"ok": True, "scheduled_posts": 0},
        "decisions": {"ok": True, "total": 2, "approved": ["Send revival emails"], "declined": ["Buy ads (reason: too pricey)"]},
    }))
    assert "7 open opportunities" in digest
    assert "$42,500" in digest
    assert "Acme Corp" in digest
    assert "Bright Dental" in digest
    assert "gone dark" in digest              # empty social queue is called out
    assert "Stripe not connected" in digest   # missing sources reported honestly
    assert "too pricey" in digest             # decline reasons feed the learning loop


def test_digest_survives_all_sources_down():
    digest = build_digest(_snapshot({
        "crm": {"ok": False, "note": "CRM scan timed out"},
        "leads": {"ok": False, "note": "Leads engine not enabled"},
        "google": {"ok": False, "note": "Google not connected"},
        "stripe": {"ok": False, "note": "Stripe not connected"},
        "buffer": {"ok": False, "note": "Buffer not connected"},
        "decisions": {"ok": False, "note": "no supabase"},
    }))
    assert "Unavailable" in digest
    assert "timed out" in digest


def test_initiative_prompt_carries_the_approved_contract():
    prompt = _initiative_prompt({
        "title": "Send revival emails to 4 stale deals",
        "action_type": "email_draft",
        "description": "Re-engage deals untouched 14+ days",
        "expected_impact": "4 warm conversations reopened",
        "execution_plan": {
            "mode": "auto",
            "steps": ["Send drafted email to sarah@acme.co", "Log a CRM note on each deal"],
            "tools": ["google__send_email", "twenty__add_note"],
        },
        "artifact_markdown": "Subject: Quick one\n\nHey [Name]...",
        "artifact_metadata": {"preparation_type": "outreach"},
    })
    assert "Send revival emails to 4 stale deals" in prompt
    assert "1. Send drafted email to sarah@acme.co" in prompt
    assert "google__send_email" in prompt
    assert "Subject: Quick one" in prompt


def test_tool_result_summary_flags_errors():
    ok, note = _summarize_tool_result('{"error": "Not connected to google."}')
    assert ok is False and "Not connected" in note
    ok, note = _summarize_tool_result('{"sent": true, "to": "a@b.co"}')
    assert ok is True and "a@b.co" in note
    ok, note = _summarize_tool_result("plain text result")
    assert ok is True
