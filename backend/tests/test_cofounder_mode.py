"""Batch 71/72 — Co-Founder Mode unit tests (no network)."""
from backend.lib.business.notify import DAILY_CAP, _build_html
from backend.lib.business.operator.analyst import build_digest
from backend.lib.business.operator.executor_agent import (
    _initiative_prompt,
    _parse_needs,
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


def test_digest_includes_answers_on_record_and_open_questions():
    digest = build_digest(_snapshot({
        "qna": {
            "ok": True,
            "answers": "- Q: What's your close rate? -> A: Around 20% on referrals",
            "open_questions": ["What margin do you make on Emperor tier?"],
        },
    }))
    assert "20% on referrals" in digest
    assert "never re-ask" in digest
    assert "do NOT re-ask" in digest
    assert "Emperor tier" in digest


def test_parse_needs_extracts_executor_escalations():
    report = (
        "DONE\n"
        "Sent revival email to sarah@acme.co\n"
        "Skipped step 2 - no reply-to on record\n"
        "NEED: Which email should replies go to - sales@ or your personal?\n"
        "need: What's the discount ceiling I can offer stale deals?\n"
        "NEEDLESS line that should not match\n"
    )
    needs = _parse_needs(report)
    assert len(needs) == 2
    assert needs[0].startswith("Which email")
    assert needs[1].startswith("What's the discount ceiling")
    assert _parse_needs("") == []
    assert _parse_needs("DONE\nAll steps executed.") == []


def test_notification_email_promises_the_cap():
    html = _build_html("Your co-founder prepared 4 moves", ["Line one.", "Line two."], "https://jarvismgco.com")
    assert f"max {DAILY_CAP} a day" in html
    assert "Line one." in html
    assert "Open Rue" in html
