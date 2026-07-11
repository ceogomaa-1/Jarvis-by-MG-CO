// OS1 paywall client helpers — talk to the backend billing API (same host as userPreferences).
import { BACKEND } from '@/lib/backend'

// App user_id form used everywhere in Rue: 'user_' + hex(auth uuid).
export function jarvisUserId(authUserId) {
  return 'user_' + String(authUserId || '').replace(/-/g, '')
}

// Auth-gate read: { has_access, grandfathered, plan, trialing, status, billing_enabled }.
export async function getOS1Status(userId, email) {
  try {
    const qs = new URLSearchParams({ user_id: userId, email: email || '' })
    const res = await fetch(`${BACKEND}/api/os1/status?${qs.toString()}`)
    if (!res.ok) return null
    return await res.json()
  } catch {
    return null
  }
}

// Returns true if the domain is disposable/temp-mail (block at signup).
export async function isDisposableEmail(email) {
  try {
    const res = await fetch(`${BACKEND}/api/os1/email-check`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email }),
    })
    if (!res.ok) return false
    const data = await res.json()
    return !!data.disposable
  } catch {
    return false
  }
}

// Start Stripe Checkout. Returns { ok, url } or { ok:false, error }.
export async function startCheckout({ userId, email, plan, interval, trial }) {
  try {
    const res = await fetch(`${BACKEND}/api/os1/checkout`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: userId, email, plan, interval, trial: !!trial }),
    })
    return await res.json()
  } catch {
    return { ok: false, error: 'Network error — please try again.' }
  }
}

// Open the Stripe customer portal (manage / cancel).
export async function openPortal(userId) {
  try {
    const res = await fetch(`${BACKEND}/api/os1/portal`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: userId }),
    })
    return await res.json()
  } catch {
    return { ok: false, error: 'Network error — please try again.' }
  }
}

// Contact Us form → emailed to info@mgcotechnologies.com (Resend, with fallback).
export async function submitContact(payload) {
  try {
    const res = await fetch(`${BACKEND}/api/os1/contact`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    return await res.json()
  } catch {
    return { ok: false, error: 'Network error — please try again.' }
  }
}
