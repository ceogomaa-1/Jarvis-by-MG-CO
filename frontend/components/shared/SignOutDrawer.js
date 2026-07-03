'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { supabase } from '../../lib/supabase'

import { BACKEND } from '@/lib/backend'

function safeItemText(item) {
  if (typeof item === 'string') {
    try {
      const parsed = JSON.parse(item)
      if (parsed && typeof parsed === 'object') {
        const parts = [parsed.name, parsed.label, parsed.details].filter(Boolean)
        return parts.length > 0 ? parts.join(' — ') : JSON.stringify(parsed)
      }
    } catch (_) {}
    return item
  }
  if (typeof item === 'object' && item !== null) {
    const parts = [item.name, item.label, item.details].filter(Boolean)
    return parts.length > 0 ? parts.join(' — ') : JSON.stringify(item)
  }
  return String(item)
}

function KnowsSection({ title, items }) {
  if (!items || items.length === 0) return null
  const seen = new Set()
  const texts = items.map(safeItemText).filter(t => {
    if (seen.has(t)) return false
    seen.add(t)
    return true
  })
  if (texts.length === 0) return null
  return (
    <div style={{ marginBottom: '1.1rem' }}>
      <p style={{
        fontFamily: 'var(--sans)', color: 'var(--accent)',
        fontSize: '0.55rem', letterSpacing: '0.15em', textTransform: 'uppercase',
        opacity: 0.6, margin: '0 0 0.4rem',
      }}>{title}</p>
      {texts.map((text, i) => (
        <p key={i} style={{
          fontFamily: 'var(--sans)', color: 'var(--ink)',
          fontSize: '0.78rem', lineHeight: 1.55, margin: '0.2rem 0', opacity: 0.85,
        }}>
          <span style={{ color: 'var(--accent)', marginRight: '0.35rem' }}>●</span>{text}
        </p>
      ))}
    </div>
  )
}

export default function SignOutDrawer({ isOpen, onClose, user, userId, onOpenNotes }) {
  const router = useRouter()
  const [model, setModel] = useState(null)

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

  // Fetch Jarvis model when drawer opens
  useEffect(() => {
    if (!isOpen || !userId) return
    setModel(null)
    fetch(`${BACKEND}/api/user/model/${userId}`)
      .then(r => r.json())
      .then(setModel)
      .catch(() => setModel({}))
  }, [isOpen, userId])

  const handleSignOut = async () => {
    if (supabase) await supabase.auth.signOut()
    onClose()
    router.replace('/login')
  }

  if (!user) return null

  const displayName = user.user_metadata?.full_name || user.email?.split('@')[0] || 'User'
  const avatarUrl = user.user_metadata?.avatar_url
  const initial = displayName.charAt(0).toUpperCase()

  const id = model?.identity || {}
  const focus = model?.current_focus || {}
  const relationship = model?.jarvis_relationship || {}
  const work = model?.work_context || {}

  const identityItems = [
    id.name && typeof id.name === 'string' && `Name: ${id.name}`,
    id.role && typeof id.role === 'string' && `Role: ${id.role}`,
    id.company && typeof id.company === 'string' && `Company: ${id.company}`,
    id.location && typeof id.location === 'string' && `Based in: ${id.location}`,
  ].filter(Boolean)

  const trustLabel = relationship.trust_level
    ? `${relationship.trust_level} (${relationship.interaction_count || 0} interactions)`
    : null

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
          padding: '0 20px', height: 56, flexShrink: 0,
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
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* User info */}
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '24px 24px 20px', textAlign: 'center', flexShrink: 0 }}>
          {avatarUrl ? (
            <img
              src={avatarUrl}
              alt={displayName}
              referrerPolicy="no-referrer"
              style={{ width: 56, height: 56, borderRadius: '50%', border: '1px solid rgba(243,234,217,0.1)', marginBottom: 12, objectFit: 'cover' }}
            />
          ) : (
            <div style={{
              width: 56, height: 56, borderRadius: '50%', marginBottom: 12,
              background: 'rgba(255,144,114,0.08)', border: '1px solid rgba(255,144,114,0.2)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <span style={{ fontFamily: 'var(--display)', fontSize: 22, color: 'var(--ink-soft)', fontWeight: 400 }}>{initial}</span>
            </div>
          )}
          <div style={{ fontFamily: 'var(--sans)', fontSize: 14, color: 'var(--ink)', fontWeight: 300, letterSpacing: 0.2 }}>
            {displayName}
          </div>
          <div style={{ fontFamily: 'var(--sans)', fontSize: 11, color: 'var(--ink-mute)', marginTop: 3 }}>
            {user.email}
          </div>
        </div>

        {/* Divider */}
        <div style={{ marginLeft: 20, marginRight: 20, borderTop: '1px solid rgba(243,234,217,0.05)', flexShrink: 0 }} />

        {/* Jarvis Knows — scrollable middle section */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px 20px 8px' }}>
          <p style={{
            fontFamily: 'var(--sans)', color: 'var(--accent)',
            fontSize: '0.6rem', letterSpacing: '0.2em', textTransform: 'uppercase',
            opacity: 0.5, margin: '0 0 1rem',
          }}>Jarvis Knows</p>

          {!model ? (
            <p style={{ fontFamily: 'var(--sans)', color: 'var(--ink-mute)', fontSize: '0.75rem' }}>Loading...</p>
          ) : (
            <>
              <KnowsSection title="Identity" items={identityItems} />
              <KnowsSection title="Current Focus" items={focus.top_goals} />
              <KnowsSection title="Active Projects" items={focus.active_projects} />
              <KnowsSection title="Key People" items={work.key_people} />
              <KnowsSection title="Never Forget" items={relationship.things_jarvis_should_never_forget} />
              {trustLabel && (
                <div style={{ marginTop: '0.75rem', paddingTop: '0.75rem', borderTop: '1px solid rgba(243,234,217,0.05)' }}>
                  <p style={{ fontFamily: 'var(--sans)', color: 'var(--ink-mute)', fontSize: '0.55rem', letterSpacing: '0.1em', textTransform: 'uppercase', margin: '0 0 0.25rem' }}>Trust Level</p>
                  <p style={{ fontFamily: 'var(--sans)', color: 'var(--ink)', fontSize: '0.75rem', opacity: 0.7, margin: 0 }}>{trustLabel}</p>
                </div>
              )}
            </>
          )}
        </div>

        {/* Divider */}
        <div style={{ marginLeft: 20, marginRight: 20, borderTop: '1px solid rgba(243,234,217,0.05)', flexShrink: 0 }} />

        {/* Jarvis Notes */}
        <div style={{ padding: '14px 20px 0', flexShrink: 0 }}>
          <button
            onClick={() => { onOpenNotes?.(); onClose() }}
            style={{
              width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'flex-start', gap: 10,
              padding: '12px 16px', borderRadius: 12,
              background: 'rgba(255,144,114,0.06)', border: '1px solid rgba(255,144,114,0.15)',
              cursor: 'pointer', color: 'var(--ink)',
              fontFamily: 'var(--sans)', fontSize: 12, letterSpacing: '0.1em', textTransform: 'uppercase',
              transition: 'background 200ms ease',
            }}
            onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,144,114,0.12)'}
            onMouseLeave={e => e.currentTarget.style.background = 'rgba(255,144,114,0.06)'}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M9 11l3 3L22 4" />
              <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
            </svg>
            Jarvis Notes
          </button>
        </div>

        {/* Sign Out */}
        <div style={{ padding: 20, flexShrink: 0 }}>
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
