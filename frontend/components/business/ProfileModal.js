'use client'
import { useEffect, useState } from 'react'
import { supabase } from '../../lib/supabase'

const GLASS_OVERLAY = {
  position: 'fixed', inset: 0,
  background: 'rgba(0,0,0,0.55)',
  backdropFilter: 'blur(6px)',
  WebkitBackdropFilter: 'blur(6px)',
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  zIndex: 1000,
}

const GLASS_PANEL = {
  width: '100%', maxWidth: 440, margin: '0 20px',
  background: 'rgba(15, 15, 18, 0.55)',
  backdropFilter: 'blur(28px) saturate(180%)',
  WebkitBackdropFilter: 'blur(28px) saturate(180%)',
  border: '1px solid rgba(232,232,232,0.15)',
  borderRadius: 20,
  padding: 28,
  fontFamily: 'system-ui, sans-serif',
  boxShadow: '0 24px 60px rgba(0,0,0,0.55), inset 0 1px 0 rgba(232,232,232,0.06)',
}

export default function ProfileModal({ open, onClose }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [signingOut, setSigningOut] = useState(false)

  useEffect(() => {
    if (!open) return
    setLoading(true)
    supabase.auth.getUser()
      .then(({ data }) => setUser(data?.user || null))
      .catch(() => setUser(null))
      .finally(() => setLoading(false))
  }, [open])

  if (!open) return null

  const handleSignOut = async () => {
    setSigningOut(true)
    try {
      await supabase.auth.signOut()
      window.location.href = '/'
    } catch (e) {
      console.error('Sign out failed', e)
      setSigningOut(false)
    }
  }

  const displayName =
    user?.user_metadata?.full_name ||
    user?.user_metadata?.name ||
    user?.user_metadata?.display_name ||
    (user?.email ? user.email.split('@')[0] : 'You')
  const email = user?.email || '—'
  const avatarLetter = (displayName?.[0] || email?.[0] || '?').toUpperCase()

  return (
    <div onClick={onClose} style={GLASS_OVERLAY}>
      <div onClick={e => e.stopPropagation()} style={GLASS_PANEL}>
        <div style={{
          fontFamily: 'var(--font-pixel), monospace',
          fontSize: 10, letterSpacing: '0.12em',
          color: '#2d7ff9', marginBottom: 8, textTransform: 'uppercase',
        }}>
          👤 ACCOUNT
        </div>
        <div style={{
          fontFamily: 'var(--font-pixel), monospace',
          fontSize: 13, color: '#e8e8e8', marginBottom: 22, lineHeight: 1.5,
        }}>
          Signed in to Rue
        </div>

        {loading ? (
          <div style={{ color: 'rgba(232,232,232,0.5)', fontSize: 13, padding: 12 }}>Loading…</div>
        ) : !user ? (
          <div style={{
            color: 'rgba(232,232,232,0.6)', fontSize: 13,
            padding: '12px 14px',
            background: 'rgba(239,68,68,0.08)',
            border: '1px solid rgba(239,68,68,0.25)',
            borderRadius: 10,
          }}>
            No active session detected. Try refreshing the page.
          </div>
        ) : (
          <>
            <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 22 }}>
              <div style={{
                width: 52, height: 52, borderRadius: '50%',
                background: 'linear-gradient(135deg, #2d7ff9, #d4623f)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 22, fontWeight: 700, color: '#fff', flexShrink: 0,
                boxShadow: '0 4px 16px rgba(45,127,249,0.35)',
              }}>
                {avatarLetter}
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 15, color: '#e8e8e8', fontWeight: 600, marginBottom: 2 }}>
                  {displayName}
                </div>
                <div style={{
                  fontSize: 12, color: 'rgba(232,232,232,0.55)',
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}>
                  {email}
                </div>
              </div>
            </div>

            <div style={{
              background: 'rgba(232,232,232,0.04)',
              border: '1px solid rgba(232,232,232,0.08)',
              borderRadius: 10, padding: '12px 14px', marginBottom: 18,
              fontSize: 11, color: 'rgba(232,232,232,0.6)', lineHeight: 1.55,
            }}>
              <div style={{ marginBottom: 6 }}>
                <span style={{ color: 'rgba(232,232,232,0.4)' }}>User ID</span>{' '}
                <span style={{ fontFamily: 'ui-monospace, monospace', color: '#e8e8e8' }}>{user.id?.slice(0, 8)}…</span>
              </div>
              <div>
                <span style={{ color: 'rgba(232,232,232,0.4)' }}>Joined</span>{' '}
                <span style={{ color: '#e8e8e8' }}>
                  {user.created_at ? new Date(user.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : '—'}
                </span>
              </div>
            </div>
          </>
        )}

        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
          <button
            onClick={handleSignOut}
            disabled={signingOut || !user}
            style={{
              background: 'transparent',
              border: '1px solid rgba(239,68,68,0.3)',
              borderRadius: 12, padding: '10px 18px',
              color: '#ef4444', fontSize: 13, fontWeight: 500,
              fontFamily: 'system-ui, sans-serif',
              cursor: (signingOut || !user) ? 'default' : 'pointer',
              opacity: (signingOut || !user) ? 0.5 : 1,
              transition: 'all 200ms ease',
            }}
          >
            {signingOut ? 'Signing out…' : 'Sign out'}
          </button>
          <button
            onClick={onClose}
            style={{
              background: 'transparent',
              border: '1px solid rgba(232,232,232,0.1)',
              borderRadius: 12, padding: '10px 24px',
              color: 'rgba(232,232,232,0.7)', fontSize: 13,
              fontFamily: 'system-ui, sans-serif', cursor: 'pointer',
              transition: 'all 200ms ease',
            }}
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
