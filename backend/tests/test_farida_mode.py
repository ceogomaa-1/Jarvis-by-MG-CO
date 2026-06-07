"""
Tests for Farida mode — isolation, ID-format robustness, section parsing, resilience.

All imports come from backend.lib.business.farida_loader, which has zero
external dependencies, so these tests run anywhere Python 3.10+ is available.

Run with:  pytest backend/tests/test_farida_mode.py -v
"""

import os
import sys
import pytest

# Ensure repo root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.lib.business.farida_loader import (
    FARIDA_USER_ID,
    user_id_to_uuid,
    is_farida,
    load_greeting,
    load_persona_block,
    _FARIDA_MD,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
FARIDA_UUID = "899a08aa-98d9-4bcc-96c6-f581940425e0"
FARIDA_HEX = "user_" + FARIDA_UUID.replace("-", "")  # user_-prefixed hex form
OTHER_UUID = "00000000-0000-0000-0000-000000000099"
ANOTHER_UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


# ---------------------------------------------------------------------------
# 1. FARIDA_USER_ID constant is correct
# ---------------------------------------------------------------------------
def test_constant_value():
    assert FARIDA_USER_ID == FARIDA_UUID


# ---------------------------------------------------------------------------
# 2. ID normalisation — both formats resolve to the same UUID
# ---------------------------------------------------------------------------
class TestUserIdToUuid:
    def test_bare_uuid_passthrough(self):
        assert user_id_to_uuid(FARIDA_UUID) == FARIDA_UUID

    def test_hex_prefix_converted(self):
        assert user_id_to_uuid(FARIDA_HEX) == FARIDA_UUID

    def test_bare_uuid_matches_constant(self):
        assert user_id_to_uuid(FARIDA_UUID) == FARIDA_USER_ID

    def test_prefixed_hex_matches_constant(self):
        assert user_id_to_uuid(FARIDA_HEX) == FARIDA_USER_ID

    def test_other_uuid_does_not_match(self):
        assert user_id_to_uuid(OTHER_UUID) != FARIDA_USER_ID

    def test_another_uuid_does_not_match(self):
        assert user_id_to_uuid(ANOTHER_UUID) != FARIDA_USER_ID

    def test_arbitrary_hex_prefix_does_not_match(self):
        assert user_id_to_uuid("user_" + "0" * 32) != FARIDA_USER_ID


# ---------------------------------------------------------------------------
# 3. is_farida helper
# ---------------------------------------------------------------------------
class TestIsFarida:
    def test_bare_uuid_true(self):
        assert is_farida(FARIDA_UUID) is True

    def test_hex_form_true(self):
        assert is_farida(FARIDA_HEX) is True

    def test_other_uuid_false(self):
        assert is_farida(OTHER_UUID) is False

    def test_another_uuid_false(self):
        assert is_farida(ANOTHER_UUID) is False

    def test_empty_string_false(self):
        assert is_farida("") is False

    def test_random_hex_prefix_false(self):
        assert is_farida("user_" + "a" * 32) is False


# ---------------------------------------------------------------------------
# 4. farida.md section loading (requires the real file to exist)
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not os.path.exists(_FARIDA_MD), reason="farida.md not present")
class TestFaridaLoader:
    def test_greeting_non_empty(self):
        g = load_greeting()
        assert g, "Greeting must not be empty"

    def test_greeting_mentions_mohamed(self):
        assert "Mohamed" in load_greeting()

    def test_greeting_contains_hi(self):
        assert "Hi" in load_greeting() or "Farida" in load_greeting()

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

    def test_greeting_and_persona_are_distinct(self):
        g = load_greeting()
        b = load_persona_block()
        # They should not be identical
        assert g != b


# ---------------------------------------------------------------------------
# 5. Resilience — missing file returns empty strings, never crashes
# ---------------------------------------------------------------------------
class TestResilience:
    def test_missing_file_greeting_returns_empty(self, tmp_path):
        result = load_greeting(md_path=str(tmp_path / "nonexistent.md"))
        assert result == ""

    def test_missing_file_persona_returns_empty(self, tmp_path):
        result = load_persona_block(md_path=str(tmp_path / "nonexistent.md"))
        assert result == ""

    def test_empty_file_returns_empty(self, tmp_path):
        f = tmp_path / "empty.md"
        f.write_text("")
        assert load_greeting(md_path=str(f)) == ""
        assert load_persona_block(md_path=str(f)) == ""


# ---------------------------------------------------------------------------
# 6. Isolation assertion — non-Farida IDs must not match
# ---------------------------------------------------------------------------
class TestIsolation:
    _NON_FARIDA = [
        OTHER_UUID,
        ANOTHER_UUID,
        "user_" + "0" * 32,
        "user_" + "f" * 32,
        "",
        "not-a-uuid",
    ]

    def test_non_farida_ids_never_match(self):
        for uid in self._NON_FARIDA:
            assert not is_farida(uid), f"is_farida returned True for non-Farida id: {uid!r}"

    def test_only_farida_id_matches(self):
        """Prove the gate is exact: only the two forms of Farida's real ID pass."""
        assert is_farida(FARIDA_UUID)
        assert is_farida(FARIDA_HEX)
        for uid in self._NON_FARIDA:
            assert not is_farida(uid)
