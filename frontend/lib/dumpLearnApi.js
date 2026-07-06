// Dump Learn API — bins, items, explain, follow-up chat.
// Backend routes live in backend/routes/dump_learn_routes.py.

import { v4 as uuidv4 } from 'uuid'
import { BACKEND } from '@/lib/backend'
import { supabase } from '@/lib/supabase'
import { userIdToUuid } from '@/lib/attachments'

export const DUMP_LEARN_BUCKET = 'dump-learn-uploads'

async function j(res) {
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    let message = body
    try { message = JSON.parse(body).detail || body } catch { /* not JSON — use raw text */ }
    throw new Error(message || `Request failed (${res.status})`)
  }
  return res.json()
}

// ── Bins ───────────────────────────────────────────────────────────────────
export async function listBins(userId) {
  return j(await fetch(`${BACKEND}/api/dump-learn/bins/${userId}`)).then(d => d.bins || [])
}
export async function createBin(userId, title) {
  return j(await fetch(`${BACKEND}/api/dump-learn/bins/${userId}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  })).then(d => d.bin)
}
export async function getBin(userId, binId) {
  return j(await fetch(`${BACKEND}/api/dump-learn/bins/${userId}/${binId}`))
}
export async function getBinStatus(userId, binId) {
  return j(await fetch(`${BACKEND}/api/dump-learn/bins/${userId}/${binId}/status`))
}
export async function updateBin(userId, binId, patch) {
  return j(await fetch(`${BACKEND}/api/dump-learn/bins/${userId}/${binId}`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  })).then(d => d.bin)
}
export async function deleteBin(userId, binId) {
  return j(await fetch(`${BACKEND}/api/dump-learn/bins/${userId}/${binId}`, { method: 'DELETE' }))
}

// ── Items ──────────────────────────────────────────────────────────────────

// Uploads a file straight to the private dump-learn-uploads bucket (same
// convention as attachments.js) — the raw bytes never pass through our API
// server. Returns the storage path, or null on failure.
export async function uploadDumpLearnFile(file, userId) {
  if (!supabase || !userId) return null
  const uuid = userIdToUuid(userId)
  const safeName = file.name.replace(/[^a-zA-Z0-9._-]/g, '_')
  const path = `${uuid}/${uuidv4()}-${safeName}`
  const { error } = await supabase.storage.from(DUMP_LEARN_BUCKET).upload(path, file)
  if (error) {
    console.error('[DumpLearn] file upload failed', error)
    return null
  }
  return path
}

export function kindForFile(file) {
  const name = (file.name || '').toLowerCase()
  const type = file.type || ''
  if (type === 'application/pdf' || name.endsWith('.pdf')) return 'pdf'
  if (name.endsWith('.docx')) return 'docx'
  if (name.endsWith('.pptx')) return 'pptx'
  if (type.startsWith('image/')) return 'image'
  return null
}

export async function addItem(userId, binId, item) {
  return j(await fetch(`${BACKEND}/api/dump-learn/bins/${userId}/${binId}/items`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(item),
  })).then(d => d.item)
}

// High-level helper: given a raw File, uploads it then registers the item.
export async function addFileItem(userId, binId, file) {
  const kind = kindForFile(file)
  if (!kind) throw new Error(`Unsupported file type: ${file.name}`)
  const storage_path = await uploadDumpLearnFile(file, userId)
  if (!storage_path) throw new Error(`Upload failed for ${file.name}`)
  return addItem(userId, binId, {
    kind, storage_path, source_name: file.name,
    media_type: kind === 'image' ? file.type : undefined,
  })
}

export async function addUrlItem(userId, binId, url) {
  const isYoutube = /youtu\.?be/.test(url)
  return addItem(userId, binId, { kind: isYoutube ? 'youtube' : 'url', source_url: url, source_name: url })
}

export async function addTextItem(userId, binId, text, sourceName) {
  return addItem(userId, binId, { kind: 'text', text, source_name: sourceName || 'Pasted text' })
}

export async function deleteItem(userId, binId, itemId) {
  return j(await fetch(`${BACKEND}/api/dump-learn/bins/${userId}/${binId}/items/${itemId}`, { method: 'DELETE' }))
}

// ── Explain + follow-up chat ─────────────────────────────────────────────────
export async function explainBin(userId, binId, level) {
  return j(await fetch(`${BACKEND}/api/dump-learn/bins/${userId}/${binId}/explain`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ level }),
  }))
}

export async function askBin(userId, binId, question) {
  return j(await fetch(`${BACKEND}/api/dump-learn/bins/${userId}/${binId}/ask`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
  }))
}
