"""
Regression test for JARVIS-BRAIN-MAP.md Phase 4 (shared Rue Core operating
contract): JARVIS_CORE_CONTRACT must be present in both Personal's and
Business's system prompts, so the ambiguity/clarification and honest-outcome
rules apply identically across both products.
"""
import pytest

from backend.lib.jarvis_core import JARVIS_CORE_CONTRACT


def test_personal_system_prompt_includes_jarvis_core_contract():
    from backend.llm import _build_system_prompt

    static_prompt, _dynamic = _build_system_prompt(
        memory_context="",
        user_model_context="",
        system_override=None,
        tone_context="",
    )
    assert JARVIS_CORE_CONTRACT in static_prompt


@pytest.mark.asyncio
async def test_business_system_prompt_includes_jarvis_core_contract():
    from backend.lib.business.system_prompt_builder import build_system_prompt

    static_prompt, _dynamic, _used_memory_ids = await build_system_prompt("test-phase4-unit", "hello")
    assert JARVIS_CORE_CONTRACT in static_prompt
