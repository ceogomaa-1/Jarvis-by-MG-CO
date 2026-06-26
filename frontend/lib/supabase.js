import { createBrowserClient } from '@supabase/ssr'

// Share the Supabase auth cookie across the apex (jarvismgco.com) AND all subdomains
// (www.jarvismgco.com) so a session created on one host is valid on the other. Without this
// the cookie is host-only and switching apex↔www (e.g. Personal → OS1) drops the session and
// loops the user back to login. Production only — localhost and *.vercel.app previews keep a
// host-only cookie (no domain) so they're unaffected.
function authCookieOptions() {
  if (typeof window === 'undefined') return undefined
  const host = window.location.hostname
  if (host.endsWith('jarvismgco.com')) {
    return { domain: '.jarvismgco.com', path: '/', sameSite: 'lax', secure: true }
  }
  return undefined
}

export const supabase =
  typeof window !== 'undefined'
    ? createBrowserClient(
        process.env.NEXT_PUBLIC_SUPABASE_URL,
        process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
        { cookieOptions: authCookieOptions() }
      )
    : null
