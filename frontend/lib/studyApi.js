// Study Mode API — separate study notes + multi-chat storage.
// Backend routes live in backend/routes/study_routes.py.

const BACKEND = 'https://jarvis-backend-4oz6.onrender.com'

async function j(res) {
  if (!res.ok) throw new Error(`${res.status} ${await res.text().catch(() => '')}`)
  return res.json()
}

// ── Capture (photo → extracted, categorized note) ───────────────────────────
export async function captureStudyNote(userId, imageBase64, imageType) {
  return j(await fetch(`${BACKEND}/api/study/capture/${userId}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ image_base64: imageBase64, image_type: imageType }),
  }))
}

// ── Notes ──────────────────────────────────────────────────────────────────
export async function listStudyNotes(userId) {
  return j(await fetch(`${BACKEND}/api/study/notes/${userId}`)).then(d => d.notes || [])
}
export async function createStudyNote(userId, content, category) {
  return j(await fetch(`${BACKEND}/api/study/notes/${userId}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content, category }),
  })).then(d => d.note)
}
export async function updateStudyNote(userId, noteId, patch) {
  return j(await fetch(`${BACKEND}/api/study/notes/${userId}/${noteId}`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  })).then(d => d.note)
}
export async function deleteStudyNote(userId, noteId) {
  return j(await fetch(`${BACKEND}/api/study/notes/${userId}/${noteId}`, { method: 'DELETE' }))
}

// ── Chats ──────────────────────────────────────────────────────────────────
export async function listStudyChats(userId) {
  return j(await fetch(`${BACKEND}/api/study/chats/${userId}`)).then(d => d.chats || [])
}
export async function getStudyChat(userId, chatId) {
  return j(await fetch(`${BACKEND}/api/study/chats/${userId}/${chatId}`)).then(d => d.chat)
}
export async function createStudyChat(userId, { title, messages } = {}) {
  return j(await fetch(`${BACKEND}/api/study/chats/${userId}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, messages }),
  })).then(d => d.chat)
}
export async function updateStudyChat(userId, chatId, patch) {
  return j(await fetch(`${BACKEND}/api/study/chats/${userId}/${chatId}`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  })).then(d => d.chat)
}
export async function deleteStudyChat(userId, chatId) {
  return j(await fetch(`${BACKEND}/api/study/chats/${userId}/${chatId}`, { method: 'DELETE' }))
}
