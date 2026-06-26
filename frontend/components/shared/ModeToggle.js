'use client'
import { useRouter } from 'next/navigation'
import { setJarvisMode } from '../../lib/userPreferences'

// currentMode: 'personal' | 'business'
export default function ModeToggle({ userId, currentMode }) {
  const router = useRouter()

  // Canonical site origin (www is the canonical host — apex 308-redirects to it). Overridable
  // via env for previews/staging. With the auth cookie scoped to .jarvismgco.com, the session
  // is shared across apex↔www, so this hop no longer drops the login.
  const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || 'https://www.jarvismgco.com'
  const OS1_URL = process.env.NEXT_PUBLIC_OS1_URL || `${SITE_URL}/os1`

  const handleSwitch = async () => {
    // Personal → Business now routes through the OS1 paywall gate. The gate (on /os1) decides
    // access: existing/grandfathered/active users pass straight into OS1, new users see pricing.
    if (currentMode === 'personal') {
      window.location.href = OS1_URL
      return
    }
    // Business → Personal keeps its original behavior.
    if (userId) await setJarvisMode(userId, 'personal')
    router.push('/')
  }

  const label = currentMode === 'personal' ? 'Jarvis for Business →' : 'Personal Jarvis'

  return (
    <button
      onClick={handleSwitch}
      style={{
        background: 'none',
        border: '1px solid rgba(243,234,217,0.12)',
        borderRadius: 5,
        padding: '5px 13px',
        color: 'rgba(243,234,217,0.38)',
        cursor: 'pointer',
        fontFamily: 'system-ui, sans-serif',
        fontSize: 11,
        letterSpacing: '0.08em',
        transition: 'color 0.2s, border-color 0.2s',
      }}
      onMouseEnter={e => {
        e.currentTarget.style.color = 'rgba(243,234,217,0.7)'
        e.currentTarget.style.borderColor = 'rgba(243,234,217,0.25)'
      }}
      onMouseLeave={e => {
        e.currentTarget.style.color = 'rgba(243,234,217,0.38)'
        e.currentTarget.style.borderColor = 'rgba(243,234,217,0.12)'
      }}
    >
      {label}
    </button>
  )
}
