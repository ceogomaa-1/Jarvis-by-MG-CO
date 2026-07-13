"""
Tests for the per-user response-feedback trainer (message 👍/👎 under every
Rue reply). Feedback must land in the rater's OWN user model
(model_data.response_feedback), distill into ≤10 lessons, survive LLM
failures, never write when the profile lookup failed, and surface in
summarize_user_for_prompt for that user only.
"""
import json

import pytest

from backend import user_model
from backend.lib.personal import feedback_trainer
from backend.lib.personal.feedback_trainer import record_feedback
from backend.user_model import _fresh_model


def _patch_store(monkeypatch, model=None, lookup_failed=False):
    """Patch the trainer's persistence: returns dict capturing the saved model."""
    saved = {}
    base = model if model is not None else _fresh_model("user_test")

    async def fake_get(user_id):
        return base, lookup_failed

    async def fake_save(user_id, m):
        saved["user_id"] = user_id
        saved["model"] = m
        return True

    monkeypatch.setattr(feedback_trainer, "get_user_model", fake_get)
    monkeypatch.setattr(feedback_trainer, "save_user_model", fake_save)
    return saved


def _patch_llm(monkeypatch, reply=None, raises=False):
    import backend.llm as llm

    async def fake_think(*args, **kwargs):
        if raises:
            raise RuntimeError("anthropic down")
        return reply

    monkeypatch.setattr(llm, "jarvis_think", fake_think)


@pytest.mark.asyncio
async def test_invalid_rating_rejected(monkeypatch):
    saved = _patch_store(monkeypatch)
    result = await record_feedback("user_test", "meh", "some reply")
    assert result["ok"] is False
    assert result["reason"] == "invalid_rating"
    assert not saved  # nothing written


@pytest.mark.asyncio
async def test_empty_message_rejected(monkeypatch):
    saved = _patch_store(monkeypatch)
    result = await record_feedback("user_test", "up", "   ")
    assert result["ok"] is False
    assert result["reason"] == "empty_message"
    assert not saved


@pytest.mark.asyncio
async def test_lookup_failed_never_writes(monkeypatch):
    saved = _patch_store(monkeypatch, lookup_failed=True)
    result = await record_feedback("user_test", "up", "great reply")
    assert result["ok"] is False
    assert result["reason"] == "profile_unavailable"
    assert not saved


@pytest.mark.asyncio
async def test_feedback_stores_log_and_lessons(monkeypatch):
    saved = _patch_store(monkeypatch)
    _patch_llm(monkeypatch, reply='{"lessons": ["Keep replies short and direct"]}')

    result = await record_feedback(
        "user_test", "down", "a very long rambling reply",
        user_prompt="quick question", comment="too long",
    )
    assert result["ok"] is True
    assert result["lessons_count"] == 1

    fb = saved["model"]["response_feedback"]
    assert fb["lessons"] == ["Keep replies short and direct"]
    assert len(fb["log"]) == 1
    entry = fb["log"][0]
    assert entry["rating"] == "down"
    assert entry["comment"] == "too long"
    assert entry["prompt"] == "quick question"
    assert "rambling" in entry["response"]


@pytest.mark.asyncio
async def test_llm_failure_keeps_old_lessons_but_logs(monkeypatch):
    model = _fresh_model("user_test")
    model["response_feedback"] = {"log": [], "lessons": ["Existing lesson"]}
    saved = _patch_store(monkeypatch, model=model)
    _patch_llm(monkeypatch, raises=True)

    result = await record_feedback("user_test", "up", "nice reply")
    assert result["ok"] is True
    fb = saved["model"]["response_feedback"]
    assert fb["lessons"] == ["Existing lesson"]  # unchanged on LLM failure
    assert len(fb["log"]) == 1                   # raw event still recorded


@pytest.mark.asyncio
async def test_log_capped_and_lessons_capped(monkeypatch):
    model = _fresh_model("user_test")
    model["response_feedback"] = {
        "log": [{"ts": "t", "rating": "up", "response": f"r{i}", "prompt": "", "comment": ""}
                for i in range(feedback_trainer.MAX_LOG)],
        "lessons": [],
    }
    saved = _patch_store(monkeypatch, model=model)
    too_many = json.dumps({"lessons": [f"lesson {i}" for i in range(25)]})
    _patch_llm(monkeypatch, reply=too_many)

    result = await record_feedback("user_test", "up", "newest reply")
    fb = saved["model"]["response_feedback"]
    assert len(fb["log"]) == feedback_trainer.MAX_LOG          # capped
    assert fb["log"][-1]["response"] == "newest reply"          # newest kept
    assert len(fb["lessons"]) == feedback_trainer.MAX_LESSONS   # capped
    assert result["lessons_count"] == feedback_trainer.MAX_LESSONS


@pytest.mark.asyncio
async def test_lessons_injected_into_prompt_summary(monkeypatch):
    model = _fresh_model("user_test")
    model["identity"]["name"] = "Mo"
    model["response_feedback"] = {"log": [], "lessons": ["Never open with a greeting"]}

    async def fake_get(user_id):
        return model, False

    monkeypatch.setattr(user_model, "get_user_model", fake_get)
    summary = await user_model.summarize_user_for_prompt("user_test")
    assert "LEARNED FROM THEIR FEEDBACK" in summary
    assert "Never open with a greeting" in summary


@pytest.mark.asyncio
async def test_no_lessons_no_injection(monkeypatch):
    model = _fresh_model("user_test")
    model["identity"]["name"] = "Mo"

    async def fake_get(user_id):
        return model, False

    monkeypatch.setattr(user_model, "get_user_model", fake_get)
    summary = await user_model.summarize_user_for_prompt("user_test")
    assert "LEARNED FROM THEIR FEEDBACK" not in summary
