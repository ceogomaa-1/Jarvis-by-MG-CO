# CHANGELOG — Batch 42: "CONCRETE" — Phase 0 (Stability Audit + Test Harness)

**Date:** 2026-06-10
**Branch:** main
**Scope:** Phase 0 only — audit, test harness, regression tests for previously-fixed
bugs, prioritized defect list. **No production behavior changed**, with one
exception noted below (test-speed-only monkeypatches).

---

## Deliverables

1. **`STABILITY-AUDIT.md`** (new, root of repo) — full system map:
   - §1–2: every backend route (Personal `/api/...` and Business `/api/business/...`)
     with method, auth, request/response shape, and error handling.
   - §3: connector inventory (12 connectors) with write-action gating, timeouts,
     auth-failure UX, crash-proofing.
   - §4: `business/chat.py` tool-loop `stop_reason` handling (all 8 cases confirmed
     to terminate cleanly).
   - §5: creation pipeline (orchestrator → sub-agents → site generator → deploy
     pipeline vs. legacy LLM-driven `deployment_phase.py`).
   - §6: frontend inventory — 54 fetch call sites, polling loops, SSE consumers,
     working indicators, auth flow, attachment handling.
   - §7: confirmed-present fixes from Batches 2/4/5/6/6b (not re-flagged).
   - §8: test harness design (this batch).
   - §9: prioritized defect list, 21 items ranked by severity × frequency, with a
     suggested Phase 1–6 ordering.
   - §10: explicitly out-of-scope items for Phase 0.

2. **Test harness** (`backend/tests/`):
   - `.env.test` — throwaway placeholder credentials. `ANTHROPIC_API_KEY` is a
     non-empty placeholder (required so `backend/main.py` doesn't `RuntimeError`
     on import); Supabase/connector keys left empty so every route takes its
     documented "not configured" fallback branch.
   - `conftest.py` — loads `.env.test` with `override=True` *before* any backend
     module is imported, stubs `mem0` (see Defect #8 below), and provides a
     session-scoped `client` fixture (`TestClient(backend.main.app)`).

3. **New test files**:
   - `backend/tests/test_smoke_routes.py` — 41 tests covering every GET route
     across Personal and Business (status codes + required JSON keys), plus
     validation-error paths (`400`/`422`/`404`), voice-route `503`s, and OAuth
     redirects (asserted via `follow_redirects=False` so no real network call to
     Google is made).
   - `backend/tests/test_creation_routing_guards.py` — 9 tests for the Batch 6
     `_is_website_build`/`_INGEST_RE` paste-guard matrix (short triggers, ingest
     intents, long pastes with trigger only in body vs. first line).
   - `backend/tests/test_deploy_pipeline_422_retry.py` — 2 tests for the Batch 6
     GitHub 422-collision retry in `deploy_pipeline.py` (collision retries to
     `-v2` and continues through to `deployment_pending`; non-422 errors fail
     fast with no retry).

---

## Dev-environment fixes (required to get the harness running at all)

- **8 packages from `requirements.txt` were not installed** in this dev
  environment (`apscheduler`, `supabase`, `reportlab`, `pypdf`, `python-docx`,
  `cartesia`, `deepgram-sdk`, `trafilatura`). Without them, `backend.main` could
  not be imported at all. Ran `pip install -r requirements.txt` to close the gap.
  The pre-existing 61 tests never caught this because none of them import
  `backend.main`.

- **Test-speed fix (no production change)**: `deploy_pipeline._EXTERNAL_STATUS_INTERVAL`
  defaults to `8.0` seconds — `_await_connector_call` always sleeps a full
  interval before checking whether the (instant, fake) connector call finished.
  The existing `test_deploy_pipeline_pending.py::test_deploy_pipeline_returns_pending_without_polling`
  was taking **32 seconds** as a result. Added the same
  `monkeypatch.setattr(deploy_pipeline, "_EXTERNAL_STATUS_INTERVAL", 0.01)` that
  the *other* existing test in that file already used. New tests in
  `test_deploy_pipeline_422_retry.py` use the same pattern from the start.
  **Result: full backend suite went from 61 tests / ~33s to 113 tests / ~1.8s.**

---

## New defect discovered while building the harness

While wiring up `conftest.py`'s `TestClient(app)` fixture, importing
`backend.main` failed even with a valid `ANTHROPIC_API_KEY` placeholder:

```
ValueError: Mem0 API Key not provided. Please provide an API Key.
```

**Root cause**: `backend/memory.py:14` runs
`_client = MemoryClient(api_key=MEM0_API_KEY)` **at module import time**.
`MemoryClient.__init__` makes a **live HTTP call to `https://api.mem0.ai/v1/ping/`**
to validate the key and raises on any non-2xx response or unreachable host.
`backend/routes/chat.py` (Personal) imports `backend.memory` at module level,
and `backend/main.py` imports `chat.py` at module level — so:

- Missing/invalid/revoked `MEM0_API_KEY`, **or**
- any Mem0-side outage/network blip at boot time

...crashes the **entire app (Personal + Business)** with an opaque error, not a
clear message like the existing `ANTHROPIC_API_KEY` `RuntimeError` check.

This is now **Defect #8** in `STABILITY-AUDIT.md` §9 (HIGH severity — same
total-outage blast radius as the `ANTHROPIC_API_KEY` check, but with a broader,
third-party-network-dependent trigger surface and no diagnostic message). The
defect list (21 items) was renumbered to insert this at #8; the "Suggested
Phase ordering" section was updated accordingly.

For the test harness itself, `conftest.py` stubs `mem0` in `sys.modules` before
`backend.main` is imported (mirrors how the existing suite avoids real
Supabase) — this is test-isolation only and does **not** fix the production
issue, which is left for Phase 1.

---

## Test results

```
python -m pytest backend/tests -q
113 passed in 1.80s
```

(61 pre-existing + 41 smoke + 9 creation-routing-guard + 2 deploy-422-retry)

---

## Prioritized defect list (summary — full detail in STABILITY-AUDIT.md §9)

| # | Severity | Defect |
|---|---|---|
| 1 | HIGH | `intent_classifier` blocking sync `httpx.post` (8s) inside async system-prompt build — likely root cause of "feels slow" |
| 2 | HIGH | `/api/proactive/check/{user_id}` unhandled `jarvis_think` call → recurring 500s every 5 min |
| 3 | CRITICAL | No auth/authz on any Personal route (IDOR-class) |
| 4 | CRITICAL | `/api/debug/last-error` unauthenticated, leaks tracebacks + user messages |
| 5 | HIGH | No `/health`, no global exception handler |
| 6 | MEDIUM-HIGH | Business attachments silently dropped if >20MB/unsupported, no user feedback |
| 7 | MEDIUM-HIGH | `/business/deploy-status` reports `BUILDING` even when Vercel connector call itself fails |
| 8 | HIGH | **(new)** `backend/memory.py` Mem0 client boot-time live network dependency crashes whole app |
| 9 | HIGH | App-wide hard crash if `ANTHROPIC_API_KEY` unset |
| 10–21 | MEDIUM → LOW | tool-loop parity, unsigned OAuth state, `supabase_project__run_sql` not write-gated, local-disk state, operator SSE no terminal sentinel, unhandled 500s, error-shape inconsistency, misc (see §9) |

Suggested ordering for Phases 1–6 is in `STABILITY-AUDIT.md` §9.

---

## Not done in Phase 0 (by design)

- No production code changed (other than the two test-speed monkeypatches above).
- No fixes to any of the 21 defects — that's Phase 1+.
- Frontend test infrastructure (Jest/Vitest/Playwright) was **not** added —
  `frontend/package.json` has no test runner, so the "attachment drop" and
  "readiness polling" frontend bugs remain untestable until a later phase adds
  one. Flagged in §8, not actioned here.
- Live verification against deployed Render/Vercel instances — out of scope
  per §10.
