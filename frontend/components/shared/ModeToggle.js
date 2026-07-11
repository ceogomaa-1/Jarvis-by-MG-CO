'use client'
import { useRouter } from 'next/navigation'
import { setJarvisMode } from '../../lib/userPreferences'

// currentMode: 'personal' | 'business'
export default function ModeToggle({ userId, currentMode }) {
  const router = useRouter()

  // Stay on the CURRENT origin (relative nav). The old absolute www URL forced an origin
  // hop that (a) escaped preview deployments onto production and (b) started OAuth on a
  // host the Supabase allowlist didn't cover — the root of the OS1 login loop. Apex→www
  // canonicalization is handled by the platform's 308, not by us.
  const OS1_URL = process.env.NEXT_PUBLIC_OS1_URL || '/os1'

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

  const label = currentMode === 'personal' ? 'Rue for Business →' : 'Personal Rue'

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
