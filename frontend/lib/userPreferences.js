import { BACKEND } from '@/lib/backend'

export async function getJarvisMode(userId) {
  if (!userId) return null
  try {
    const res = await fetch(`${BACKEND}/api/user-preferences/${userId}`)
    if (!res.ok) return undefined  // server error — caller treats as unknown, not "no mode"
    const data = await res.json()
    return data.jarvis_mode || null
  } catch {
    return undefined  // network error — same
  }
}

export async function setJarvisMode(userId, mode) {
  if (!userId) return false
  try {
    const res = await fetch(`${BACKEND}/api/user-preferences`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: userId, jarvis_mode: mode }),
    })
    return res.ok
  } catch {
    return false
  }
}

export async function createBusinessUser({ userId, email, companyName, industry, role }) {
  try {
    const res = await fetch(`${BACKEND}/api/business-users`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: userId,
        email,
        company_name: companyName,
        industry,
        role,
      }),
    })
    return res.ok
  } catch {
    return false
  }
}

// Returns { exists: true, ... } or { exists: false } only when the lookup
// definitively succeeded. On a network error or server error, returns
// { exists: null } — callers must NOT treat that as "no profile" and redirect
// into onboarding, since that turns a transient failure into a redirect loop.
export async function getBusinessUser(userId) {
  if (!userId) return { exists: null }
  try {
    const res = await fetch(`${BACKEND}/api/business-users/${encodeURIComponent(userId)}`)
    if (!res.ok) return { exists: null }
    return await res.json()
  } catch {
    return { exists: null }
  }
}

// Returns { ok: true, business_user: {...} } on confirmed success, or
// { ok: false } on failure. Callers must verify ok+business_user before
// redirecting to chat — a 200 with ok:false used to be treated as success,
// leaving the chat page's first-timer check failing forever (redirect loop).
export async function completeBusinessOnboarding({ userId, email, name, industry, customIndustry, companyName, mission }) {
  try {
    const res = await fetch(`${BACKEND}/api/business/onboard/complete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: userId,
        email,
        name,
        industry,
        custom_industry: customIndustry || null,
        company_name: companyName,
        mission: mission || null,
      }),
    })
    if (!res.ok) return { ok: false }
    const data = await res.json()
    return data?.ok && data?.business_user ? data : { ok: false }
  } catch {
    return { ok: false }
  }
}
