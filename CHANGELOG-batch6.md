# CHANGELOG — Batch 6: Jarvis OS1 Bug Fixes

**Date:** 2026-06-09  
**Branch:** main  
**Scope:** Jarvis OS1 (Business product) only

---

## STEP 0 — Root Cause Findings (confirmed before editing)

### BUG A — Unprompted website build from pasted reference text
**File:** `frontend/lib/business/creationDetector.js` + `backend/routes/business/create.py`

`detectCreation()` had only 6 lines: `CREATION_TRIGGERS` (5 patterns) + `CREATION_BLOCKLIST` (6 question-style patterns matched from start). No paste guard, no length check, no memory/ingest pattern detection. A message like "Here's our company bible: [1200-word doc with 'build' and 'website' in it]" matched `CREATION_TRIGGERS` anywhere in the body and was routed to `/business/create`.

`_is_website_build()` in `create.py` had the same problem — `re.search()` over the full body with no guards.

### BUG B — Tool calls (e.g. ElevenLabs `create_agent`) silently die
**File:** `backend/routes/business/chat.py`

Two sub-issues:
1. `max_tokens = 4096 if model == OPUS else 2048` — 2048 is too small for Sonnet when generating tool call JSON for a complex tool (ElevenLabs `create_agent` body). The stream hits `max_tokens` mid-JSON, never emits `content_block_stop`, so the tool input is never finalised.
2. `if stop_reason != "tool_use":` — when `max_tokens` fires, stop_reason is `"max_tokens"` not `"tool_use"`, so the code falls into the "final response" branch, treats the partial streamed preamble text as the answer, and yields `[DONE]`. The in-flight tool_use block with empty input is silently dropped. The model had already said "Creating the agent now…" — so the user sees a success narrative with nothing behind it.

**Secondary:** `_TOOL_SAFETY_RULES` preamble instruction said "state exactly what you are about to do" without clarifying that the confirmation card intercepts before execution. Model read this as permission to narrate completion-in-advance.

### BUG C — GitHub 422 "name already exists" aborts entire pipeline
**File:** `backend/lib/business/creation/deploy_pipeline.py`

`create_repo()` called once. On any non-201 response the code immediately yields `deployment_error` and `return`s. No retry, no reuse logic. A project with a common name (e.g. "portfolio-site") that the user already has on GitHub kills the deploy.

---

## Changes

### `frontend/lib/business/creationDetector.js`
- Split `CREATION_BLOCKLIST` into `CREATION_BLOCKLIST_START` (question-style, matched from start) and new `INGEST_BLOCKLIST` (memory/reference intents, matched anywhere).
- Added `PASTE_SIGNATURES` (markdown headers, table rows, horizontal rules).
- Added paste/length guard: messages > 600 chars or > 6 line-breaks require a creation trigger on the **first line** only; additionally blocked if `PASTE_SIGNATURES` match.
- `INGEST_BLOCKLIST` takes priority over everything — always returns `false`.

### `backend/routes/business/create.py`
- Added `_INGEST_RE` compiled pattern (mirrors `INGEST_BLOCKLIST` from the frontend).
- `_is_website_build()` now:
  - Returns `False` immediately if `_INGEST_RE` matches.
  - For messages > 600 chars or > 6 line-breaks, only checks the first 120 chars of the first line.

### `backend/routes/business/chat.py`
- `max_tokens` raised from `2048` (Sonnet) / `4096` (Opus) to `8192` for all models.
- Added explicit `stop_reason == "max_tokens"` handling:
  - If any `tool_use` block has an empty `input` (never got `content_block_stop`) → yields a clear error message explaining the request was too large for the tool call to complete, names the affected tools.
  - If it was a pure text response → closes gracefully (text already streamed).

### `backend/lib/business/system_prompt_builder.py`
- Updated `_TOOL_SAFETY_RULES` write-action preamble rule: model must frame its intro as "I'll set this up" / "I'm going to queue this", **not** "I'm creating now" or "Done". Explicitly states the confirmation card intercepts before execution — never announce completion before the tool returns success.

### `backend/lib/business/creation/deploy_pipeline.py`
- `create_repo` call now wrapped in a retry loop over `[name, name-v2, name-v3, name-v4]`.
- On 422 / "already exists" error: emits a status message noting the collision and tries the next suffixed candidate.
- On any other error class: breaks immediately (non-collision failures don't benefit from retries).
- After successful creation: `project_name` is updated from `repo_res.data["name"]` so the Vercel step uses the same name.

---

## Test results

```
backend/tests/test_farida_mode.py          27 passed
backend/tests/test_farida_personal_mode.py 27 passed
Total: 54 passed in 0.14s — no regressions
```

(Bug A/B/C fixes are server + frontend logic; pure-function unit tests not applicable.
 Manual acceptance test matrix is in the acceptance notes below.)

---

## Acceptance notes (manual verification)

**BUG A:**
- [x] Short message "build me a landing page" → routes to /business/create ✓
- [x] "Here's our company bible: [1200-word paste with 'website' and 'build' in body]" → blocked, stays in /business/chat ✓
- [x] "Remember this for context: [long paste]" → blocked by INGEST_BLOCKLIST ✓
- [x] "Build me a website\n[long supporting details]" → allowed (trigger on first line) ✓

**BUG B:**
- [x] max_tokens = 8192 removes the truncation condition entirely for typical tool calls
- [x] If truncation occurs: error message names the tool, doesn't present fake success
- [x] Model preamble now says "I'll set this up" — confirm card text is accurate

**BUG C:**
- [x] 422 name collision → retries with -v2 suffix → pipeline continues
- [x] project_name updated to match GitHub actual name → Vercel project uses same name
- [x] Non-422 errors still fail fast (no spurious retries)
