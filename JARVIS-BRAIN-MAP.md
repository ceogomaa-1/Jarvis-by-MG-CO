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

---

## G. Phase 2 — Completion Report

**Status: DONE. Implemented, deployed to local server, verified live (real `/api/chat` and `/api/business/chat/stream` calls), regression-tested, committed.**

### What changed

- New `backend/lib/grounding.py` — exports `GROUNDING_CONTRACT`, a single canonical anti-hallucination block (the 3 rules from §B's Phase 2 target: only state facts from a tool/connector result, the user's own messages, memory, or their profile; if a lookup/scrape/search failed or returned nothing, say so and either ask or proceed with an explicitly-labeled placeholder; never backfill specifics that weren't actually retrieved).
- **B3** (`backend/llm.py`, Personal): `GROUNDING_CONTRACT` injected into `_build_system_prompt()`, right after `_CITATION_RULES`.
- **B1 / B6** (`backend/lib/business/system_prompt_builder.py`, Business chat): `GROUNDING_CONTRACT` injected into `build_system_prompt()`, unconditionally, for every prompt variant (generic and bible-loaded). This is the same injection point that serves B6's concern (wrong-bible-section answers) — the contract's "never backfill specifics, a labeled placeholder beats a confident guess" rule applies regardless of which bible sections got loaded.
- **B1** (`backend/lib/business/creation/sub_agents.py`, Business creation sub-agents): `_BASE_SUB_AGENT_TONE` rewritten to include `GROUNDING_CONTRACT` plus a sub-agent-specific addendum ("you can't ask the user anything — if a real fact wasn't given to you in this task's context, use an obviously-generic placeholder like `[Your Business Name]` instead of inventing one"). Applies to all 6 `SUB_AGENT_PROMPTS` (strategist/copywriter/designer/researcher/analyst/reporter).
- **B4** (`backend/user_model.py`): `get_user_model()` now returns `(model, lookup_failed)` instead of just `model`, distinguishing "genuinely new/empty user" (`lookup_failed=False`) from "Supabase lookup itself failed" (`lookup_failed=True`). Three downstream functions updated:
  - `summarize_user_for_prompt()` — on `lookup_failed`, returns a "PROFILE LOOKUP UNAVAILABLE right now (Supabase error) — this is NOT necessarily a new user" message instead of falling through to "New user — still getting to know them."
  - `update_user_model()` — on `lookup_failed`, returns `False` immediately without merging/saving, preventing a transient Supabase outage from overwriting a real profile with a fresh empty one via the upsert's merge-duplicates.
  - `get_onboarding_prompt()` — on `lookup_failed`, returns the "complete" onboarding prompt (doesn't re-trigger onboarding for a returning user during an outage).
  - `backend/routes/user_routes.py`'s two endpoints (`/user/onboarding-status/{user_id}`, `/user/model/{user_id}`) updated for the new tuple signature; response shapes unchanged (frontend unaffected).
- **B5** (`backend/memory.py`): new sentinel constant `MEMORY_LOOKUP_FAILED_NOTE`. `get_relevant_memories()` keeps its `str` return type, but now returns this sentinel (instead of `""`) when Mem0 is rate-limited or errors — so the system prompt can tell Jarvis "the lookup failed, this does NOT mean there's nothing to know" rather than implying zero memories. The genuinely-empty case (`results == []`) still returns `""` unchanged.
- **B8** (`backend/lib/business/creation/site_generator.py` + `backend/routes/business/create.py`): `generate_site()`/`_fallback_site()` now return an `is_fallback: bool` field. `create.py`'s two deploy call sites check this flag and, if true, emit a new `deployment_status` SSE event telling the user a generic starter was deployed instead of their custom build ("Say 'rebuild the site' to retry the custom version") — previously this distinction was silently dropped.
- **B2** (`backend/lib/business/web_scrape.py` `execute_web_tool`) — **no fix needed**. Confirmed live this phase (regression test 2 below): a failed scrape returns a real connection-error result to the model, which (with `GROUNDING_CONTRACT` now in its prompt) reports the failure honestly and explicitly refuses to invent menu items/founding years.
- **B7** (`backend/lib/business/walkthrough_generator.py`) — **no fix needed**. On inspection, walkthroughs are generic "how to use [SaaS tool]" tutorials grounded by real web search (Brave API, falling back to `web_search`) — they describe the tool's general public UI (true regardless of whether *this* user has connected it), not claims about the user's specific account data. If search returns nothing, `_fallback()` returns an honest generic "open the application and navigate to the relevant section" rather than a fabricated specific UI claim. B7's original framing ("does it check connection status before claiming 'click X in your Stripe dashboard'") doesn't apply to this kind of generic, search-grounded tutorial content.

### Mid-phase fix (found during live verification, not in original §B list)

The first live `/api/chat` smoke test after restarting the server returned `"Hit a snag on my end. Try that again?"` with `_debug: "LLM_EXCEPTION: UnicodeEncodeError: 'charmap' codec can't encode character '→' in position 59"`. Root cause: `backend/llm.py`'s `get_current_moment_block()` has a pre-existing debug `print(f"TIME_INJECT: user_id={user_id} → tz=...")` containing a literal `→` (U+2192) arrow. On this Windows dev box, `sys.stdout` defaults to `cp1252`, which cannot encode `→` — so **every** `/api/chat` call (this print runs on every `jarvis_think()`) was crashing into the generic "Hit a snag" fallback, pre-dating Phase 2 and unrelated to any Phase 2 edit. This is exactly the kind of "Jarvis silently fails and reports a generic non-answer" failure mode the batch is about, and it was blocking all live verification, so it was fixed as part of this phase: `backend/main.py` now calls `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` / same for `stderr` at the top of the module (before any other imports), so non-ASCII characters in logging (→, em-dashes, etc., used throughout the codebase) never crash a request again. Production (Linux/Render) already defaults to UTF-8 stdout, so this is a no-op there — purely a Windows-dev-local fix for a latent bug. Required a full server restart (killed PID 27000, fresh process on PID 10076).

### Live verification — real output from the running server (post-fix)

| # | Check | Call | Result |
|---|---|---|---|
| — | `/api/chat` smoke test | `POST /api/chat {"user_id":"user_d4533f...", "message":"just say OK and nothing else, this is a smoke test"}` | `{"response":"OK", ...}` — no more `LLM_EXCEPTION` |
| 3a | Real user, real profile (B4 success path) | `POST /api/chat {"user_id":"user_d4533f...", "message":"What is my name?"}` | `"Your name is Mohamed."` — correct, from real Supabase `user_models` row |
| 3b | Regression #3 — seeded "dream job" fact | Seeded a throwaway test user (`current_focus.top_goals = ["Dream job: become a creative director at a major ad agency"]`, `onboarding_complete: true`, `interaction_count: 3`) via `save_user_model`, then `POST /api/chat {"user_id":"test-phase2-regression3", "message":"What is my dream job?"}` | `"Your dream job is to become a creative director at a major ad agency.\n\nWhat kind of work are you doing right now to move toward that?"` — answered from seeded profile, no invention, natural follow-up. Test row deleted from Supabase after. |
| 2 | Regression #2 — restaurant URL that doesn't resolve | `POST /api/business/chat/stream {"user_id":"test-phase2-regression2", "message":"Here is my restaurant website: https://this-restaurant-domain-does-not-exist-zzzqq123.com -- whats on the menu and when was it founded?"}` | Tool call `web__scrape_website` executed → failed (connection error). Response: *"That URL is dead — the fetch came back with a connection error... Here's what I **won't** do: make up your menu, invent a founding year, or fill in plausible-sounding details. That would be fabricated data, not your real business. **Here's what I need from you to move forward:** 1. Correct URL... 2. Or just tell me directly..."* — textbook B2 + GROUNDING_CONTRACT behavior. |
| B5 | Mem0 rate-limited during 3a/3b (`429 Too Many Requests`, real, observed in logs) | `get_relevant_memories()` invoked as part of normal chat flow | Confirmed returns `MEMORY_LOOKUP_FAILED_NOTE` (`"(memory lookup temporarily unavailable — this does not mean there's nothing to know about the user...)"`), not `""` — verified by direct call. The live chat responses above did not claim "I know nothing about you." |

### Automated tests — real output

```
$ python -m pytest backend/tests/ -q
164 passed, 2 warnings in 1.65s   (was 148 before this phase; +16 new: test_user_model.py x8, test_memory.py x3, test_site_generator.py x5)
```

### Honesty notes

- B2 and B7 required no code change — both were already grounded (real tool-result errors / real web-search context respectively). The value added for B2 is the *reporting* layer: `GROUNDING_CONTRACT` is what turns "scrape failed" from a possible silent-invention risk into the explicit, user-visible refusal-to-fabricate seen in regression test 2's live output.
- B4 and B5 fix the same class of bug (a failed lookup being indistinguishable from "genuinely nothing here") via two different mechanisms — B4 is a `(dict, bool)` tuple signature change (3 internal callers + 1 route file, all within reach, and the data-loss risk in `update_user_model` justified the explicit check), while B5 is a non-breaking sentinel string (4 callers across 3 files, including cron and voice routes, where a signature change would have had a much larger ripple). Both achieve "tell the model the lookup failed, don't imply nothing to know."
- The Mem0 `429 Too Many Requests` seen during live verification is a real, currently-active condition on the production Mem0 account (log message says "quota exceeded, resets June 1" — today is 2026-06-14, so either this message has a stale/incorrect date or the quota is monthly and still exhausted; this is a pre-existing operational issue, not a Phase 2 regression, and is out of scope for this batch beyond confirming B5's failure-path behaves correctly under it).
- The Unicode/stdout-encoding fix is a genuine pre-existing production-readiness bug (every `/api/chat` call on a `cp1252`-stdout host was failing), discovered only because Phase 2's live verification required a real `/api/chat` round-trip. It is unrelated to any Phase 2 grounding change but was blocking, so it was fixed in the same commit.
- Regression test 2 was run against the **chat** flow (`/api/business/chat/stream`), not the full **creation** flow (multi-agent site build + Vercel deploy), which is what "build an agent for this restaurant" would route to per Phase 1's classifier. The chat-flow test exercises the identical `GROUNDING_CONTRACT` text and the identical `web__scrape_website` tool/failure path that the creation flow's sub-agents and `site_generator.py` also rely on (B1/B8), so it's a faithful proxy without requiring a full live deploy cycle for this verification pass.

---

## H. Phase 3 — Completion Report

**Status: DONE. One real bug fixed (C7), two items confirmed already-solid (C3, C6), verified live, committed.**

### What changed

- **C7** (`backend/routes/business/create.py` `GET /business/deploy-status`, + `frontend/components/business/ChatCanvas.js`): when the Vercel deployment-status *check itself* fails (`status_res.ok is False` — e.g. a 404/401/network error calling Vercel's API), the route previously returned `{"state": "BUILDING", "error": <real error>}`. The frontend poller ignores `error` for any non-`READY`/`ERROR`/`FAILED`/`CANCELED` state and just shows "Building on Vercel… (Xs, BUILDING)" — so a connector failure that already happened was presented as "still in progress," indefinitely (until the existing 6-minute poll timeout). Fixed:
  - Backend now returns `{"state": "UNKNOWN", "error": <real error>}` in this case, and persists it via `update_deployment_by_id(deployment_id, "UNKNOWN", error=...)` (maps to `status: "building"`, `deployment_status: "UNKNOWN"`, `deployment_error: <real error>` in `business_creations` — so the real error is visible to anything reading that row, not silently dropped).
  - Frontend poller (`ChatCanvas.js`) now special-cases `state === 'UNKNOWN'`: shows `"Can't check deployment status right now ({error}) — retrying… (Xs)"` instead of `"Building on Vercel… (Xs, UNKNOWN)"`. Still polls/retries (status-check hiccups are often transient) and still falls back to the existing 6-minute "Still building… the repo and expected URL are saved below" message if it never resolves — only the *in-progress messaging* changed, not the control flow.
  - New test `backend/tests/test_deploy_status_unknown.py` (1 test).
- **C3** (`backend/routes/business/chat.py` `/business/chat/confirm-action`) — **no fix needed**. `_make_fallback_confirmation()` checks `"error" in result_data` FIRST, before any "deleted"/"updated"/"created" status branches, returning `"Action failed: {error}"` — it cannot fall through to an optimistic default when an error is present. The primary path (Haiku-generated confirmation) is separately instructed: "If the result contains an 'error' key, the action FAILED — say so plainly and do not claim success." Live-verified below.
- **C6** (`backend/routes/proactive_routes.py` `/proactive/check/{user_id}` + `backend/cron/notes_reminders.py` + `backend/cron/briefing.py`) — **no fix needed**. The code MAP.md §C6 described (a bare `jarvis_think` call with no try/except, "mark done" before delivery confirmed) no longer exists in this form — it was superseded by the `fd06459`/`8e99050`/`579f0b5` reminder-system rewrite that landed on `main` before this batch started. Current state, re-verified by reading the live code this phase:
  - `check_proactive()` wraps everything in try/except and "Never raises — any internal error is swallowed and returns has_message: false" (verbatim from its own docstring).
  - `run_notes_reminders()` only calls `_mark_note_done()` (or re-arms a recurring note) once **every** dispatch channel (`inapp`/`push`/`email`) has confirmed-delivered, or the note is >48h overdue (explicit retry-cutoff, logged). A failed channel is left unmarked and retried next tick — never silently marked done.
  - `run_morning_briefings()` per-user try/except; `save_briefing()` (which writes the `proactive_messages` row the user actually sees) is only called *after* `generate_morning_briefing()` (the `jarvis_think` call) succeeds — a failure means no row is written and no claim is made, just a skipped check-in for that day.

### Live verification — real output from the running server

| # | Check | Call | Result |
|---|---|---|---|
| C7a | Status-check failure on a real Vercel-connected user, invalid deployment ID | `GET /api/business/deploy-status?user_id=3363afdc-9bca-4b88-893c-f535c62a6687&deployment_id=dpl_invalid_test_xyz123` | `{"state":"UNKNOWN","url":null,"error":"Deployment lookup failed: 404","logs":null}` — real Vercel 404, no longer reported as `BUILDING` |
| C7b | Sanity check — existing "not connected" path unchanged | `GET /api/business/deploy-status?user_id=test-no-vercel-user&deployment_id=dpl_invalid_test_xyz123` | `{"state":"ERROR","url":null,"error":"Vercel connector not connected","logs":null}` — unchanged |
| C3 / regression #7 | Tool failure reported honestly, not as success | `POST /api/business/chat/confirm-action {"user_id":"test-phase3-confirm-action","tool_name":"elevenlabs__update_agent","tool_input":{"agent_id":"fake_agent_123","first_message":"Hey there!"}}` (ElevenLabs not connected for this user) | `{"response":"The action failed — ElevenLabs is not connected. You need to connect it via Settings → Connections before you can update the agent.","tool_result":{"error":"Not connected to elevenlabs. Connect it via Settings → Connections and try again."}}` — real error surfaced, no "Done"/"Updated" claim |

### Automated tests — real output

```
$ python -m pytest backend/tests/test_deploy_status_unknown.py -v
test_deploy_status_unknown.py::test_status_check_failure_is_unknown_not_building PASSED
1 passed

$ python -m pytest backend/tests/ -q
165 passed, 2 warnings   (was 164 before this phase; +1 new)

$ npm run build   (frontend/)
exit 0 — compiles clean, no errors
```

### Honesty notes

- C6 required reading three files (`proactive_routes.py`, `notes_reminders.py`, `briefing.py`) to confirm the §C6-described bug no longer exists anywhere in the proactive-message pipeline — this was a "verify the fix already happened" task, not a "no fix needed because I didn't look" rubber stamp. The unrelated `fd06459`/`8e99050` commits (already on `main` before this batch) did the actual work; this phase's contribution for C6 is the verification + write-up.
- C7's frontend change (`ChatCanvas.js` status string) was verified via `npm run build` (compiles clean) but **not** exercised in a browser against a live deploy — doing so would require triggering a real multi-minute Creation 1.0 site build + Vercel deploy and then forcing the status-check call to fail mid-poll, which is disproportionate for a one-line status-message change that doesn't alter control flow (the `UNKNOWN` branch falls into the same "keep polling" path as the previous default, only the displayed string differs). The backend half (the actual `state` value returned) was verified live against the real Vercel API (C7a above).
- C1/C2/C4/C5/C8 from §C were Phase 0 findings already rated ✅ solid or low-priority/internal-only and were not re-litigated this phase — no new information surfaced that would change those verdicts.
