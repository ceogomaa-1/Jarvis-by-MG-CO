// Batch 56 — "What's New" announcements client.
// Shared by Jarvis Personal (app/page.js) and Jarvis OS1 (business ChatCanvas).

const BACKEND = 'https://jarvis-backend-4oz6.onrender.com'

export async function fetchAnnouncements(userId) {
  if (!userId) return { announcements: [], unread_count: 0, count: 0 }
  try {
    const res = await fetch(`${BACKEND}/api/announcements/${encodeURIComponent(userId)}`)
    if (!res.ok) return { announcements: [], unread_count: 0, count: 0 }
    return await res.json()
  } catch {
    return { announcements: [], unread_count: 0, count: 0 }
  }
}

export async function markAnnouncementSeen(userId, announcementId) {
  if (!userId || !announcementId) return false
  try {
    const res = await fetch(`${BACKEND}/api/announcements/${encodeURIComponent(userId)}/seen`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ announcement_id: announcementId }),
    })
    return res.ok
  } catch {
    return false
  }
}

export async function markAllAnnouncementsSeen(userId) {
  if (!userId) return false
  try {
    const res = await fetch(`${BACKEND}/api/announcements/${encodeURIComponent(userId)}/seen`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ all: true }),
    })
    return res.ok
  } catch {
    return false
  }
}
