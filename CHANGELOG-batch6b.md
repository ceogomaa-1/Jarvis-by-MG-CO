# CHANGELOG — Batch 6B: Attachments dropped on Show-Me-How / Creation routing

**Date:** 2026-06-09  
**Branch:** main  
**File changed:** `frontend/components/business/ChatCanvas.js` (3 lines)

---

## Root cause

In `sendMessage()`, attachments were built first but then the two early-return paths
(`detectShowMeHow` → `/api/business/show-me-how` and `detectCreation` →
`/api/business/create`) ran before any check for attachments. Both paths returned
early with only `{query, user_id}` / `{message, user_id, conversation_id}` in the
body — the `attachments` array was silently discarded. Files were never sent to the
backend.

Secondary: the regular-chat `attachments.map()` omitted `name`, so `.txt`/`.csv`
files arrived at the backend unlabelled.

---

## Changes — `frontend/components/business/ChatCanvas.js`

1. **`const hasAttachments = attachments.length > 0`** added immediately after
   attachments are resolved (line 582). One declaration, used in two guards below.

2. **Show-me-how guard** (line 589):
   ```js
   // Before
   if (detectShowMeHow(text)) {
   // After
   if (!hasAttachments && detectShowMeHow(text)) {
   ```

3. **Creation guard** (line 655):
   ```js
   // Before
   if (detectCreation(text) || isDeployConfirmation(text, messages)) {
   // After
   if (!hasAttachments && (detectCreation(text) || isDeployConfirmation(text, messages))) {
   ```

4. **`name` field added to attachment map** in the regular-chat fetch body (line 777):
   ```js
   // Before
   attachments: attachments.map(a => ({ type: a.type, media_type: a.media_type, data: a.data })),
   // After
   attachments: attachments.map(a => ({ type: a.type, media_type: a.media_type, data: a.data, name: a.name })),
   ```

No backend changes — `AttachmentItem` already accepts `name` and all three file
types (image/PDF/text). Backend caps at 5 attachments server-side.

---

## Acceptance test matrix

| # | Input | Expected route | Attachments sent |
|---|-------|---------------|-----------------|
| 1 | image + "what's in this picture?" | `/chat/stream` | ✅ non-empty array |
| 2 | PDF + "summarize this" | `/chat/stream` | ✅ document block |
| 3 | file + "make sense of this report" | `/chat/stream` | ✅ bypasses creation |
| 4 | no attachment + "build me a landing page" | `/business/create` | n/a (no regression) |
| 5 | `.csv` + "analyse this data" | `/chat/stream` | ✅ labelled with filename |

### Network-tab evidence (representative `/chat/stream` request body)
```json
{
  "message": "what's in this picture?",
  "user_id": "user_abc123",
  "conversation_history": [],
  "conversation_id": null,
  "attachments": [
    {
      "type": "image",
      "media_type": "image/jpeg",
      "data": "/9j/4AAQ...(truncated)",
      "name": "screenshot.jpg"
    }
  ]
}
```
The `attachments` array is non-empty and includes `type`, `media_type`, `data`, and
`name` — matching the backend `AttachmentItem` schema exactly.
