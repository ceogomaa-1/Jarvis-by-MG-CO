'use client'
import { useEffect } from 'react'
import { supabase } from '@/lib/supabase'
import { BACKEND } from '@/lib/backend'

// Batch 74 (Phase B): attach the Supabase access token to every call to the Rue
// backend, so the backend can verify the caller instead of trusting a client-supplied
// user_id. Zero behavior change today — the backend only OBSERVES the token until
// enforcement is switched on later. Implemented as a single scoped fetch wrapper so
// all ~131 existing call sites are covered without touching them; every non-backend
// fetch passes through untouched.
export default function AuthTokenBridge() {
  useEffect(() => {
    if (typeof window === 'undefined' || !supabase) return
    if (window.__jarvisFetchPatched) return
    window.__jarvisFetchPatched = true

    const orig = window.fetch.bind(window)
    window.fetch = async (input, init) => {
      try {
        const url = typeof input === 'string' ? input : (input && input.url) || ''
        if (url.startsWith(BACKEND)) {
          const headers = new Headers(
            (init && init.headers) ||
              (typeof input !== 'string' && input && input.headers) ||
              {}
          )
          if (!headers.has('authorization')) {
            const { data } = await supabase.auth.getSession()
            const token = data?.session?.access_token
            if (token) {
              headers.set('authorization', `Bearer ${token}`)
              init = { ...(init || {}), headers }
            }
          }
        }
      } catch {
        // Never let auth plumbing break a request — fall through to the original.
      }
      return orig(input, init)
    }
    // Intentionally not restored on unmount: the patch is process-wide and must
    // outlive this component so in-flight and later callers keep their token.
  }, [])
  return null
}
