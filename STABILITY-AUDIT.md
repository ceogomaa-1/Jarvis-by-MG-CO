# STABILITY AUDIT — Jarvis (Personal + Jarvis OS1)

**Date:** 2026-06-09
**Scope:** Phase 0 of Batch 42 ("CONCRETE"). Read-only inventory — no behavior changed.
**Stack:** Next.js (Vercel) + FastAPI (Render) + Supabase (DB/auth) + Anthropic + ElevenLabs/Cartesia/Deepgram + Brave + connectors (Stripe, GitHub, Vercel, Notion, Google, Twilio, SMTP, GoHighLevel, Supabase-project, Buffer, ElevenLabs).

This document is the map. It does not fix anything. Section 9 is the prioritized defect list that Phases 1–6 work from.

---

## 0. Repo / Product Layout

```
backend/
  main.py                  — FastAPI app, router registration, CORS, cron scheduler, NO /health, NO global exception handler
  llm.py                   — Personal Jarvis: system prompt builder + jarvis_think() (single-pass tool loop)
  routes/                  — Personal product routes (chat, voice, memory, notes, documents, export, files, history, google auth, proactive, user prefs/model)
  routes/business/         — Jarvis OS1 (Business) routes (chat, create, show-me-how, connections, conversations, operator, proactive, readiness, brand)
  lib/business/            — Business system prompt builder, connectors, tool builder/executor, creation pipeline, readiness, Farida
  tools/                   — Personal-only tool registry (web search, gmail, calendar, documents, timers, etc.) — NOT used by Business
  cron/                    — morning briefings (08:00), business risk briefings (06:00), operator nightly (02:00), all America/Toronto
  tests/                   — 61 existing tests (Buffer connector, deploy pipeline pending, Farida x2)

frontend/
  app/                     — Next.js App Router: landing, login, welcome (mode picker), personal (`/`), business (`/business/chat`, `/business/workflow`), auth callback
  app/api/waitlist         — only Next.js API route (Notion proxy for waitlist form) — NOT a backend proxy
  components/business/     — ChatCanvas, CreationCanvas, Walkthrough, WorkflowCanvas, ReadinessBar, modals, ThinkingIndicator, etc.
  components/onboarding/   — SplitChoice, BusinessOnboardingModal, TimezoneStep, LoadingTransition
  lib/business/            — creationDetector.js, showMeHowDetector.js (pure regex routing, client-side)
```

Two products share one backend and one Supabase project:
- **Jarvis Personal** — `jarvis-by-mg-co.vercel.app`, root `/` chat, `backend/routes/*.py` + `backend/llm.py`.
- **Jarvis OS1 (Business)** — `/business/chat`, `backend/routes/business/*.py` + `backend/lib/business/*`.

---

## 1. Backend Routes — Jarvis Personal (`/api/...`)

### `chat.py`
| Route | Method | Auth | Request | Success | Error handling | Streaming |
|---|---|---|---|---|---|---|
| `/api/chat` | POST | `user_id` body field, **no validation** | `ChatRequest{user_id, message, conversation_history, image_base64?, image_type?, attachments?, voice_mode?}` | `{"response","user_id","usage"?,"_debug"?}` | try/except around `jarvis_think`; on exception logs to in-memory `_error_buffer`, returns `_FALLBACK_LLM_ERROR` with **HTTP 200**. `_debug` field leaks `f"{type(exc).__name__}: {exc}"` | No |
| `/api/chat/stream` | POST | same | same | SSE `data: <char>` per char, `usage` event, `__sources` event, `[DONE]` | All paths (incl. error/usage-limit) reach `[DONE]`. Errors stream `_FALLBACK_LLM_ERROR`/`_FALLBACK_EMPTY` as normal text + `[DEBUG:...]` line (info leak) | "Streaming" but **`jarvis_think` runs to completion first**, then chars are emitted with `asyncio.sleep(0.01)` — first byte is delayed by the full LLM+tool round trip |
| `/api/chat/artifact` | POST | `user_id` body field, only used for moment block | `{message, user_id}` | `{"artifact": "<html>"}` | **No try/except around the `httpx` call** → unhandled exception = raw 500. Non-200 handled (`resp.text[:200]` returned to client) | No |
| `/api/usage` | GET | `user_id` query, default `""` | — | `{used,limit,remaining,is_admin,resets_in}` or `400` if missing | Hardcoded fallback `limit:15` when Supabase unconfigured — **mismatches actual `DAILY_MESSAGE_LIMIT=32`** | No |
| `/api/debug/last-error` | GET | **none — fully open** | — | last 20 `{user_msg, traceback, debug}` entries | N/A | No |

### `documents.py`
| Route | Method | Auth | Notes |
|---|---|---|---|
| `/api/documents/upload` | POST | `user_id` Form field, no validation | `HTTPException(400/500)` for bad input/no DB; **no try/except around Supabase insert** (`document_chunks`/`user_documents`) → raw 500 on transient DB error |
| `search_user_documents()` (helper used by chat) | n/a | n/a | Two-layer try/except, fully fail-safe → `""` worst case |

### `export.py`
| `/api/export/pdf` | POST | `user_id` field present but **unused** | `503` if reportlab missing; **no try/except around `doc.build()`** — malformed content → raw 500 |

### `files_routes.py`
| `/api/files/upload` | POST | `user_id` Form field, **unused** | Image branch: **no try/except around Anthropic httpx call** → raw 500 on network error/timeout. PDF/text branches have local fallbacks. |

### `google_auth_routes.py`
| Route | Method | Notes |
|---|---|---|
| `/api/google/auth/{user_id}` | GET | Redirect to Google OAuth, `user_id` used as `state` — **unsigned** |
| `/api/google/callback` | GET | `state`=`user_id` round-tripped, **not verified**. No try/except around token-exchange/Supabase upsert → raw 500. On missing `refresh_token`, returns raw Google `tokens` dict to client |
| `/api/google/status/{user_id}` | GET | delegates to `get_user_refresh_token`, no try/except here |

### `history_routes.py`, `memory_routes.py`, `notes_routes.py`
All `GET /api/{history,memory,notes}/{user_id}` — no validation, fail-safe at helper level (`[]`/`{}` on error). **Notes are per-user JSON files on local disk** (`data/notes/{user_id}_notes.json`) — not durable across Render redeploys/instances, no file locking.

### `proactive_routes.py`
| Route | Method | Notes |
|---|---|---|
| `/api/proactive/{user_id}` | GET | No try/except around two `httpx` calls (GET + PATCH mark-read), 10s timeout each |
| `/api/proactive/check/{user_id}` | GET, **polled every 5 min by frontend** | `_check_due_reminders` swallows all errors via bare `except Exception: return None` (no logging). If a reminder is due, calls `jarvis_think` (Anthropic) **with no try/except** — any Anthropic failure → raw 500 on every 5-min poll, AND the note never gets marked done (write-back happens *after* the LLM call), so the 500 repeats indefinitely until Anthropic succeeds |

### `user_preferences.py` — most consistent error pattern in Personal
All 5 routes (`GET/POST /api/user-preferences[/...]`, `/api/business-users`) use `try/except Exception as e: return {"ok": False, "error": str(e)}` — consistent shape, but `str(e)` leaks raw exception text in 200 responses.

### `user_routes.py`
`GET /api/user/onboarding-status/{user_id}`, `GET /api/user/model/{user_id}` — no validation, no try/except; `/user/model/{user_id}` returns the **entire internal user model verbatim**.

### `voice_routes.py`
~17 routes (`/voice/session`, `/voice/save-transcript`, `/voice/tool/*` ×10, `/voice/transcribe`, `/voice/synthesize[-stream]`, `/voice/list-voices`, `/voice/test*`). Highlights:
- `/voice/tool/*` (calendar, email, search, memory-search, local, timer×4) all return `{"result": "..."}` with **HTTP 200 even on failure** (by design — fed back to ElevenLabs agent), but means monitoring can't distinguish success/failure by status code.
- `/voice/save-transcript`: **no try/except** around the main save loop — partial saves possible on mid-loop exception.
- `/voice/list-voices`: calls `client.voices.list()` **synchronously inside `async def`** — blocks the event loop (unlike `synthesize_jarvis_voice` which correctly uses `asyncio.to_thread`).
- `/voice/synthesize-stream`: raw byte stream, no try/except around the Cartesia WS loop — mid-stream error just cuts audio off (no graceful end marker, but this is a raw stream not SSE so `[DONE]` doesn't apply).
- Many routes leak `str(e)` into `HTTPException(500, ...)` detail or `{"result": f"...{str(e)}"}`.

### Shared infra (`main.py`, `utils/`, `usage_limits.py`, `llm.py`)
- **No `/health` endpoint.** `GET /` → `{"status":"Jarvis is alive"}`, no dependency checks.
- **No global FastAPI exception handler** — unhandled exceptions fall through to default Starlette 500.
- **CORS**: `allow_origins=["*"]`, `allow_credentials=False`, explicit method allowlist, all headers.
- **No shared `user_id` normalization/auth helper** for Personal routes — `user_id` is raw client input everywhere (path/body/query/form/WS-header), never verified against a session. `_is_farida()` and `is_admin()` are the only special-cased identity checks.
- `usage_limits.py`: rolling 32-msg/90-min window via `business_daily_usage` table (shared name with Business); fails open (returns `[]`) if Supabase errors.
- `llm.py`: single `AsyncAnthropic` client, `timeout=60.0, max_retries=2`. `jarvis_think()` is **single-pass**: one tool-use round only — if the model wants to chain tool calls, the second round's `tool_use` is dropped and only its (possibly empty) text is returned → can trigger `_FALLBACK_EMPTY`. Individual tool calls inside the loop are **not wrapped** in try/except — one failing tool aborts the whole response.
- Hard `RuntimeError` at import time if `ANTHROPIC_API_KEY` missing — **takes down the entire app, including all Business/OS1 routes**, for a Personal-chat dependency.
- **`backend/memory.py` instantiates `mem0.MemoryClient(api_key=MEM0_API_KEY)` at module-import time** (line 14). `MemoryClient.__init__` makes a **live HTTP call to `https://api.mem0.ai/v1/ping/`** to validate the key and raises `ValueError` on any non-2xx response, and raises an *uncaught* `httpx` connection error if the host is unreachable. `chat.py` (imported by `main.py`) imports `backend.memory` at module level, so: missing/invalid/revoked `MEM0_API_KEY`, **or** any Mem0-side outage/network blip at boot, **takes down the entire app (Personal + Business)** with an opaque error — no clear message like the `ANTHROPIC_API_KEY` `RuntimeError` above. Confirmed by reproducing the import failure locally with `MEM0_API_KEY` unset (see §8 — required stubbing `mem0` to get the test harness to import `backend.main` at all).
- `local_agent_routes.py` (`/ws/local-agent`): `_connected_agents`/`_pending_requests` are **process-local in-memory dicts** — breaks under multi-instance/multi-worker Render deploys. Malformed JSON from client (`json.loads`) not caught — could kill the WS handler ungracefully.

---

## 2. Backend Routes — Jarvis OS1 (Business) (`/api/business/...`)

### `chat.py`
| Route | Method | Notes |
|---|---|---|
| `/business/usage` | GET | `{used,limit,remaining,is_admin,resets_in,window_minutes}`, falls back to `{used:0,limit:32,...}` if Supabase down |
| `/business/chat/stream` | POST (SSE) | `{message,user_id,conversation_id,attachments[]}`. `WRITE_ACTIONS` (15 actions across google/twilio/smtp/notion/elevenlabs/gohighlevel/buffer), `MAX_TOOL_ROUNDS=5`, `max_tokens=8192` (Batch 6). **All exit paths confirmed to emit a final message + `[DONE]`**: limit_exceeded, Farida greeting, non-200 Anthropic, stream `error`, `max_tokens` truncation (Batch 6 guard), `max_tokens` final text, non-tool_use stop, write-action gate (`pending_action`), `MAX_TOOL_ROUNDS` exhaustion, outer exception |
| `/business/chat/confirm-action` | POST | Always 200: `{"response","tool_result"}`. Confirmation-text generation (Haiku, 30s) falls back to `_make_fallback_confirmation` on failure |

`AttachmentItem.name: str = ""` present (Batch 6b); server-side `attachments[:5]` cap + 8000-char text-decode limit.

### `brand_routes.py`, `connections.py`, `conversations.py`
| Route | Notes |
|---|---|
| `GET/POST /business/brand` | 400 no user_id; 500 if upsert fails |
| `GET /business/connections/manifests` | static list |
| `GET/POST/DELETE /business/connections`, `POST /business/connections/test` | creds **persisted before validation** — a failed `test()` leaves an `"invalid"`-status row with the bad secret still in Supabase |
| `GET/POST /business/connections/google/auth\|callback` | same unsigned-`state`=`user_id` pattern as Personal |
| `GET/POST/PATCH/DELETE /business/conversations[...]` | **inconsistent success/error shapes**: PATCH returns `{"conversation":...}` on success but `{"ok":False}` on exception; POST `/messages` returns `{"message":...}` vs `{"ok":False}` |
| `GET /business/agents/activity`, `GET /business/memories/count` | swallow errors → empty defaults |

### `create.py`, `create_actions.py`
| Route | Notes |
|---|---|
| `GET /business/deploy-status` | Polls Vercel. **If the Vercel connector call itself fails (`ok=False`), reports `{"state":"BUILDING","error":...}`** instead of `ERROR` — a persistent connector failure looks identical to "still building" to a polling client |
| `POST /business/create` (SSE) | Two paths: deploy-confirmation (looks up prior artifact via `_DEPLOY_OFFER_RE` over last 8 assistant msgs) and normal creation via `orchestrate_creation`. **Batch 6 `_is_website_build`/`_INGEST_RE` guard confirmed present** (>600 chars or >6 newlines → only first line checked; ingest intents always `False`). All paths (incl. outermost exception, which calls `fail_creation_row`) end in `[DONE]` |
| `POST /business/create/{id}/refine` (SSE) | 404/400 pre-stream checks; empty result emits **both** `error` and `complete` events (double-signal) before `[DONE]` |
| `GET /business/create/{id}/pdf` | 404/400/503 as above |

### `operator_routes.py`
| Route | Notes |
|---|---|
| `GET /business/operator/pending\|runs` | raw REST, empty defaults on error |
| `POST /business/operator/trigger` | fire-and-forget `BackgroundTasks`, failures not surfaced |
| `GET /business/operator/status/stream` (SSE) | polling loop, **max 600×1s (10min) — if no terminal status by then, generator just stops with NO `[DONE]`/timeout sentinel** |
| `PATCH /business/operator/actions/{id}` | one of the few routes that raises `HTTPException(500, detail=str(e))` rather than swallowing |

### `proactive_routes.py`, `readiness_routes.py`
| Route | Notes |
|---|---|
| `GET /business/proactive/latest`, `/business/metrics` (GET) | empty defaults on miss/error |
| `POST /business/metrics` | **most rigorous error surfacing** of all routes audited (400/503/502/500 distinguished) |
| `GET /business/readiness` | 400 no user_id, delegates to `calculate_readiness` (single big try/except, partial-failure-safe, `is_ready: score>=100`) |
| `POST /business/autonomous/toggle` | fire-and-forget background insight generation on enable |
| `GET /business/proactive/unread`, `PATCH /business/proactive/{id}/read` | empty/ok defaults |

### `show_me_how.py`
`POST /business/show-me-how` (SSE): `status→title→intro→step*→complete→[DONE]`, exceptions → generic error + `[DONE]`. `GET /business/proxy-image` (10s timeout, 502 on exception). `POST /business/show-me-how/pdf` (503 if reportlab missing, `str(e)` in 500 detail).

---

## 3. Connector Inventory (Business)

| Connector | Service | Write actions (confirm-gated) | Timeout/retry | Auth-failure UX | Crash-proof |
|---|---|---|---|---|---|
| `buffer_conn.py` | Buffer (GraphQL) | `create_post`, `schedule_post`, `add_to_queue` ✅ | 25s, no retry | "access denied" on 401/403 | ✅ |
| `twilio_conn.py` | Twilio SMS | `send_sms` ✅ | 15s, no retry | "Invalid Account SID/Auth Token" | ✅ |
| `stripe_conn.py` | Stripe (read-only) | none (writes deferred) | 20s/page ×5, no retry | distinguishes invalid key vs restricted perms | ✅ |
| `smtp_conn.py` | SMTP | `send_email` ✅ | 15s socket, no retry | "use App Password" on auth error | ✅ (via `asyncio.to_thread`) |
| `elevenlabs_conn.py` | ElevenLabs | `create/update/delete_agent` ✅ | 30s TTS, no retry | `ConnectorResult(ok=False)` on `raise_for_status` | ✅ |
| `notion_conn.py` | Notion | `create_page`, `create_database` ✅ | default httpx timeout, no retry | ok=False on non-2xx | ✅ |
| `google_conn.py` | Google (Calendar+Gmail) | create/update/delete event, send_email ✅ | mints fresh token **every call** (no caching), bare `except: pass` → `None` | "Connect with Google" / "reconnect" messaging ✅ | ✅ |
| `canva_conn.py` | Canva | **stub** — only `test()` | n/a | "requires partner approval" | n/a |
| `gohighlevel_conn.py` | GoHighLevel CRM | `create_contact` ✅ | 10–15s, no retry | ok=False on non-2xx | ✅ |
| `github_connector.py` | GitHub (PAT) | none (deploy-pipeline only) | 20s (10s connect); `push_files` retries ref-update up to 5× | n/a | ✅ |
| `vercel_connector.py` | Vercel | none (deploy-pipeline only) | `deploy_files` 60s; 409 conflicts handled | n/a | ✅ |
| `supabase_project_connector.py` | Supabase Mgmt API | **`run_sql` (arbitrary SQL) NOT in `WRITE_ACTIONS`** — confirm is prompt-only | 30s, no retry | n/a | ✅ |

**Global pattern**: `tool_executor.execute_tool` wraps everything in try/except → `{"error": "Tool execution error: {e}"}`; `get_connector_for_user` returns `None` (not raise) for missing/inactive → `"Not connected to {connector_type}. Connect it via Settings → Connections..."`. **No connector failure can crash a chat turn** (confirmed across all 12).

**Dead/misleading**: `registry.py::_CONNECTOR_ACTIONS["canva"]` advertises `list_designs`/`create_design`, which don't exist on `CanvaConnector` — graceful "Unknown action" if ever called, but misleading in the system prompt's tool summary.

**Note**: `backend/tools/*` (Personal tool registry — web search, gmail, calendar, documents, timers) is **not used by Business** at all, except one optional fallback import of `web_search` inside `walkthrough_generator.py` (try/except-wrapped, static fallback on failure).

---

## 4. Tool Loop — `business/chat.py` `stop_reason` Handling

| `stop_reason` | Handling |
|---|---|
| `tool_use`, no write blocks | Execute via `execute_tool`, append results, continue loop |
| `tool_use`, write blocks present | `pending_action` SSE event + `[DONE]` — never executed inline, requires `/confirm-action` |
| `max_tokens` + in-flight tool_use with empty/partial input | **Batch 6 fix**: explicit truncation error naming the tool + `[DONE]` |
| `max_tokens` + pure text | Treated as final, usage incremented, `[DONE]` |
| `end_turn` / `refusal` / `pause_turn` / other | Final response, usage incremented, `[DONE]` |
| `MAX_TOOL_ROUNDS` (5) exhausted | "I hit a processing limit..." + `[DONE]` |
| Anthropic non-200 / stream `error` | Generic error + `[DONE]` |
| Outer exception | "Something went wrong. Please try again." + `[DONE]` |

No path treats a truncated `tool_use` as final-and-successful. No path lets Jarvis claim a write action succeeded without `/confirm-action` → `execute_tool` → real `ConnectorResult`. (Personal's `jarvis_think` does **not** have this rigor — see §1.)

---

## 5. Creation Pipeline (`backend/lib/business/creation/*`)

- **`orchestrator.py`**: `_plan_creation` (Opus, 60s) → JSON plan; sub-agents run via `asyncio.gather`. `run_sub_agent` never raises (verified) — `return_exceptions=False` is safe in practice.
- **`sub_agents.py`**: strategist/copywriter/designer/researcher/analyst/reporter, all Sonnet-4-6, 90s timeout.
- **`site_generator.py`**: `generate_site()` **always** returns a complete valid dict — any failure falls back to `_fallback_site()` (build-clean Next.js site). Downstream `site["project_name"]`/`site.get("files",[])` always safe.
- **`deploy_pipeline.py`** (deterministic, Batch 1/6): preflight requires GitHub+Vercel; **422-retry confirmed present** (`[name, name-v2, name-v3, name-v4]`, breaks on success or non-422 error); push_files 120s; optional Supabase migration (non-fatal); Vercel create_project→set_env→deploy_files (120s); ends `deployment_pending`. Per-step timeouts default 90s with 8s heartbeat pings.
- **`deployment_phase.py`** (OLD LLM-loop, non-website creations): `max_rounds=8`, `DEPLOYMENT_TIMEOUT=40.0`/round, but `create.py` wraps the whole thing in `asyncio.wait_for(timeout=45.0)` — **a single slow round can blow the outer 45s budget**, surfacing a generic timeout even though the loop was progressing. Increasingly superseded by `deploy_pipeline.py` for website builds.
- **`intent_detector.py`**: dead code, not imported by `create.py`/`chat.py`. Lacks the Batch 6 ingest guard. Latent trap if ever wired up.
- **`persistence.py`**: all Supabase ops try/except-wrapped, never raises.

---

## 6. Frontend Inventory

### 6.1 Frontend → Backend Fetches (54 call sites)

| Flow | Endpoints called |
|---|---|
| **Chat (Business)** | `POST /api/business/chat/stream` (SSE), `POST /api/business/chat/confirm-action`, `GET /api/business/usage` |
| **Chat (Personal)** | `POST /api/chat/stream` (SSE, AbortController 60s), `POST /api/chat/artifact`, `GET /api/usage` |
| **Creation** | `POST /api/business/create` (SSE), `GET /api/business/deploy-status` (poll), `POST /api/business/create/{id}/refine` (SSE), `GET /api/business/create/{id}/pdf` |
| **Show Me How** | `POST /api/business/show-me-how` (SSE), `POST /api/business/show-me-how/pdf` |
| **Conversations** | `GET/POST/DELETE /api/business/conversations[...]`, `GET /api/business/memories/count` |
| **Connections** | `GET /api/business/connections/manifests`, `GET/POST/DELETE /api/business/connections`, `POST /api/business/connections/test`, OAuth `.../google/auth` |
| **Brand / Metrics** | `GET/POST /api/business/brand`, `GET/POST /api/business/metrics` |
| **Operator / Workflow** | `GET /api/business/agents/activity`, `POST /api/business/operator/trigger`, `EventSource /api/business/operator/status/stream`, `GET /api/business/operator/pending`, `PATCH /api/business/operator/actions/{id}` |
| **Proactive (Business)** | `GET /api/business/proactive/latest`, `GET /api/business/proactive/unread` (poll), `PATCH /.../{id}/read`, `POST /.../mark-read` |
| **Readiness** | `GET /api/business/readiness` (poll, see §6.2) |
| **Onboarding / Prefs** | `GET/POST /api/user-preferences[...]`, `POST /api/business-users`, `PATCH /api/user-preferences/preferred-name\|timezone`, `POST /api/user-preferences/complete-onboarding` |
| **Personal model/history** | `GET /api/user/model/{userId}`, `GET /api/user/onboarding-status/{userId}`, `GET /api/history/{userId}`, `GET /api/proactive/{userId}`, `GET /api/proactive/check/{userId}` (poll) |
| **Voice** | `POST /api/voice/save-transcript` (flush, poll), `POST /api/voice/transcribe`, `POST /api/voice/synthesize-stream` |
| **Google** | `GET /api/google/status/{userId}`, `GET /api/google/auth/{userId}` (redirect) |
| **Export** | `POST /api/export/pdf` |

### 6.2 Polling Loops

| Location | Interval | Endpoint | Cleanup |
|---|---|---|---|
| `ReadinessBar.js:9-14` | **30000ms** | `/api/business/readiness` | ✅ `clearInterval`, gated on `userId` |
| `ChatCanvas.js` (~330-355) | 60000ms | `/api/business/proactive/unread` (+PATCH read) | ✅, gated on `autonomousEnabled && userId` |
| `ChatCanvas.js startDeployPolling` (403-478) | 5000ms, 6min cap | `/api/business/deploy-status` | ✅ on terminal states; **on fetch exception, interval NOT cleared — retries until 6min cap** |
| `app/page.js` (~1372-1380) | 30000ms | `POST /api/voice/save-transcript` (buffer flush) | ✅, gated on `userId` + non-empty buffer |
| `app/page.js` (~1577-1595) | **300000ms (5min)** | `GET /api/proactive/check/{userId}` | ✅, gated on `userId && onboardingComplete`; tab-title flips when unfocused |

**Readiness "fires every ~1s" claim — NOT reproduced in current source.** `ReadinessBar.js` is the only caller of `/api/business/readiness` repo-wide; its interval is 30000ms with correct cleanup, gated on `userId`. Either (a) already fixed in a prior batch, (b) symptom observed against a stale Vercel bundle, or (c) the *symptom* is real but caused by `ReadinessBar` **remounting** every ~1s due to a parent re-render loop in `ChatCanvas.js` (each mount re-fires the initial fetch before the 30s interval would tick) — which would not show up as a "1000ms" constant in source. **Action for Phase 4: verify against the live Network tab before declaring fixed or chasing a non-existent constant.**

### 6.3 SSE/Streaming Consumers

| Consumer | Endpoint | Events handled | Frozen-loading risk |
|---|---|---|---|
| ChatCanvas — show-me-how | `/api/business/show-me-how` | `status,title,intro,step,complete,error` | None |
| ChatCanvas — creation | `/api/business/create` | `conv_id,plan,agent_status,creation_id,artifact,complete,error,deployment_started,deployment_status,deployment_pending,deployment_complete,deployment_error` | None — all paths set `streaming:false` |
| ChatCanvas — chat | `/api/business/chat/stream` | `conv_id,tool_call,pending_action,usage` + 30ms-batched text | None — error path sets `streaming:false`, `isThinking:false`, `loading:false` |
| RefineModal | `/api/business/create/{id}/refine` | `artifact,error,[DONE]` | None |
| WorkflowCanvas | `EventSource /operator/status/stream` | raw `{stage,cycles_completed,status}`, `onerror` resets `isRunning` | None |
| app/page.js — personal chat | `/api/chat/stream` | `[DONE],[ERROR],[DEBUG:...]`, `__vs`, `__sources`, `usage`, text | None — `MAX_RETRIES=2` then `failed:true` + retry toast |

### 6.4 Working Indicators
`ThinkingIndicator.tsx` (business) + an **independent duplicate inline copy** in `app/page.js` (lines 806-848, same `_THINKING_PHRASES`, 400ms dots/4000ms phrase cycle) — code-duplication, not a runtime conflict. `JarvisAvatar` (`isStreaming` prop), `StatusPill` (per sub-agent in CreationCanvas), `Walkthrough` loading dots, generic `TetrisLoader`, `ConfirmActionButton` hold-progress. No simultaneous/competing indicators found within one flow. Batch 4's `{isThinking && !isActivelyStreaming && <ThinkingIndicator/>}` and 30ms batcher confirmed present and correct.

### 6.5 Auth Flow
`SplitChoice` → Google OAuth (`signInWithOAuth`) → `/auth/callback` (server route, `exchangeCodeForSession`, validates `next` starts with `/`) → `app/page.js` (Personal) or `business/chat/page.js` (Business, `user_id = 'user_' + uuid.replace(/-/g,'')`). `app/page.js` guards re-render races with `setUser(prev=>...)`/`setUserId(prev=>...)` and a `justOnboardedRef` documented-race-guard around `SIGNED_IN`/`SIGNED_OUT` during PKCE exchange. All per-user effects gated on `[userId]`, `userId` starts `null` — no observed request-before-auth race in current source.

### 6.6 Attachment Handling
| Mode | Cap | Over-cap behavior |
|---|---|---|
| Personal (`app/page.js`) | 25MB/file, max 5 | Friendly toast `"{file} is over the 25MB limit"`, file skipped |
| Business (`ai-prompt-box.tsx::addFiles`, used by ChatCanvas) | 20MB/file, max 5, type allowlist | **CONFIRMED: silently filtered via `.filter()` — NO toast, NO feedback.** User has no indication a file was dropped |

---

## 7. Confirmed-Present Fixes From Prior Batches (not re-flagged)

| Batch | Fix | Status |
|---|---|---|
| 2 | Buffer connector replaces Metricool, wired into `WRITE_ACTIONS`/`tool_builder`/`tool_executor` | ✅ present |
| 4 | True SSE streaming in business chat, `status:thinking`/`spinning up` events, 30ms batcher, `ThinkingIndicator` gating | ✅ present |
| 5 | Farida mode (Business `farida_loader.py`/`farida.md` + Personal `farida_personal_loader.py`/`farida.md`) | ✅ present, isolated |
| 6 | `creationDetector.js` paste guard + `INGEST_BLOCKLIST`; `create.py::_is_website_build`/`_INGEST_RE`; `chat.py max_tokens=8192` + truncated-tool_use guard; `deploy_pipeline.py` GitHub 422 retry (`-v2/-v3/-v4`) | ✅ present |
| 6b | `ChatCanvas.js` `hasAttachments` guard bypasses show-me-how/creation routing; `name` field on attachments | ✅ present |

---

## 8. Test Harness (Phase 0 deliverable)

- `backend/tests/conftest.py` — loads `.env.test` (throwaway values), stubs the `mem0` module (see below), provides a `client` fixture (`TestClient(backend.main.app)`).
- `.env.test` — `ANTHROPIC_API_KEY` set to a placeholder (required so `backend/main.py` doesn't `RuntimeError` on import); Supabase/connector keys left empty so routes take their documented "not configured" fallback branches.
- **`mem0` stub**: `conftest.py` installs a fake `mem0` module into `sys.modules` (`MemoryClient` with no-op `__init__`/`add`/`search`/`get_all`) before `backend.main` is imported. Without this, `backend.main` cannot be imported at all in a credential-less environment — see the new defect #8 in §9, discovered while building this harness.
- **Dev-environment dependency gap**: 8 packages declared in `requirements.txt` (`apscheduler`, `supabase`, `reportlab`, `pypdf`, `python-docx`, `cartesia`, `deepgram-sdk`, `trafilatura`) were **not installed** in this dev environment before Phase 0 — `backend.main` could not be imported until `pip install -r requirements.txt` was run. The existing 61 tests never noticed because none of them import `backend.main`. Worth a setup-doc note (out of scope to act further in Phase 0).
- `backend/tests/test_smoke_routes.py` — hits every parameter-free/dummy-`user_id` GET route, asserts status in each route's documented acceptable set + valid JSON with expected top-level keys.
- New regression tests for previously-fixed bugs (Batch 6) that had no automated coverage:
  - `test_creation_routing_guards.py` — `_is_website_build`/`_INGEST_RE` paste-guard matrix (mirrors Batch 6 acceptance notes).
  - `test_deploy_pipeline_422_retry.py` — GitHub 422 collision retries through `-v2`/`-v3`; non-422 errors do not retry.
- Existing 61 tests (Buffer connector, deploy pipeline pending, Farida ×2) still pass — no regressions.

**Frontend test infrastructure: absent.** `frontend/package.json` has no `test` script and no Jest/Vitest/Playwright/Testing-Library dependency. The "attachment drop" (Batch 6b) and "readiness polling" (§6.2) bugs are frontend-only and currently **cannot** be regression-tested without adding a JS test runner. Recommended for a later phase (flagged, not actioned in Phase 0 per "change no behavior yet").

---

## 9. Prioritized Defect List (severity × frequency)

Ranked for Phase 1+ triage. "Frequency" = how often a real user/session would hit the code path.

| # | Defect | Severity | Frequency | Where |
|---|---|---|---|---|
| 1 | **`intent_classifier._classify_with_haiku` makes a synchronous `httpx.post` (8s timeout) inside `async build_system_prompt`** — blocks the entire FastAPI worker's event loop for up to 8s on any business chat turn where keyword-matching finds <2 sections. Likely a direct contributor to "feels slow." | HIGH | HIGH (every novel-phrasing business message) | `backend/lib/business/intent_classifier.py`, called from `system_prompt_builder.py:~355` |
| 2 | **`/api/proactive/check/{user_id}` (polled every 5 min by Personal frontend) calls `jarvis_think` with no try/except**, and the due-reminder note is only marked done *after* that call succeeds — a single Anthropic hiccup causes a raw 500 every 5 minutes indefinitely for that user, with the reminder stuck "due" forever. | HIGH | HIGH (every active Personal user, every 5 min, until it breaks) | `backend/routes/proactive_routes.py` |
| 3 | **No authentication/authorization on any Personal route** — `user_id` is fully client-supplied (body/path/query/form/WS-header) with zero session verification across `/api/history`, `/api/memory`, `/api/notes`, `/api/user/model`, `/api/user-preferences`, voice tools, etc. Cross-user data read/write (IDOR-class). | CRITICAL | Always-present risk | All of `backend/routes/*.py` (Personal) |
| 4 | **`/api/debug/last-error` is unauthenticated** and returns the last 20 full Python tracebacks + first 200 chars of real user messages. | CRITICAL | Always-present risk, trivial to hit | `backend/routes/chat.py` |
| 5 | **No `/health` endpoint and no global exception handler** — Render/uptime monitoring can't detect "running but degraded" (Supabase down, Anthropic key revoked), and any unhandled exception (several enumerated below) returns a raw, inconsistent 500. Blocks all of Phase 6. | HIGH | Always-present (monitoring gap) | `backend/main.py` |
| 6 | **Business attachments silently dropped if >20MB or unsupported type** — `ai-prompt-box.tsx::addFiles` filters with zero user feedback (Personal mode shows a toast for the equivalent case). User believes the file was sent. | MEDIUM-HIGH | MEDIUM (any large/odd-format attachment) | `frontend/components/ui/ai-prompt-box.tsx:496-514` |
| 7 | **`/business/deploy-status` reports `{"state":"BUILDING"}` when the underlying Vercel connector call itself fails (`ok=False`)** — a persistent connector/auth failure is indistinguishable from "still building," so the frontend's deploy poller (5s × 6min) just times out vaguely instead of surfacing the real error ("deploy vanish"-class). | MEDIUM-HIGH | MEDIUM (any Vercel API/auth issue during deploy) | `backend/routes/business/create.py` (`/business/deploy-status`) |
| 8 | **`backend/memory.py` instantiates `mem0.MemoryClient(...)` at module-import time, which makes a live HTTP call to `api.mem0.ai/v1/ping`** — missing/invalid `MEM0_API_KEY` *or* a Mem0-side outage at boot crashes the entire app (Personal + Business) with an opaque `ValueError`/connection error, not a clear message. Discovered while building this harness (§8) — required stubbing `mem0` just to import `backend.main`. Same total-outage blast radius as #9 below, but broader trigger surface (third-party network dependency at every boot/restart). | HIGH | LOW (boot/restart-time only, but every Render redeploy is a boot) | `backend/memory.py:14` |
| 9 | **App-wide hard crash if `ANTHROPIC_API_KEY` is unset** — takes down Business/OS1 routes too, for a Personal-only dependency. Single env-var typo = total outage of both products. | HIGH | LOW (config-time only, but blast radius = everything) | `backend/main.py:36-39` |
| 10 | **Personal `jarvis_think()` tool loop is single-pass** — a second round of `tool_use` after the first tool result is silently dropped (only its text, possibly empty, is returned → `_FALLBACK_EMPTY`). Individual tool-call exceptions inside the loop are not caught, aborting the whole response. Business's `chat.py` has none of these gaps (§4). | MEDIUM-HIGH | MEDIUM (any Personal chat needing 2+ chained tool calls, or any tool throwing) | `backend/llm.py` |
| 11 | **OAuth `state` = raw, unsigned `user_id`** in both `/api/google/callback` and `/business/connections/google/callback` — combined with #3, allows binding a Google account's tokens to an arbitrary `user_id` via a forged callback. | MEDIUM-HIGH | LOW (requires deliberate action) | `backend/routes/google_auth_routes.py`, `backend/routes/business/connections.py` |
| 12 | **`supabase_project__run_sql` (arbitrary SQL on the user's own Supabase project) is not in `WRITE_ACTIONS`** — the hold-to-confirm flow never triggers; the only safeguard is a prompt instruction to "confirm before schema changes." | MEDIUM-HIGH | LOW (only if user connects this connector) | `backend/lib/business/connectors/supabase_project_connector.py`, `backend/routes/business/chat.py` |
| 13 | **Local-disk state on (likely ephemeral/multi-instance) Render**: `data/notes/{user_id}_notes.json` (no file locking, race on concurrent tabs), `data/last_interaction/`, `local_agent_routes._connected_agents` in-memory dict (breaks across instances). | MEDIUM | MEDIUM (notes/reminders feature; local-agent feature) | `backend/routes/notes_routes.py`, `proactive_routes.py`, `local_agent_routes.py`, `main.py` lifespan |
| 14 | **`/business/operator/status/stream` SSE has no terminal sentinel after its 10-minute (600×1s) cap** — generator just stops; frontend `EventSource` sees a silent close with no "timeout"/`[DONE]` signal. | MEDIUM | LOW (only very long operator runs) | `backend/routes/business/operator_routes.py` |
| 15 | **Several unhandled-exception 500 paths**: `documents.py` Supabase insert, `files_routes.py` image-description httpx call, `chat.py:/chat/artifact` httpx call, `google_auth_routes.py:/google/callback`, `export.py` PDF build. None leak secrets, but all violate "no silent/raw 500s." | MEDIUM | LOW-MEDIUM each, but numerous | scattered, see §1 |
| 16 | **Deploy-status frontend poller doesn't `clearInterval` on fetch exception** — retries every 5s for up to 6 minutes on a network blip during deploy, no backoff/escalation. | LOW-MEDIUM | LOW | `ChatCanvas.js startDeployPolling` |
| 17 | **Inconsistent error-response shapes** across the whole backend (`{ok:false,error}` vs raw `HTTPException` vs `{"result":"...error..."}` 200 vs swallowed-to-default). `str(e)` leaked into 200/500 bodies in ~10+ places (`user_preferences.py`, `voice_routes.py`, `conversations.py`, `chat.py _debug`). This is the Phase 1 "one error contract" item. | LOW-MEDIUM | HIGH (pervasive) | many files |
| 18 | **Two hardcoded Anthropic model strings outside `llm.py`** (`claude-sonnet-4-20250514` in `chat.py:/chat/artifact` vs `claude-sonnet-4-6` in `files_routes.py`/`llm.py`), each with its own ad-hoc `httpx` client (different timeouts, no retries, bypassing the shared `_client`). | LOW | LOW | `backend/routes/chat.py`, `backend/routes/files_routes.py` |
| 19 | **`/api/usage` hardcoded fallback `limit:15` vs actual `DAILY_MESSAGE_LIMIT=32`** when Supabase is unconfigured. | LOW | LOW (only when Supabase down) | `backend/routes/chat.py` |
| 20 | **`/voice/list-voices` blocks the event loop** with a synchronous `client.voices.list()` inside `async def` (every other Cartesia call uses `asyncio.to_thread`). | LOW | LOW (voice settings page only) | `backend/routes/voice_routes.py` |
| 21 | Misc low-severity: dead `intent_detector.py` (lacks Batch 6 guards, not wired up — latent trap); `_CONNECTOR_ACTIONS["canva"]` advertises non-existent methods; `conversations.py` PATCH/`/messages` success-vs-error shape mismatch; `/refine` double-signal (`error`+`complete`) on empty result; duplicate `ThinkingIndicator` implementations (Personal/Business); `ConfirmActionButton` interval lacks unmount cleanup; `PendingActionsStack.js` PATCH omits `user_id` (likely dead UI); **readiness-polling-flood claim unconfirmed in source** — needs live verification (§6.2); `user_id_to_uuid` duplicated across 6+ files (DRY only, not a bug). | LOW | varies | various |

### Suggested Phase ordering implied by this list
- **Phase 1 (reliability/error contract)**: #2, #5, #8, #9, #15, #17, #14, #10 (tool-loop parity for Personal).
- **Phase 2 (auth/data integrity)**: #3, #4, #11, #12, #13.
- **Phase 3 (core flows)**: #6, #7, #10 (attachments/creation/deploy already largely fixed by Batch 6/6b — close remaining gaps).
- **Phase 4 (performance)**: #1 (highest-impact perceived-speed fix), #16, live-verify readiness polling (#21).
- **Phase 5 (working indicators)**: mostly already solid (Batch 4) — close #21 duplication only if time allows.
- **Phase 6 (regression/monitoring)**: depends on #5 (`/health`) being done first; wire Sentry/structured logging; load smoke.

---

## 10. What Phase 0 Did Not Cover (explicitly out of scope here)

- Live verification against the deployed Render/Vercel instances (Network tab, actual latency numbers) — needed for #1, #20 (readiness), and Phase 4 baselines generally.
- `backend/lib/business/operator/*` and `backend/lib/business/risk/*` internals (only their route-level entry points were audited).
- Frontend bundle-size / re-render profiling (Phase 4/5).
- Load testing (Phase 6).
