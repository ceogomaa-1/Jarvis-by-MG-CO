# CHANGELOG — Batch 44: Real Estate Operator Suite

**Date:** 2026-06-10
**Branch:** feat/batch-43-45
**Scope:** New Real Estate-only toolset (6 tools) gated behind industry detection,
plus the GoHighLevel connector upgrade and document-export plumbing they depend on.

---

## What shipped

A dedicated toolset for users whose business profile resolves to `real_estate.md`
(via `bible_loader.get_industry_filename`). Non-RE users see none of this — the
tools are appended in `tool_builder.build_tools_for_user()` only when
`real_estate.profile.is_real_estate_user(user_id)` is true, independent of which
connectors they have active.

### 1. GoHighLevel connector — v2 API + stale-lead scanner
- `backend/lib/business/connectors/gohighlevel_conn.py`: added v2
  (`services.leadconnectorhq.com`) support — Private Integration token +
  Location ID, alongside the existing v1 (legacy API key) actions.
- `realestate__ghl_scan_stale_leads` (`days_stale` default 14, `limit` default 25):
  paginates contacts, pulls last note per contact, classifies (cheap/Haiku model)
  whether each needs a follow-up, and returns a ranked list with drafted
  follow-up messages.
- `realestate__ghl_add_note`: logs a note back to a CRM contact.

### 2. Offer & Amendment Drafter
- `realestate__draft_offer_document` (`type`: offer|amendment) — LLM drafts
  Parties/Property/Terms/Conditions/Signatures, rendered to a branded PDF
  (MG&CO dark cover + clean white body) via the new
  `pdf_export.generate_branded_document_pdf()`. Always appends:
  *"Draft prepared by Jarvis OS1 — review with your brokerage/legal counsel
  before presenting."*

### 3. Showing Booker
- `realestate__book_showing` — creates a Google Calendar event
  (`Showing — {address} w/ {client}`), and if GoHighLevel is connected and a
  matching contact is found, logs a note back to the CRM.

### 4. Seller Contact Research
- `realestate__research_seller_contacts` — web search + (if available) headless
  Playwright page reads of top results, LLM-extracted into structured contacts
  with source URLs and confidence. Public sources only, robots.txt-respecting,
  10s/page timeout, max 5 pages. Degrades gracefully (web-search-only) if
  Playwright isn't installed/available at runtime.

### 5. PDF Form Auto-Fill
- `realestate__fill_pdf_form` (`doc_id`, `known_values`) — reads AcroForm fields
  via `pypdf`, LLM maps field names to the user's profile/conversation values,
  fills and returns a download link. If the PDF has no fillable fields, returns
  an honest breakdown of what Jarvis *would* fill and where.
- Chat wiring: when a Real Estate user attaches a PDF, `chat.py` stashes it via
  `document_store.save_document()` and tells Claude the resulting `doc_id` so it
  can call this tool when the user says "fill this".

### 6. PowerPoint Generator
- `realestate__generate_presentation` (`type`: listing|cma|buyer_guide|custom) —
  one reusable MG&CO-branded `python-pptx` template (dark title slide, blue
  accent bars, "Powered by Jarvis OS1" footer). LLM writes the slide content,
  python-pptx renders it, returned as a download link.

### Plumbing added for all of the above
- `backend/lib/business/document_store.py` + `GET /api/business/documents/{doc_id}`
  — temp-dir document store + download route, used by the PDF/PPTX tools.
- `backend/lib/business/pdf_export.py`: new `generate_branded_document_pdf()`
  (dark MG&CO cover page + clean white body, footer note).
- `backend/lib/business/real_estate/` package: `profile.py` (industry/profile
  lookup + `is_real_estate_user`), `llm.py` (shared Claude call helper), and one
  module per tool.
- `backend/lib/business/real_estate/tools.py`: `REAL_ESTATE_TOOLS` definitions +
  `execute_real_estate_tool()` dispatcher.

### Wiring
- `tool_builder.build_tools_for_user()`: appends `REAL_ESTATE_TOOLS` for RE users.
- `tool_executor.execute_tool()`: routes `realestate__*` tool names to
  `execute_real_estate_tool()` before the connector lookup (these tools manage
  their own connector dependencies).
- `chat.py`: added `realestate__ghl_add_note` and `realestate__book_showing` to
  `WRITE_ACTIONS` (hold-to-confirm before they run), with human-readable
  `_describe_action()` labels; PDF-attachment doc_id injection for RE users.
- `system_prompt_builder.py`: new `_REAL_ESTATE_CAPABILITIES` block, appended to
  the system prompt only for RE-industry users, telling Jarvis to proactively
  offer these six capabilities.

---

## Dependencies added (`requirements.txt`)
- `python-pptx>=0.6.23`
- `playwright>=1.40.0`

Both installed cleanly in this environment (`python-pptx-1.0.2`, `playwright-1.60.0`).

---

## ⚠️ ACTION REQUIRED FROM MOHAMED

1. **Render build command** — Playwright's package installs via pip, but its
   browser binary (Chromium) does not. Update the Render build command for the
   backend service to install it after `pip install -r requirements.txt`, e.g.:

   ```
   pip install -r requirements.txt && playwright install chromium --with-deps
   ```

   Without this, `realestate__research_seller_contacts` will gracefully degrade
   to web-search-only (it does **not** crash) — but seller-research quality will
   be lower until the build command is updated.

2. **GoHighLevel credentials** — the client needs to open **Connections** and
   enter:
   - **Private Integration Token** (GHL → Settings → Private Integrations)
   - **Location ID** (GHL → Settings → Business Profile)

   Until both are set, `realestate__ghl_scan_stale_leads` and
   `realestate__ghl_add_note` return a friendly "GoHighLevel isn't connected
   yet — open Connections and add your Private Integration token + Location ID."
   message — no crash. The Connections UI auto-generates the new Location ID
   field from the connector manifest, so no frontend changes were needed.

---

## Verification performed

- `python -c "from backend.main import app"` — **0 import errors**, 94 routes registered.
- Tool gating: mocked `is_real_estate_user` — non-RE user gets **0** of the 6
  RE tools, RE user gets **all 7** tool definitions (6 spec'd tools; GHL scanner
  + add_note count as 2 of the 7 entries).
- `realestate__ghl_scan_stale_leads` / `ghl_add_note` with no GHL connection
  configured → friendly "GoHighLevel isn't connected yet…" error, no crash,
  via both the direct function and the `execute_real_estate_tool` dispatcher.
- PPTX generation (`generate_presentation`, mocked LLM): produced a valid
  4-slide `.pptx` (title + content + table + content slides), saved/loaded via
  `document_store`.
- PDF generation (`draft_offer_document`, mocked LLM): produced a valid 2-page
  branded PDF with the liability note, saved/loaded via `document_store`.
- `npm run build` (frontend) — **exit 0**, all 16 routes built (the
  `onnxruntime-web` "Critical dependency" warnings are pre-existing and
  unrelated to this change).

---

## Not done in this batch

- Production push (`main`) — held pending explicit user confirmation per
  standing process rules on shared/production state. Pushed to the preview
  branch (`feat/batch-43-45`) only.
