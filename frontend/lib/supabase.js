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

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY

// Keep public routes and the preview renderable when auth is intentionally not
// configured. Auth-dependent screens already treat a null client as signed out.
export const supabase =
  typeof window !== 'undefined' && supabaseUrl && supabaseAnonKey
    ? createBrowserClient(supabaseUrl, supabaseAnonKey, {
        cookieOptions: authCookieOptions(),
      })
    : null
