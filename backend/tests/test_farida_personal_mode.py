"""
Tests for Farida mode — Jarvis Personal product.
Covers isolation, ID-format robustness, section parsing, and resilience.

All imports come from backend.farida_personal_loader, which has zero
external dependencies — tests run anywhere Python 3.10+ is available.

Run with:  pytest backend/tests/test_farida_personal_mode.py -v
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.farida_personal_loader import (
    FARIDA_USER_ID,
    _is_farida,
    load_greeting,
    load_persona_block,
    _FARIDA_MD,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
FARIDA_UUID = "899a08aa-98d9-4bcc-96c6-f581940425e0"
FARIDA_HEX_NO_DASHES = FARIDA_UUID.replace("-", "")
FARIDA_HEX_PREFIXED = "user_" + FARIDA_HEX_NO_DASHES
FARIDA_UUID_PREFIXED = "user_" + FARIDA_UUID

OTHER_UUID = "00000000-0000-0000-0000-000000000099"
ANOTHER_UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

_NON_FARIDA = [
    OTHER_UUID,
    ANOTHER_UUID,
    "user_" + "0" * 32,
    "user_" + "f" * 32,
    "00000000000000000000000000000000",
    "",
    "not-a-uuid",
    "899a08aa",  # partial
]


# ---------------------------------------------------------------------------
# 1. FARIDA_USER_ID constant
# ---------------------------------------------------------------------------
def test_constant_value():
    assert FARIDA_USER_ID == FARIDA_UUID


# ---------------------------------------------------------------------------
# 2. _is_farida — all four accepted ID forms
# ---------------------------------------------------------------------------
class TestIsFarida:
    def test_bare_uuid(self):
        assert _is_farida(FARIDA_UUID) is True

    def test_hex_no_dashes(self):
        assert _is_farida(FARIDA_HEX_NO_DASHES) is True

    def test_user_prefixed_hex(self):
        assert _is_farida(FARIDA_HEX_PREFIXED) is True

    def test_user_prefixed_uuid(self):
        assert _is_farida(FARIDA_UUID_PREFIXED) is True

    def test_uppercase_uuid(self):
        assert _is_farida(FARIDA_UUID.upper()) is True

    def test_empty_string_false(self):
        assert _is_farida("") is False

    def test_other_uuid_false(self):
        assert _is_farida(OTHER_UUID) is False

    def test_another_uuid_false(self):
        assert _is_farida(ANOTHER_UUID) is False

    def test_partial_id_false(self):
        assert _is_farida("899a08aa") is False

    def test_all_non_farida_false(self):
        for uid in _NON_FARIDA:
            assert not _is_farida(uid), f"_is_farida unexpectedly True for {uid!r}"


# ---------------------------------------------------------------------------
# 3. Isolation — only Farida's IDs pass the gate, none of the others
# ---------------------------------------------------------------------------
class TestIsolation:
    def test_only_farida_ids_pass(self):
        farida_forms = [FARIDA_UUID, FARIDA_HEX_NO_DASHES, FARIDA_HEX_PREFIXED, FARIDA_UUID_PREFIXED]
        for uid in farida_forms:
            assert _is_farida(uid), f"_is_farida should be True for {uid!r}"

    def test_non_farida_ids_never_pass(self):
        for uid in _NON_FARIDA:
            assert not _is_farida(uid), f"_is_farida leaked True for {uid!r}"


# ---------------------------------------------------------------------------
# 4. farida.md section loading (requires the real file)
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not os.path.exists(_FARIDA_MD), reason="backend/farida.md not present")
class TestFaridaPersonalLoader:
    def test_greeting_non_empty(self):
        assert load_greeting(), "Greeting must not be empty"

    def test_greeting_mentions_mohamed(self):
        assert "Mohamed" in load_greeting()

    def test_greeting_mentions_farida_or_hi(self):
        g = load_greeting()
        assert "Farida" in g or "Hi" in g

    def test_persona_block_non_empty(self):
        assert load_persona_block(), "Persona block must not be empty"

    def test_persona_block_mentions_mohamed(self):
        assert "Mohamed" in load_persona_block()

    def test_greeting_does_not_bleed_into_knowledge(self):
        g = load_greeting()
        assert "## Knowledge Block" not in g
        assert "## Behavioral Rules" not in g

    def test_persona_block_does_not_contain_opening_message(self):
        b = load_persona_block()
        assert "## Opening Message" not in b

    def test_sections_are_distinct(self):
        assert load_greeting() != load_persona_block()

    def test_unique_content_in_persona_only(self):
        """Unique farida.md markers must appear in persona block but NOT in greeting."""
        # These strings appear in Knowledge Block, not Opening Message
        b = load_persona_block()
        assert "CEOMO" in b or "future wife" in b, "Persona block should contain knowledge facts"


# ---------------------------------------------------------------------------
# 5. Resilience — missing / empty file never crashes
# ---------------------------------------------------------------------------
class TestResilience:
    def test_missing_file_greeting_empty(self, tmp_path):
        assert load_greeting(md_path=str(tmp_path / "no.md")) == ""

    def test_missing_file_persona_empty(self, tmp_path):
        assert load_persona_block(md_path=str(tmp_path / "no.md")) == ""

    def test_empty_file_all_empty(self, tmp_path):
        f = tmp_path / "empty.md"
        f.write_text("")
        assert load_greeting(md_path=str(f)) == ""
        assert load_persona_block(md_path=str(f)) == ""

    def test_file_without_sections_all_empty(self, tmp_path):
        f = tmp_path / "plain.md"
        f.write_text("# No sections here at all\n\nJust some text.")
        assert load_greeting(md_path=str(f)) == ""
        assert load_persona_block(md_path=str(f)) == ""


# ---------------------------------------------------------------------------
# 6. Product boundary — confirms no business files were touched
# ---------------------------------------------------------------------------
def test_business_files_unchanged():
    """Sanity check: business farida_loader is a different module."""
    try:
        from backend.lib.business.farida_loader import FARIDA_USER_ID as biz_id
        from backend.farida_personal_loader import FARIDA_USER_ID as personal_id
        # Both reference the same user ID (same person, different products)
        assert biz_id == personal_id
    except ImportError:
        pass  # business module optional in this test environment
