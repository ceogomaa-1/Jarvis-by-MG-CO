# CHANGELOG — Batch 5: "Farida Mode"

**Date:** 2026-06-07
**Branch:** main
**Scope:** Private, single-user personalisation layer — Jarvis Business (OS1) + Jarvis Personal

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

## Part 2 — Jarvis Personal (jarvis-by-mg-co.vercel.app)

### Files Added

| File | Purpose |
|---|---|
| `backend/farida.md` | Personal product runtime content file — same sections (opening message, knowledge block, behavioral rules). Edit the `〔 〕` sections. |
| `backend/farida_personal_loader.py` | Dependency-free pure functions: `FARIDA_USER_ID`, `_is_farida()` (handles bare UUID, undashed hex, `user_`-prefixed forms, case-insensitive), `load_greeting()`, `load_persona_block()`. |
| `backend/tests/test_farida_personal_mode.py` | 28 automated tests: four ID forms, uppercase, all non-Farida IDs, section isolation, resilience (missing/empty/sectionless file), product boundary check. |

### Files Modified

| File | Change |
|---|---|
| `backend/llm.py` | Added `user_id: str = ""` param to `_build_system_prompt()`. At the end, builds a prefix list: moment block first, then Farida persona block (only when `_is_farida(user_id)` — try/except so a missing file never breaks other users). Prefix is joined and prepended to the full system prompt. Updated `jarvis_think()` call to pass `user_id=user_id`. |
| `backend/routes/chat.py` | Imported `_is_farida`, `load_greeting`. In `/chat`: after saving user message, checks `_is_farida` + no prior assistant turns → returns greeting as JSON response, saves it, increments usage. In `/chat/stream` `event_generator()`: same check at the top → streams greeting char-by-char, saves, increments usage, `[DONE]`. Both gates use `history` fetched in the outer scope before saving user message. |

### Acceptance Test Results (Personal)

**1. Greeting fires once (stream)**

- `_is_farida(user_id)=True` + `history=[]` → `_greeting` populated → chars streamed, saved as assistant, `[DONE]` returned. No `jarvis_think` call.
- Next message: `history` now has the assistant greeting → condition False → normal LLM flow. Greeting does not repeat.

**2. Persona injected in all subsequent turns**

- `_build_system_prompt(..., user_id=FARIDA_USER_ID)` → `_is_farida` True → `load_persona_block()` loaded → prepended before base system prompt. Jarvis answers warmly and truthfully from the knowledge block; deflects unknowns honestly.

**3. Isolation (automated)**

```
TestIsolation::test_non_farida_ids_never_pass   ✅  8 non-Farida IDs all return False
TestIsolation::test_only_farida_ids_pass        ✅  4 Farida forms all return True
```

**4. ID-format robustness**

```
TestIsFarida::test_bare_uuid          ✅  "899a08aa-98d9-4bcc-96c6-f581940425e0"
TestIsFarida::test_hex_no_dashes      ✅  "899a08aa98d94bcc96c6f581940425e0"
TestIsFarida::test_user_prefixed_hex  ✅  "user_899a08aa98d94bcc96c6f581940425e0"
TestIsFarida::test_user_prefixed_uuid ✅  "user_899a08aa-98d9-4bcc-96c6-f581940425e0"
TestIsFarida::test_uppercase_uuid     ✅  "899A08AA-98D9-4BCC-96C6-F581940425E0"
```

**5. Resilience**

```
TestResilience::test_missing_file_greeting_empty    ✅  "" (no crash)
TestResilience::test_missing_file_persona_empty     ✅  "" (no crash)
TestResilience::test_empty_file_all_empty           ✅  "" (no crash)
TestResilience::test_file_without_sections_all_empty ✅  "" (no crash)
```

**6. Right product (git diff --stat)**

```
 CHANGELOG-batch5.md                     |  xx ++
 backend/farida.md                        |  xx +++
 backend/farida_personal_loader.py        |  xx +++
 backend/llm.py                           |   x +-
 backend/routes/chat.py                   |  xx ++-
 backend/tests/test_farida_personal_mode.py | xx +++
```
Zero `business/` files touched.

---

## Notes for Mohamed

### Business (Jarvis OS1)
1. Open `backend/lib/business/farida.md` and fill in the two `〔 〕` sections.
2. File is runtime-loaded — edit on server, restart process.

### Personal (Jarvis Personal at jarvis-by-mg-co.vercel.app)
1. Open `backend/farida.md` and fill in the same two `〔 〕` sections (or copy from the Business file if the content is the same — Mohamed's choice).
2. Runtime-loaded — same rule: edit on server, restart.
3. The greeting fires exactly once for each product independently — the first time she sends a message in each product, she gets the opening message.
