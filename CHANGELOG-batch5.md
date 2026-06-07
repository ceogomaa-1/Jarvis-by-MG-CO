# CHANGELOG — Batch 5: "Farida Mode"

**Date:** 2026-06-07
**Branch:** main
**Scope:** Private, single-user personalisation layer for Jarvis OS1 (Business product)

---

## What Was Built

A silent, isolated personalisation layer that activates exclusively for one specific user. All other users are completely unaffected.

### Files Added

| File | Purpose |
|---|---|
| `backend/lib/business/farida.md` | Runtime content file: opening message, Mohamed knowledge block, behavioral rules. Edit the `〔 〕` sections to fill in personal details. |
| `backend/tests/test_farida_mode.py` | Automated tests covering: ID-format normalisation, persona injection, isolation, resilience when file is missing. |
| `CHANGELOG-batch5.md` | This file. |

### Files Modified

| File | Change |
|---|---|
| `backend/lib/business/system_prompt_builder.py` | Added `FARIDA_USER_ID` constant, `_farida_section()` parser, `_load_farida_greeting()`, `_load_farida_persona_block()`. Modified `build_system_prompt()` to prepend the knowledge + rules block when (and only when) the normalised user ID matches. |
| `backend/routes/business/chat.py` | Imported `FARIDA_USER_ID` and `_load_farida_greeting`. Added pre-setup check that detects Farida's first-ever conversation (zero rows in `business_conversations` before setup). In `generate()`, intercepts the response stream and delivers the exact opening message from `farida.md`, saves it to DB, and returns — no Anthropic API call on that first turn. |

---

## Acceptance Test Results

### 1. Greeting fires once

- First message with `user_id = 899a08aa-98d9-4bcc-96c6-f581940425e0` and no prior `business_conversations` rows → `farida_greeting` is populated from `farida.md` → message is streamed verbatim, saved as assistant message, `[DONE]` emitted. Anthropic API is **not** called.
- Second message in same conversation → `conv_id` is now set (non-null) → `farida_greeting = ""` → normal Anthropic flow runs. Greeting does **not** repeat.
- Second conversation (rows now exist) → check finds existing rows → `farida_greeting = ""` → normal flow.

### 2. Persona + truthful Q&A

- Farida's system prompt contains the knowledge block from `farida.md` (Mohamed facts, behavioral rules).
- Model is instructed to answer from that block only and deflect with `"Mohamed didn't tell me that one — you'll have to ask him 🤍"` for anything not covered.
- No fabricated facts — honesty gate is in the behavioral rules.

### 3. Isolation (automated — `test_farida_mode.py`)

```
test_other_user_system_prompt_has_no_farida_content
  - "future wife" not in prompt for 00000000-0000-0000-0000-000000000099  ✅
  - "CEOMO"       not in prompt for 00000000-0000-0000-0000-000000000099  ✅
  - "future wife" not in prompt for aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee ✅
  - "CEOMO"       not in prompt for user_0000000000000000000000000000ffff ✅
```

### 4. ID-format robustness

```
test_bare_uuid_matches_constant     ✅  _user_id_to_uuid("899a08aa-...")  == FARIDA_USER_ID
test_prefixed_hex_matches_constant  ✅  _user_id_to_uuid("user_899a08aa98d94bcc...")  == FARIDA_USER_ID
test_hex_id_also_gets_farida_content ✅  build_system_prompt(FARIDA_HEX) contains "Mohamed"
```

### 5. Resilience

```
test_resilience_missing_file  ✅  _load_farida_greeting() == ""  (no crash)
                               ✅  _load_farida_persona_block() == ""  (no crash)
Normal users unaffected.       ✅  (farida_block="" → prompt unchanged)
```

---

## Notes for Mohamed

1. Open `backend/lib/business/farida.md` and fill in the two `〔 〕` sections:
   - **In the opening message:** Write the personal lines only you can write — what you love about her, a real moment, what you promise.
   - **In the knowledge block:** Add any additional true facts (how you met, dates, her favorites) so Jarvis can answer truthfully if she asks.
2. The file is runtime-loaded — no redeploy needed after editing it on the server. On Vercel/containerised environments, update the file and restart the server process.
3. The greeting fires exactly once: the very first time she opens Jarvis and sends any message. After that, Jarvis behaves as her full business assistant with the warm Mohamed persona baked into every conversation.
