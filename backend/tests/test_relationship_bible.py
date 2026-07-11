"""
Tests for the Relationship Playbook ("the Bible") — Rue Personal only.

Covers bible loading, the system-prompt injection wrapper, and the
relationship-context detector (keyword/regex fast path + Haiku fallback).

Run with:  pytest backend/tests/test_relationship_bible.py -v
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.lib.personal.relationship_bible import (
    _BIBLE_MD,
    build_relationship_injection,
    is_relationship_context,
    load_bible,
)


# ---------------------------------------------------------------------------
# 1. Bible loading
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not os.path.exists(_BIBLE_MD), reason="relationship_bible.md not present")
class TestLoadBible:
    def test_non_empty(self):
        assert load_bible()

    def test_contains_core_sections(self):
        text = load_bible()
        assert "PRIME DIRECTIVES" in text
        assert "THE VOICE" in text
        assert "ETHICS / RED LINES" in text
        assert "CALIBRATION" in text


class TestLoadBibleResilience:
    def test_missing_file_returns_empty(self, tmp_path):
        assert load_bible(md_path=str(tmp_path / "no.md")) == ""

    def test_empty_file_returns_empty(self, tmp_path):
        f = tmp_path / "empty.md"
        f.write_text("")
        assert load_bible(md_path=str(f)) == ""


# ---------------------------------------------------------------------------
# 2. System-prompt injection wrapper
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not os.path.exists(_BIBLE_MD), reason="relationship_bible.md not present")
class TestBuildInjection:
    def test_non_empty(self):
        assert build_relationship_injection()

    def test_announces_relationship_mode(self):
        assert "RELATIONSHIP MODE" in build_relationship_injection()

    def test_contains_bible_content(self):
        injection = build_relationship_injection()
        assert "PRIME DIRECTIVES" in injection
        assert "ETHICS / RED LINES" in injection

    def test_mentions_calibration_override(self):
        injection = build_relationship_injection()
        assert "wellbeing" in injection.lower()


class TestBuildInjectionResilience:
    def test_missing_file_returns_empty(self, tmp_path):
        assert build_relationship_injection(md_path=str(tmp_path / "no.md")) == ""


# ---------------------------------------------------------------------------
# 3. Relationship-context detection — strong signals (no Haiku needed)
# ---------------------------------------------------------------------------
class TestStrongSignals:
    @pytest.mark.asyncio
    async def test_girlfriend(self):
        assert await is_relationship_context("my girlfriend hasn't texted me back in two days")

    @pytest.mark.asyncio
    async def test_breakup(self):
        assert await is_relationship_context("we broke up last week and I don't know what to do")

    @pytest.mark.asyncio
    async def test_standalone_ex(self):
        assert await is_relationship_context("should I text my ex back?")

    @pytest.mark.asyncio
    async def test_get_her_back(self):
        assert await is_relationship_context("how do I get my ex back, she left me 2 weeks ago")

    @pytest.mark.asyncio
    async def test_situationship(self):
        assert await is_relationship_context("it's complicated, more of a situationship honestly")

    @pytest.mark.asyncio
    async def test_what_are_we(self):
        assert await is_relationship_context("should I just ask him what are we at this point")

    @pytest.mark.asyncio
    async def test_signal_from_recent_history(self):
        # Current message alone has no signal, but recent context does.
        recent = "ugh my boyfriend has been so distant lately"
        assert await is_relationship_context("what should I even say to him", recent)


# ---------------------------------------------------------------------------
# 4. Relationship-context detection — no signal at all
# ---------------------------------------------------------------------------
class TestNoSignal:
    @pytest.mark.asyncio
    async def test_unrelated_question(self):
        assert not await is_relationship_context("can you help me plan my week?")

    @pytest.mark.asyncio
    async def test_calendar_date_question(self):
        assert not await is_relationship_context("what's today's date?")

    @pytest.mark.asyncio
    async def test_ex_employer_does_not_trigger(self):
        # "ex-" compounds (hyphenated) must not match the standalone "ex" check.
        assert not await is_relationship_context("my ex-employer still owes me my last paycheck")

    @pytest.mark.asyncio
    async def test_example_word_does_not_trigger(self):
        assert not await is_relationship_context("let me give you an example of what happened at work")

    @pytest.mark.asyncio
    async def test_empty_message(self):
        assert not await is_relationship_context("")


# ---------------------------------------------------------------------------
# 5. Two weak signals together count as strong (no Haiku needed)
# ---------------------------------------------------------------------------
class TestWeakSignalsCombine:
    @pytest.mark.asyncio
    async def test_two_weak_terms(self):
        # "she texted" + "jealous" = 2 weak hits -> treated as strong
        msg = "she texted me back and now I feel jealous she's replying to other people too"
        assert await is_relationship_context(msg)

    @pytest.mark.asyncio
    async def test_slow_reply_low_effort_text(self):
        # "to reply" + "haha yeah" = 2 weak hits -> treated as strong
        msg = "she took 6 hours to reply and just said 'haha yeah', what do I do?"
        assert await is_relationship_context(msg)

    @pytest.mark.asyncio
    async def test_fight_and_wants_space(self):
        # "had a fight" + "wants space" = 2 weak hits -> treated as strong
        msg = "we had a fight, she wants space, should I send a long paragraph?"
        assert await is_relationship_context(msg)


# ---------------------------------------------------------------------------
# 6. Single weak signal — delegates to the Haiku confirmation fallback
# ---------------------------------------------------------------------------
class TestSingleWeakSignalDelegatesToHaiku:
    @pytest.mark.asyncio
    async def test_confirmed_true(self, monkeypatch):
        async def _fake_confirm(message, recent_text=""):
            return True

        monkeypatch.setattr(
            "backend.lib.personal.relationship_bible._confirm_with_haiku", _fake_confirm
        )
        # "partner" alone is ambiguous (business vs. romantic) -> single weak hit
        assert await is_relationship_context("my partner and I had a rough night")

    @pytest.mark.asyncio
    async def test_confirmed_false(self, monkeypatch):
        async def _fake_confirm(message, recent_text=""):
            return False

        monkeypatch.setattr(
            "backend.lib.personal.relationship_bible._confirm_with_haiku", _fake_confirm
        )
        assert not await is_relationship_context("my business partner and I had a rough night")
