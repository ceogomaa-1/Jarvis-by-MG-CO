const BACKEND = 'https://jarvis-backend-4oz6.onrender.com'

export async function getJarvisMode(userId) {
  if (!userId) return null
  try {
    const res = await fetch(`${BACKEND}/api/user-preferences/${userId}`)
    if (!res.ok) return null
    const data = await res.json()
    return data.jarvis_mode || null
  } catch {
    return null
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
