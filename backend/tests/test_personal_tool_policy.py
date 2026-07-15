"""Personal tool routing must keep companion turns out of agent loops."""
import pytest

from backend.lib.personal.tool_policy import (
    should_offer_personal_tools,
    should_search_personal_documents,
)


FAILED_PRODUCTION_MESSAGE = """I feel like I’m genuinely overwhelmed, overthinking,
locked and depressed. My dad just got retired and I’m almost the only person with
an income for the whole house at 21yo, working 12-13h a day. I need you to be like
an FBI detective with me and help me find the problem stopping me inside."""


@pytest.mark.parametrize(
    "message",
    [
        FAILED_PRODUCTION_MESSAGE,
        "Can I talk with you? I feel depressed right now.",
        "Help me think through why my agency isn't working.",
        "I barely sleep and I've lost weight. I need a real plan.",
        "What do you think I should do with my life?",
    ],
)
def test_companion_conversations_do_not_offer_tools(message):
    assert should_offer_personal_tools(message) is False


@pytest.mark.parametrize(
    "message",
    [
        "What's the time right now?",
        "Show me what's on my calendar tomorrow",
        "Schedule a meeting on my calendar for Friday",
        "Check my inbox for emails from Alex",
        "Send an email to Sarah",
        "Set a timer for 20 minutes",
        "Search the web for the latest AI news",
        "What's the current weather in Toronto?",
        "Save this as a note",
        "Search my uploaded documents for the contract",
    ],
)
def test_explicit_actions_and_live_lookups_offer_tools(message):
    assert should_offer_personal_tools(message) is True


@pytest.mark.parametrize(
    "message",
    [
        FAILED_PRODUCTION_MESSAGE,
        "Can I talk with you about my family?",
        "Help me diagnose why my agency is stuck",
        "What should I do today?",
    ],
)
def test_normal_chat_skips_document_embedding_search(message):
    assert should_search_personal_documents(message) is False


@pytest.mark.parametrize(
    "message",
    [
        "Search my uploaded documents for the contract",
        "What does the PDF I uploaded say about termination?",
        "Find this clause inside my files",
        "According to my documents, when is payment due?",
    ],
)
def test_document_grounded_chat_runs_document_search(message):
    assert should_search_personal_documents(message) is True
