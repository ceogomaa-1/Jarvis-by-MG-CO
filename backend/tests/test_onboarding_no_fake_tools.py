"""
Regression test for a Phase 5 finding (JARVIS-BRAIN-MAP.md): a brand-new user
in onboarding gets system_override set and tools suppressed
(backend/routes/chat.py: `tools = AVAILABLE_TOOLS if not system_override else None`).
Without an explicit warning, the model hallucinated raw <function_calls> XML
and claimed "Reminder set" / "Noted" when no tool ever ran. The active
onboarding prompts (identity/goals/personality) must tell the model it has no
tools this turn; the "complete" prompt must not, since tools are active again.
"""
from backend.user_model import _NO_TOOLS_REMINDER, _ONBOARDING_SYSTEM_PROMPTS


def test_active_onboarding_prompts_warn_no_tools_available():
    for key in ("identity", "goals", "personality"):
        assert _NO_TOOLS_REMINDER in _ONBOARDING_SYSTEM_PROMPTS[key]


def test_complete_onboarding_prompt_does_not_warn_no_tools():
    assert _NO_TOOLS_REMINDER not in _ONBOARDING_SYSTEM_PROMPTS["complete"]
