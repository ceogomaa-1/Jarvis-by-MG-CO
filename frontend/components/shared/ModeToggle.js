'use client'
import { useRouter } from 'next/navigation'
import { setJarvisMode } from '../../lib/userPreferences'

// currentMode: 'personal' | 'business'
export default function ModeToggle({ userId, currentMode }) {
  const router = useRouter()

  const handleSwitch = async () => {
    const next = currentMode === 'personal' ? 'business' : 'personal'
    if (userId) await setJarvisMode(userId, next)
    router.push(next === 'business' ? '/business/chat' : '/')
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
