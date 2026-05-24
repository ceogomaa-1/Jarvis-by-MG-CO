'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { supabase } from '../../lib/supabase'

export default function SignOutDrawer({ isOpen, onClose, user }) {
  const router = useRouter()

  // Close on Escape
  useEffect(() => {
    if (!isOpen) return
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [isOpen, onClose])

  // Lock body scroll when open
  useEffect(() => {
    if (isOpen) document.body.style.overflow = 'hidden'
    else document.body.style.overflow = ''
    return () => { document.body.style.overflow = '' }
  }, [isOpen])

  const handleSignOut = async () => {
    if (supabase) await supabase.auth.signOut()
    onClose()
    router.replace('/login')
  }

  if (!user) return null

  const displayName = user.user_metadata?.full_name || user.email?.split('@')[0] || 'User'
  const avatarUrl = user.user_metadata?.avatar_url
  const initial = displayName.charAt(0).toUpperCase()

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={onClose}
        style={{
          position: 'fixed', inset: 0, zIndex: 48,
          background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)',
          opacity: isOpen ? 1 : 0,
          pointerEvents: isOpen ? 'auto' : 'none',
          transition: 'opacity 280ms ease',
        }}
      />

      {/* Drawer */}
      <aside
        style={{
          position: 'fixed', top: 0, left: 0, bottom: 0, zIndex: 49,
          width: '85%', maxWidth: 320,
          background: '#0a0908',
          borderRight: '1px solid rgba(243,234,217,0.07)',
          display: 'flex', flexDirection: 'column',
          transform: isOpen ? 'translateX(0)' : 'translateX(-100%)',
          transition: 'transform 300ms cubic-bezier(0.4, 0, 0.2, 1)',
        }}
      >
        {/* Header row */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '0 20px', height: 56,
          borderBottom: '1px solid rgba(243,234,217,0.07)',
        }}>
          <span style={{ fontFamily: 'var(--sans)', fontSize: 10, letterSpacing: '0.3em', textTransform: 'uppercase', color: 'var(--ink-mute)' }}>
            Account
          </span>
          <button
            onClick={onClose}
            aria-label="Close menu"
            style={{
              width: 32, height: 32, borderRadius: 999,
              background: 'none', border: 'none', cursor: 'pointer',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              color: 'var(--ink-soft)',
            }}
          >
            {/* X icon */}
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* User info */}
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '32px 24px 24px', textAlign: 'center' }}>
          {avatarUrl ? (
            <img
              src={avatarUrl}
              alt={displayName}
              referrerPolicy="no-referrer"
              style={{ width: 64, height: 64, borderRadius: '50%', border: '1px solid rgba(243,234,217,0.1)', marginBottom: 16, objectFit: 'cover' }}
            />
          ) : (
            <div style={{
              width: 64, height: 64, borderRadius: '50%', marginBottom: 16,
              background: 'rgba(255,144,114,0.08)', border: '1px solid rgba(255,144,114,0.2)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <span style={{ fontFamily: 'var(--display)', fontSize: 24, color: 'var(--ink-soft)', fontWeight: 400 }}>{initial}</span>
            </div>
          )}
          <div style={{ fontFamily: 'var(--sans)', fontSize: 15, color: 'var(--ink)', fontWeight: 300, letterSpacing: 0.2 }}>
            {displayName}
          </div>
          <div style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--ink-mute)', marginTop: 4 }}>
            {user.email}
          </div>
        </div>

        {/* Divider */}
        <div style={{ marginLeft: 20, marginRight: 20, borderTop: '1px solid rgba(243,234,217,0.05)' }} />

        {/* Sign Out */}
        <div style={{ padding: 20 }}>
          <button
            onClick={handleSignOut}
            style={{
              width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
              padding: '12px 16px', borderRadius: 12,
              background: 'rgba(127,0,0,0.15)', border: '1px solid rgba(239,68,68,0.3)',
              cursor: 'pointer', color: '#fca5a5',
              fontFamily: 'var(--sans)', fontSize: 12, letterSpacing: '0.15em', textTransform: 'uppercase',
              transition: 'background 200ms ease',
            }}
            onMouseEnter={e => e.currentTarget.style.background = 'rgba(127,0,0,0.28)'}
            onMouseLeave={e => e.currentTarget.style.background = 'rgba(127,0,0,0.15)'}
          >
            {/* LogOut icon */}
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
              <polyline points="16 17 21 12 16 7" />
              <line x1="21" y1="12" x2="9" y2="12" />
            </svg>
            Sign Out
          </button>
        </div>
      </aside>
    </>
  )
}
