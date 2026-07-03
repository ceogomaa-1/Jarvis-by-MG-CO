// Where should the user land after OAuth? Supabase only honors our redirectTo when
// it passes the dashboard allowlist — when it doesn't, the browser gets dumped at the
// Site URL root with the auth code and every page-level `next` param is lost. This
// stash survives that fallback (same-origin localStorage), so the root page can
// finish the journey instead of bouncing the user into the logged-out /welcome loop.
const KEY = 'jarvis_auth_next'
const MAX_AGE_MS = 10 * 60 * 1000 // OAuth round-trips take seconds; anything older is stale

export function stashAuthNext(path) {
  try {
    localStorage.setItem(KEY, JSON.stringify({ path, ts: Date.now() }))
  } catch {}
}

// One-shot read: returns a fresh, same-site relative path or null. Always clears.
export function popAuthNext() {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return null
    localStorage.removeItem(KEY)
    const { path, ts } = JSON.parse(raw)
    if (typeof path !== 'string' || !path.startsWith('/') || path.startsWith('//')) return null
    if (!ts || Date.now() - ts > MAX_AGE_MS) return null
    return path
  } catch {
    return null
  }
}

// True while the URL still carries OAuth material the Supabase client needs to
// consume (?code= / ?error= from PKCE, #access_token from implicit links).
export function urlHasAuthParams() {
  if (typeof window === 'undefined') return false
  const params = new URLSearchParams(window.location.search)
  return !!(
    params.get('code') ||
    params.get('error') ||
    params.get('error_description') ||
    (window.location.hash && window.location.hash.includes('access_token'))
  )
}
