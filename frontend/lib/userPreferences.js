const BACKEND = 'https://jarvis-backend-4oz6.onrender.com'

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

export async function getBusinessUser(userId) {
  if (!userId) return { exists: false }
  try {
    const res = await fetch(`${BACKEND}/api/business-users/${encodeURIComponent(userId)}`)
    if (!res.ok) return { exists: false }
    return await res.json()
  } catch {
    return { exists: false }
  }
}

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
    return res.ok
  } catch {
    return false
  }
}
