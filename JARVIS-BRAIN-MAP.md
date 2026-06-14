# JARVIS BRAIN STABILIZATION — Phase 0 Map

**Date:** 2026-06-14
**Scope:** Intent routing, fact-grounding, and fake-success/honesty across Jarvis Personal (`/`) and Jarvis OS1 Business (`/business/chat`).
**Relationship to `STABILITY-AUDIT.md` (Batch 42):** that audit covers error-handling/crash/latency defects (21 items, mostly infra). This map is narrower and behavioral: *does Jarvis correctly understand what the user wants, does it ever invent facts, and does it ever claim success when nothing happened*. No overlap items are re-litigated here except where they directly cause a routing/honesty bug.

This is the contract for the rest of the batch. Phases 1–5 implement against this map.

---

## A. Intent-Routing Inventory

### A1. Business — frontend 4-layer cascade (`ChatCanvas.js`, THE Phase 1 target)

Order of evaluation per user message (when `!hasAttachments`):

1. **`isAgentEdit`** (`frontend/lib/business/agentEditDetector.js`)
   - `activeAgentId = findActiveAgentId(messages)` — scans messages in reverse for `m.agent_id` or an `agent_[a-zA-Z0-9]{10,}` regex match in assistant text.
   - `isAgentModificationRequest(text)` — regex for verbs like adjust/change/tweak/edit/fix + nouns like greeting/voice/prompt/persona, minus a `NEW_AGENT_OVERRIDE` ("new/another/second agent").
   - If both true → **skip walkthrough/creation entirely**, fall through to regular chat (so `update_agent` tool can fire).

2. **`detectShowMeHow`** (`frontend/lib/business/showMeHowDetector.js`)
   - BLOCKLIST (what/which/why/should/tell me/explain) wins → false.
   - TRIGGERS: "how to", "how do i", "step by step", "walk me through", etc. → true.
   - If true → POST `/api/business/show-me-how` (SSE walkthrough).

3. **`detectCreation` || `isDeployConfirmation`** (`frontend/lib/business/creationDetector.js` + inline `ChatCanvas.js:51`)
   - `detectCreation`: INGEST_BLOCKLIST (remember/save this/memorize) wins → false. CREATION_BLOCKLIST_START (what/which/should i/how do i/how to) → false. Long paste (>600 chars or >6 newlines): only first line checked against CREATION_TRIGGERS, then PASTE_SIGNATURES (markdown headers/tables/`---`) block even a first-line match. Short message: CREATION_TRIGGERS (build/create/generate + campaign/landing page/agent/etc.) anywhere → true.
   - `isDeployConfirmation`: message is a bare "yes/ok/go ahead/ship it/deploy it/..." AND one of the last 8 assistant messages mentions deploy/GitHub+Vercel/live URL language.
   - If either true → POST `/api/business/create` (SSE creation pipeline).

4. **Fallback** → regular chat: builds `history`, POST `/api/business/chat/stream`.

**Failure modes this produces** (the actual bugs the regression tests target):
- "Adjust the agent's greeting to sound more human" → `isAgentEdit` *should* catch this via `MODIFICATION_TRIGGERS` (greeting + adjust) — but only if `activeAgentId` is non-null, i.e. only if a prior assistant message contained an `agent_...` ID. If the agent was created in an earlier session (not in current `messages` array, e.g. after a page reload or in a fresh conversation), `findActiveAgentId` returns null → `isAgentEdit=false` → falls to `detectShowMeHow` ("how"-less, probably false) → `detectCreation` ("adjust... sound more human" doesn't match CREATION_TRIGGERS, probably false) → lands in regular chat anyway, which is *correct by accident*, not by design. But if the phrasing drifts ("can you regenerate the agent's greeting") it could trip `detectCreation`'s "generate" trigger → misrouted to the Creation canvas instead of `update_agent`.
- Any of these detectors firing on a message that should go to chat (or vice versa) is a silent misroute — no error, just the wrong UI surface and the wrong backend tool offered.

### A2. Business — backend prompt-section classifier (`backend/lib/business/intent_classifier.py`)

A **5th, unrelated** classification layer: `classify_intent(user_message) -> list[str]` picks which Farida/business-bible *prompt sections* (operations/problems/metrics/risk_flags/mindset/daily_ops/moves) get injected into the system prompt for `business/chat.py`. Keyword-matching first; Haiku fallback (sync `httpx.post`, flagged as audit defect #1 — blocking call, NOT fixed here unless Phase 1's new router subsumes it). **Out of scope for Phase 1's routing fix** — this is content selection, not action routing — but Phase 1 should avoid adding a *second* synchronous Haiku call on the same turn; if the new `classify_intent` (action router) already calls Haiku/Sonnet async, consider whether this module's Haiku fallback can be merged or at least made async in passing.

### A3. Business — backend creation-routing guards (already fixed, Batch 6, confirmed present)

`backend/lib/business/creation/intent_detector.py::detect_creation()` — **dead code**, zero live callers (confirmed via grep — only self-reference and `STABILITY-AUDIT.md` mention it). Lacks the Batch 6 paste/ingest guards present in `creationDetector.js`. Not wired into `create.py` or `chat.py`. **Action: delete in Phase 1** (latent trap per audit #21) once the new router replaces the frontend detectors it would otherwise duplicate.

### A4. Personal — single-endpoint, no creation/walkthrough split

`/api/chat/stream` → `jarvis_think()` with `available_tools` always set (all registry + legacy tools offered every turn, per `LLM_ONBOARDING_GATE` log). No frontend regex routing exists for Personal — everything is one chat turn with native Anthropic tool-use. The "routing" problems on Personal are at the **tool-selection / clarification** level, not the **flow-selection** level:

- **Reminder save backstop** (`backend/agent.py:341-342,642`): `_REMINDER_TRIGGER_RE` (remind/remember to/alert me/ping me) + `_TIME_HINT_RE` (time-like phrase). If `save_note()` is called with a message that looks like a reminder trigger + time hint but the model didn't pass `remind_at_iso`, this is a backstop — exact behavior needs confirming in Phase 3 (does it refuse and ask, or silently save without a time?).
- **Ambiguous "remember the thing we talked about"** — no explicit detector; relies entirely on the model's judgment per `_BASE_SYSTEM_PROMPT`'s tool-use section (no explicit "ask which thing" instruction exists today). This is a **Phase 3 gap** (clarify-vs-guess).
- **`jarvis_think()` single-pass tool loop** (audit #10): a 2nd round of `tool_use` after the first tool result is dropped — only text (possibly empty → `_FALLBACK_EMPTY`) survives. Relevant to Phase 3 if a chained action (e.g., "check my calendar then create an event for the gap") needs 2 tool rounds — currently silently truncates to round 1.

### A5. Routing decision-point summary table

| # | Decision point | File | Mechanism | Risk |
|---|---|---|---|---|
| 1 | Agent-edit vs everything else | `agentEditDetector.js` | regex + last-N-messages agent_id scan | context lost across sessions/reloads |
| 2 | Show-me-how vs not | `showMeHowDetector.js` | regex blocklist+triggers | "how" in a creation request ("how do I get a website like X built") misroutes |
| 3 | Creation vs chat | `creationDetector.js` | regex blocklist+triggers+paste-guard | verb drift (generate/build/make on edits) |
| 4 | Deploy-confirmation | `ChatCanvas.js:51 isDeployConfirmation` | regex on bare "yes/ok" + last-8-assistant-msg scan | any other pending yes/no question in last 8 msgs (e.g. "want me to also send the SMS?") gets misread as deploy confirmation |
| 5 | Prompt-section selection | `intent_classifier.py` | keyword + sync Haiku fallback | wrong section = Jarvis lacks context to answer well (not a routing crash, a quality issue) |
| 6 | Personal reminder-save | `agent.py` regex backstop | regex | unclear ask-vs-guess behavior (Phase 3) |
| 7 | Personal tool loop depth | `llm.py jarvis_think` | hardcoded 1 round | chained actions truncate silently |

---

## B. Fact-Assertion / Grounding Inventory

Where Jarvis (either product) could state something as fact without it being grounded in real data:

| # | Location | What could be invented | Existing mitigation |
|---|---|---|---|
| B1 | `backend/lib/business/creation/sub_agents.py` (strategist/copywriter/designer/researcher/analyst/reporter, Sonnet-4-6) | Business facts (founding year, team size, locations, pricing) when generating site copy/agent prompts for a real business | None confirmed — `_VOICE_AGENT_STYLE_GUIDE` (ElevenLabs persona prompts only) says "never invent facts... don't invent 'since 1964'" but this is narrow to ElevenLabs voice-agent system prompts, not site copy generally |
| B2 | `backend/lib/business/web_scrape.py` (`execute_web_tool`, "web" connector) | If scrape fails/returns empty, does the model still write copy as if it had read the site? | Need to confirm: does a failed/empty scrape result get surfaced as `{"error": ...}` to the model (good) or as empty success (bad)? |
| B3 | `backend/llm.py _BASE_SYSTEM_PROMPT` (Personal) | General hallucination on factual claims; date/time ("You know the current date and time") — mitigated by `get_current_moment_block` | Moment block is real-time-injected — good precedent |
| B4 | `backend/user_model.py summarize_user_for_prompt` | Profile facts (goals, role, company) — these ARE grounded (Supabase-backed), but if `get_user_model` fails it silently returns `_fresh_model()` (empty) → Jarvis might then ask "what's your dream job?" as if new, contradicting earlier conversation. Not invention, but a *forgetting* failure mode adjacent to grounding. |
| B5 | `backend/memory.py get_relevant_memories` | Mem0 RateLimitError → returns `""` silently (logged only). If memory context is empty because of a 429 (not because there's nothing relevant), Jarvis has no signal to distinguish "user never told me" from "Mem0 is rate-limited right now" — could answer "I don't know that" when it actually does know, stored in Mem0, just inaccessible this turn. |
| B6 | `backend/lib/business/system_prompt_builder.py` (Farida/business-bible sections) | If `intent_classifier` picks wrong sections (A2), the model answers from whatever sections it loaded — could present generic "mindset" advice as if it were business-specific fact |
| B7 | Walkthrough generator (`show_me_how.py` / `walkthrough_generator.py`) | Step-by-step instructions for tools/connectors the user hasn't connected — does it check connection status before claiming "click X in your Stripe dashboard"? |
| B8 | Creation pipeline `site_generator.py` | `generate_site()` always returns a valid dict (good — no crash), but `_fallback_site()` is a **generic** Next.js site — if research/scrape failed, does the user get told "I built a generic placeholder because I couldn't find info about your business" or does it present as if tailored? |

**Phase 2 target**: a shared "grounding contract" — a system-prompt block (or tool-result-shaped instruction) that says: (1) only state facts that come from tool results, user messages, memory, or the user model; (2) if a scrape/search/lookup failed or returned nothing, say so explicitly and either ask or proceed with an explicitly-labeled placeholder/generic version; (3) never backfill specifics (years, numbers, names) that weren't actually retrieved.

---

## C. Fake-Success / Fake-Done Inventory

| # | Location | Current behavior | Verdict |
|---|---|---|---|
| C1 | `backend/lib/business/tool_executor.py` | Every connector path: success → real `result.data`; failure → `{"error": result.error}`; exception → `{"error": "Tool execution error: {e}"}`; not-connected → `{"error": "Not connected to X..."}`. Falls through to `Unknown action` error for unmapped `(connector_type, action_name)`. | ✅ Solid — no silent success. Model receives real data or a real error string every time. |
| C2 | `backend/routes/business/chat.py` tool loop | Per `STABILITY-AUDIT.md` §4: all `stop_reason` paths handled; `max_tokens` truncation mid-tool-call → explicit error naming the tool (Batch 6); write actions gated behind `pending_action` → `/confirm-action`. | ✅ Solid |
| C3 | `/business/chat/confirm-action` | Haiku-generated confirmation text with explicit instruction: "if [error] key present, say FAILED; otherwise quote the REAL result"; `_make_fallback_confirmation()` regex fallback if Haiku call fails. | ✅ Good precedent — but verify the fallback regex doesn't default to an optimistic "Done!" when `tool_result` actually contains an error key (Phase 3 must test this path explicitly). |
| C4 | `backend/agent.py save_note()` | Returns a real DB-backed `note_id` from Supabase. | ✅ Real |
| C5 | `backend/user_model.py update_user_model` | If Claude's JSON-extraction step throws, exception is caught and **swallowed** — `save_result` still returns `True` for the overall function (interaction count + emotional signal still saved) even though the profile-fact extraction silently did nothing this turn. Not user-visible (no claim is made to the user about profile updates), so not a *fake-success-to-user* bug — but worth noting for Phase 3's "real result reporting" framing if this function's return value is ever surfaced. | ⚠️ Internal-only, low priority |
| C6 | `backend/routes/proactive_routes.py /api/proactive/check/{user_id}` (audit #2) | `jarvis_think` call has no try/except; note marked done only *after* success → Anthropic hiccup = perpetual 500 + reminder stuck "due" forever, OR (if it succeeds) the user-visible delivered reminder text — need to confirm: if `jarvis_think` throws, does the user ever see a "reminder delivered" claim that didn't happen? Audit says no claim is made (raw 500), so not fake-success per se, but **silently broken** reminders is adjacent — Phase 3 should add the try/except regardless. | ⚠️ Infra bug, Phase 3 should patch as part of "reminders actually work" |
| C7 | `backend/lib/business/creation/deploy_pipeline.py` | Per audit: 422-retry confirmed, ends in `deployment_pending` (not a false "live" claim) — but `GET /business/deploy-status` (audit #7) reports `{"state":"BUILDING"}` even when the underlying Vercel call itself failed (`ok=False`). **This IS a fake-in-progress signal** — user sees "still building" indefinitely for a connector failure that already happened. | 🔴 Real bug — Phase 3 candidate |
| C8 | ElevenLabs agent create/update (`tool_executor.py` → `elevenlabs_conn.py`) | `ConnectorResult(ok=False)` on `raise_for_status` — propagates as `{"error": ...}`. Confirm-action then must say FAILED (C3). | ✅ Likely solid, verify in Phase 3 live test |

**Phase 3 targets**: C6 (proactive reminder try/except + don't mark done until delivery confirmed) and C7 (deploy-status must distinguish "still building" from "connector call failed") are the concrete fixes. C3's fallback path needs a live regression test.

---

## D. Regression Test List (from original spec — verbatim scenarios)

These are the acceptance tests Phase 5 must encode + Phases 1–4 must pass manually as they land:

1. **"Adjust the agent's greeting to sound more human"** (with an agent created earlier in conversation) → must route to `update_agent` tool call (chat flow), NOT the Show-Me-How walkthrough, NOT the Creation canvas.
2. **Restaurant URL + "build an agent for this restaurant"** → Jarvis must use only facts actually scraped from the URL; if scrape fails/returns nothing, Jarvis must say so and either ask for details or build a clearly-generic placeholder — never invent menu items, founding years, addresses, etc.
3. **"What's my dream job?"** (after onboarding/profile seeded with this info) → Jarvis answers from the seeded user-model/Mem0 profile, not "I don't know" / not a generic deflection.
4. **"Remind me in 1 min"** → real reminder saved with correct `remind_at_iso` (~60s from now in user's tz), delivered via the live in-app mechanism.
5. **"Note this down: [content]"** → saved as a plain note (no remind_at) without asking unnecessary clarifying questions.
6. **Ambiguous "remember the thing we talked about"** (no clear referent) → Jarvis asks a one-line clarifying question (which thing?) rather than guessing/saving nonsense or silently doing nothing.
7. **Tool failure** (e.g., connector not connected, API error) → Jarvis reports the real failure honestly ("I couldn't do X because Y — connect Z in Settings" / "the API returned an error"), never claims success.

---

## E. Phase 1 Architecture Decision

Replace the Business 4-layer frontend regex cascade (A1) with **one backend intent-classification call** that the frontend awaits before choosing a flow:

- New module: `backend/lib/business/intent_router.py` — `async def classify_message_intent(message, *, active_agent_id, recent_assistant_texts, has_attachments) -> dict`
  - Returns `{"intent": "chat" | "edit_agent" | "show_me_how" | "create" | "deploy_confirm", "reason": str}`
  - Single async Anthropic Haiku call (non-blocking — fixes the spirit of audit #1 by *not adding a second sync call*; A2's existing sync Haiku fallback is left alone for now, out of scope).
  - Deterministic short-circuits BEFORE calling Haiku (cheap, unambiguous, no model needed):
    - `has_attachments` → always `chat` (existing behavior preserved).
    - Empty/whitespace message → `chat`.
  - Everything else → one Haiku call with full context (message, active_agent_id present/absent, last 1-2 assistant messages for deploy-offer detection, INGEST/paste heuristics folded into the prompt instructions rather than separate regex).
- New route: `POST /business/classify-intent` in `backend/routes/business/chat.py`.
- Frontend: `ChatCanvas.js` replaces the `isAgentEdit`/`detectShowMeHow`/`detectCreation`/`isDeployConfirmation` cascade (lines ~650-827) with one `await classifyIntent(...)` call, switches on `.intent`.
- Delete: `creationDetector.js`, `showMeHowDetector.js`, `agentEditDetector.js`, `backend/lib/business/creation/intent_detector.py` (dead code, A3) once the new path is verified working end-to-end.
- Personal (A4): no flow-routing change in Phase 1 (single endpoint already). Phase 3/4 will address the clarify-vs-guess and tool-loop-depth items.

---

## F. Phase 1 — Completion Report

**Status: DONE. Implemented, deployed to local server, verified live, regression-tested, committed.**

### What changed
- New `backend/lib/business/intent_router.py` — `classify_message_intent()`. Deterministic short-circuits for `has_attachments`/empty message/no API key; otherwise a single async Haiku (`claude-haiku-4-5-20251001`) call returning `{"intent": "chat"|"show_me_how"|"create", "reason": str}`. Final taxonomy is 3-way (not the 5-way sketched in §E — `edit_agent` and `deploy_confirm` collapsed into `chat`/`create` respectively via the CRITICAL RULES, which is simpler and covers the same cases).
- New route `POST /api/business/classify-intent` in `backend/routes/business/chat.py`.
- `ChatCanvas.js`: replaced the entire `isAgentEdit` / `detectShowMeHow` / `detectCreation` / `isDeployConfirmation` cascade with one `await fetch('/api/business/classify-intent', ...)` call, switching on `.intent`.
- `agentEditDetector.js` trimmed to a single helper, `findActiveAgentId(messages)`, used to give the classifier "active build context."
- Deleted dead code: `frontend/lib/business/creationDetector.js`, `frontend/lib/business/showMeHowDetector.js`, `backend/lib/business/creation/intent_detector.py`.
- New test file `backend/tests/test_intent_router.py` (9 tests: deterministic short-circuits + mocked-httpx parsing/fallback robustness for valid JSON, markdown-fenced JSON, invalid intent, non-200, exception, malformed JSON).

### Mid-phase fix (found during live verification, not in original §D list)
Initial live testing surfaced a real ambiguity: a bare **"yes"** replying to the assistant offering to *explain* something (e.g. "Want me to explain how call-routing settings work?") was classified `show_me_how` instead of `chat` — i.e. a one-word confirmation could trigger the heavyweight walkthrough-generation flow instead of a normal chat explanation. Fixed by tightening the `show_me_how` definition to require the **user's own current message** to explicitly ask for a walkthrough, and adding a worked example to CRITICAL RULE 2 ("bare confirmation to an offer to explain" → `chat`). Also required restarting the local uvicorn process — it does not run with `--reload`, so edits to `intent_router.py` are not picked up by an already-running server.

### Live verification — real output from the running server (`POST /api/business/classify-intent`, real Anthropic Haiku call, post-fix)

| # | Scenario | Expected | Got `intent` | Got `reason` |
|---|---|---|---|---|
| 1 | "Adjust the agent's greeting to sound more human" (active_agent_id set, last assistant msg mentions that agent) | chat | chat | "request to modify existing agent's greeting" |
| 2 | "build an agent for this restaurant: https://example-restaurant.com" | create | create | "user explicitly asks to BUILD an agent" |
| 3 | "What's my dream job?" | chat | chat | "open-ended question seeking assistant's input/conversation" |
| 4 | "Remind me in 1 min to check the oven" | chat | chat | "user requesting a tool action (set a reminder)" |
| 5 | "Note this down: the supplier called, new lead time is 3 weeks" | chat | chat | "user sharing content for assistant to remember/store" |
| 6 | "remember the thing we talked about" (ambiguous) | chat | chat | "user asking assistant to store/remember content from conversation" |
| 7 | "yes" after assistant offered to build/deploy a voice agent | create | create | "bare confirmation to assistant's explicit build/deploy offer" |
| 8 | "yes" after assistant offered to *explain* call-routing settings | chat | chat | "bare confirmation to an offer to explain, not to build/deploy" |
| 9 | "How do I get an agent built for my business?" | create | create | "User is asking the assistant to build an agent for their business" |

**9/9 scenarios correct** — this covers regression scenarios 1, 2, 3, 4, 5, 6 from §D (routing-relevant; #7 is a Phase 3 concern) plus 3 additional adversarial cases from §A1/A5.

### Automated tests — real output
```
$ python -m pytest backend/tests/test_intent_router.py -v
test_intent_router.py::test_attachments_always_chat PASSED
test_intent_router.py::test_empty_message_is_chat PASSED
test_intent_router.py::test_no_api_key_falls_back_to_chat PASSED
test_intent_router.py::test_valid_classification_passthrough PASSED
test_intent_router.py::test_markdown_fenced_json_is_parsed PASSED
test_intent_router.py::test_invalid_intent_value_falls_back_to_chat PASSED
test_intent_router.py::test_non_200_falls_back_to_chat PASSED
test_intent_router.py::test_request_exception_falls_back_to_chat PASSED
test_intent_router.py::test_malformed_json_falls_back_to_chat PASSED
9 passed

$ python -m pytest backend/tests/ -q
148 passed   (was 139 before this phase; +9 new, 0 broken)

$ npm run build   (frontend/)
exit 0 — compiles clean (pre-existing onnxruntime-web/vad-web warnings only, unrelated)
```

### Honesty notes
- The 3-way taxonomy is simpler than the 5-way one sketched in §E. This is a deliberate simplification, not a shortfall — `edit_agent` and `deploy_confirm` are fully covered as `chat`/`create` respectively by the CRITICAL RULES, and collapsing them avoids adding two more branches to the frontend switch for no behavioral gain.
- `intent_classifier.py` (A2, prompt-section selector) and the sync-httpx blocking issue (STABILITY-AUDIT #1) were intentionally left untouched, as scoped.
- Classification is an LLM call — not deterministic. The 9/9 result is real but is one sample; genuinely adversarial phrasing could still occasionally misroute. The fallback on any error/ambiguity is always `chat` (the safest flow — never silently fires a build or a walkthrough), which bounds the failure mode.

Verification plan for Phase 1: run backend locally, hit `/business/classify-intent` directly with the 7 scenarios from §D (and a few adversarial paste/edit-drift cases from A1), confirm correct `intent` for each with real logged output before wiring the frontend; then wire frontend and manually exercise scenario 1 (agent edit) end-to-end against local backend + dev frontend.
