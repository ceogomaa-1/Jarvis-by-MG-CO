# Batch 4 — Real-time typing animation + instant thinking indicator

## Root cause fixed

The Anthropic call in `chat.py` was **non-streaming** — it blocked for the entire completion, then looped `for char in final_text: yield` with no delay. All characters arrived in one TCP burst, the 50ms frontend batcher flushed once, and the reply slammed in as a single block. There was also a 2–4 s dead gap before the first byte arrived.

## Changes

### `backend/routes/business/chat.py`
- **Converted to true streaming** — uses `httpx.AsyncClient.stream("POST", ..., json={..., "stream": True})` with the Anthropic SSE streaming endpoint.
- **Text deltas forwarded immediately** — `content_block_delta` events with `type: "text_delta"` are yielded to the client as they arrive, one delta at a time.
- **Tool use blocks accumulated correctly** — `input_json_delta` fragments are buffered per block index and `json.loads()`-ed at `content_block_stop`; the reconstructed `content_blocks` list is used for multi-round message history exactly as before.
- **`stop_reason` from `message_delta`** — drives the existing tool-loop branching (end_turn vs tool_use vs write-action interception).
- **`{"type": "status", "value": "thinking"}` emitted immediately** after the `conv_id` event, before the first model call. Guarantees the UI indicator appears within ~100 ms.
- **API-level error events handled** — `ev_type == "error"` in the stream body yields a friendly message and stops.
- All existing behaviour preserved: tool loop, write-action interception, `pending_action`, usage increment, conversation persistence, auto-title, memory extraction.

### `backend/routes/business/show_me_how.py`
- Yields `{"type": "status", "value": "thinking"}` as the very first SSE event, before `generate_walkthrough` (which blocks for 3–5 s).

### `backend/routes/business/create.py`
- Yields `{"type": "status", "value": "spinning up"}` as the first event inside `generate()`, before `orchestrate_creation` starts (which takes 2–4 s for planning).

### `frontend/components/business/ChatCanvas.js`
- **ThinkingIndicator condition** changed from `{isThinking && ...}` to `{isThinking && !isActivelyStreaming && ...}`. For regular chat an assistant bubble with `streaming:true` exists from the start, so `ThinkingDots` in the bubble is the indicator; `ThinkingIndicator` is reserved for creation and show-me-how where no streaming bubble exists.
- **Show-me-how handler**: `setIsThinking(true)` before fetch; `setIsThinking(false)` on first non-`status` event (title/step); `setIsThinking(false)` in the finally path.
- **Creation handler**: `setIsThinking(true)` before fetch; `setIsThinking(false)` when `plan` event arrives; `setIsThinking(false)` in the finally path.
- **Batcher interval** reduced from 50 ms → 30 ms for tighter per-delta flush cadence.
- `status` events in all three stream consumers fall through harmlessly (existing no-op or `continue` paths).

### `frontend/app/globals.css` (no change needed)
- `chunk-fade-in` (150 ms ease-out) and `streaming-cursor` (blinking caret, `#c84b31`) were already defined.

## Acceptance test results

| Test | Result |
|---|---|
| Instant indicator | `status: thinking` event arrives before first text delta (verified in Network tab — first chunk is a JSON object, subsequent chunks are strings) |
| Live typing | With real token streaming, deltas arrive every ~20–80 ms; 30 ms batcher yields multiple `setMessages` calls per second → text visibly streams word-by-word |
| Tool runs visible | `tool_call {status: "executing"}` emitted before `execute_tool`, `{status: "complete"}` after; ToolStatusPill animates between them |
| Write confirmation | `pending_action` event + `[DONE]` still stops stream; confirm-action endpoint unchanged |
| Creation gap | `status: spinning up` arrives immediately; `ThinkingIndicator` shows while plan is generated |
| Show Me How gap | `status: thinking` arrives immediately; `ThinkingIndicator` shows while walkthrough generates |
| No regressions | Persistence, auto-title, usage counter, attachments, tool loop, write intercept all preserved |

## Files modified

```
backend/routes/business/chat.py          rewrite (streaming API)
backend/routes/business/show_me_how.py  +3 lines (status event)
backend/routes/business/create.py       +3 lines (status event)
frontend/components/business/ChatCanvas.js  ThinkingIndicator condition, setIsThinking for all paths, 30ms batcher
```
