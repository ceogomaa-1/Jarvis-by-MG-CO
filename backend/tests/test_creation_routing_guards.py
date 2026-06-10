"""
Regression tests for the Batch 6 creation-routing guards
(`_is_website_build` / `_INGEST_RE` in backend/routes/business/create.py).

Mirrors the manual acceptance notes in CHANGELOG-batch6.md "BUG A":
  - Short creation requests route to /business/create.
  - Long pastes only trigger creation if the trigger is on the first line.
  - Memory/ingest-style messages never trigger creation, regardless of length
    or whether "build"/"website" appear in the body.
"""

from backend.routes.business.create import _is_website_build, _INGEST_RE, _WEBSITE_BUILD_RE


# ─── Short messages — trigger detection ────────────────────────────────────

def test_short_build_request_is_website_build():
    assert _is_website_build("build me a landing page") is True


def test_short_create_site_request_is_website_build():
    assert _is_website_build("Can you create a site for my bakery?") is True


def test_short_non_creation_message_is_not_website_build():
    assert _is_website_build("what's the weather like today?") is False


def test_empty_message_is_not_website_build():
    assert _is_website_build("") is False
    assert _is_website_build(None) is False


# ─── Ingest/memory intents always block, regardless of length ─────────────

def test_remember_this_short_message_is_blocked():
    assert _is_website_build("Remember this: my favorite color is blue") is False


def test_company_bible_paste_is_blocked():
    body_lines = ["We are building a new website for our business division."] * 12
    message = "Here's our company bible: " + " ".join(body_lines)
    assert len(message) > 600
    assert _INGEST_RE.search(message)
    assert _is_website_build(message) is False


def test_remember_this_for_context_long_paste_is_blocked():
    body = "\n".join([f"Background detail line {i} about our company and its products and services."
                       for i in range(10)])
    message = "Remember this for context:\n" + body
    assert message.count("\n") > 6
    assert _is_website_build(message) is False


# ─── Long pastes — only the first line is checked for a trigger ───────────

def test_long_paste_with_build_only_in_body_is_not_website_build():
    first_line = "Here is some background information about our company history and mission."
    body_lines = ["We need a new website built for our business division next quarter."] * 10
    message = first_line + "\n" + "\n".join(body_lines)
    assert message.count("\n") > 6
    assert not _WEBSITE_BUILD_RE.search(first_line)
    assert not _INGEST_RE.search(message)
    assert _is_website_build(message) is False


def test_build_me_a_website_first_line_with_long_body_is_website_build():
    first_line = "Build me a website"
    body_lines = ["Supporting detail line about our products and target audience."] * 10
    message = first_line + "\n" + "\n".join(body_lines)
    assert message.count("\n") > 6
    assert _is_website_build(message) is True
