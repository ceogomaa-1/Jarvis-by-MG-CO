import { v4 as uuidv4 } from 'uuid'
import { supabase } from './supabase'

export const ATTACHMENTS_BUCKET = 'personal-chat-attachments'
const SIGNED_URL_TTL = 60 * 60 // 60 minutes

// Mirrors backend `_user_id_to_uuid` — converts 'user_<32hex>' back to the
// dashed UUID that matches `auth.uid()`, so storage paths satisfy the
// personal-chat-attachments RLS policy: (storage.foldername(name))[1] = auth.uid()::text
export function userIdToUuid(userId) {
  const hex = (userId || '').replace(/^user_/, '')
  if (hex.length === 32 && /^[0-9a-f]+$/i.test(hex)) {
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
  }
  return userId
}

// Uploads a file under {user_uuid}/{uuid}-{filename}.
// Returns the storage path, or null if upload failed (caller falls back to
// in-memory preview only — the attachment is still sent to Claude as base64).
export async function uploadChatAttachment(file, userId) {
  if (!supabase || !userId) return null
  const uuid = userIdToUuid(userId)
  const safeName = file.name.replace(/[^a-zA-Z0-9._-]/g, '_')
  const path = `${uuid}/${uuidv4()}-${safeName}`
  try {
    const { error } = await supabase.storage.from(ATTACHMENTS_BUCKET).upload(path, file)
    if (error) {
      console.error('Attachment upload failed:', error)
      return null
    }
    return path
  } catch (e) {
    console.error('Attachment upload error:', e)
    return null
  }
}

export async function getAttachmentSignedUrl(path) {
  if (!supabase || !path) return null
  try {
    const { data, error } = await supabase.storage
      .from(ATTACHMENTS_BUCKET)
      .createSignedUrl(path, SIGNED_URL_TTL)
    if (error) {
      console.error('Signed URL failed:', error)
      return null
    }
    return data?.signedUrl || null
  } catch (e) {
    console.error('Signed URL error:', e)
    return null
  }
}

export function isImageAttachment(att) {
  return (att?.media_type || att?.type || '').startsWith('image/')
}

export function formatFileSize(bytes) {
  if (!bytes) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

// Truncates a filename in the middle, preserving its extension.
export function truncateMiddle(name, maxLen = 26) {
  if (!name || name.length <= maxLen) return name || ''
  const dot = name.lastIndexOf('.')
  const ext = dot > 0 ? name.slice(dot) : ''
  const base = dot > 0 ? name.slice(0, dot) : name
  const keep = Math.max(maxLen - ext.length - 1, 2)
  const head = Math.ceil(keep / 2)
  const tail = Math.floor(keep / 2)
  return `${base.slice(0, head)}…${base.slice(base.length - tail)}${ext}`
}
