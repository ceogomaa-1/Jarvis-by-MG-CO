'use client'
import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { motion, AnimatePresence } from 'framer-motion'
import { Inbox, BookOpen, Wrench, Star, User, Database, Target, Home } from 'lucide-react'
import { supabase } from '../../lib/supabase'
import { setJarvisMode } from '../../lib/userPreferences'

import MorningQueueModal from './MorningQueueModal'
import BrandModal from './BrandModal'
import ConnectionsModal from './ConnectionsModal'
import KnowledgeBaseModal from './KnowledgeBaseModal'
import ProfileModal from './ProfileModal'
import CrmCockpit from './CrmCockpit'
import LeadsCockpit from './LeadsCockpit'
import HomeCockpit from './home/HomeCockpit'

const BACKEND = 'https://jarvis-backend-4oz6.onrender.com'

const PANEL_WIDTH = 248

function UnreadBadge() {
  return (
    <span style={{
      position: 'absolute', top: 2, right: 2,
      width: 7, height: 7, borderRadius: '50%',
      background: 'var(--os1-accent)',
      boxShadow: '0 0 8px var(--os1-glow)',
    }} />
  )
}

function HamburgerIcon() {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <line x1="4" y1="7" x2="20" y2="7" />
      <line x1="4" y1="12" x2="20" y2="12" />
      <line x1="4" y1="17" x2="20" y2="17" />
    </svg>
  )
}

function MenuItem({ icon, label, hint, badge, onClick }) {
  return (
    <button
      onClick={onClick}
      className="os1-card"
      style={{
        width: '100%',
        display: 'flex', alignItems: 'center', gap: 12,
        padding: '13px 14px',
        cursor: 'pointer',
        color: 'var(--os1-text)',
        textAlign: 'left',
        marginBottom: 12,
        position: 'relative',
      }}
    >
      <span style={{ color: 'var(--os1-text-dim)', display: 'flex', flexShrink: 0, position: 'relative' }}>
        {icon}
        {badge && (
          <span style={{
            position: 'absolute', top: -3, right: -5,
            width: 6, height: 6, borderRadius: '50%',
            background: 'var(--os1-accent)',
            boxShadow: '0 0 8px var(--os1-glow)',
          }} />
        )}
      </span>
      <span style={{ display: 'flex', flexDirection: 'column', gap: 3, minWidth: 0 }}>
        <span className="font-pixel" style={{ fontSize: 13, lineHeight: 1.3 }}>{label}</span>
        {hint && (
          <span className="os1-serif-micro" style={{ fontSize: 9, lineHeight: 1.35, color: 'var(--os1-text-faint)' }}>
            {hint}
          </span>
        )}
      </span>
    </button>
  )
}

export default function ChatHeaderMenu({ userId, onBrandSaved, open, onToggle, onClose, onActPrompt, autoOpenHome = false }) {
  const router = useRouter()
  const [openModal, setOpenModal] = useState(null)
  const [authUser, setAuthUser] = useState(null)
  const [unreadCount, setUnreadCount] = useState(0)
  const [crmWorkspace, setCrmWorkspace] = useState(null)   // null until checked; {provisioned,...}
  const [crmOpen, setCrmOpen] = useState(false)
  const [leadsEnabled, setLeadsEnabled] = useState(false)  // mgcoleads feature flag (env-gated)
  const [leadsOpen, setLeadsOpen] = useState(false)
  const [homeOpen, setHomeOpen] = useState(false)          // Batch 67 — Jarvis Home cockpit

  // Default-landing: the page resolves the user's Home setting and flips autoOpenHome.
  useEffect(() => {
    if (autoOpenHome) setHomeOpen(true)
  }, [autoOpenHome])

  // Home block "navigate" actions resolve to the existing surfaces.
  const handleHomeNavigate = (target) => {
    if (target === 'crm') { setHomeOpen(false); setCrmOpen(true) }
    else if (target === 'leads') { setHomeOpen(false); setLeadsOpen(true) }
    else if (target === 'morning_queue') { setHomeOpen(false); openM('queue') }
    else if (target === 'connections') { openM('connections') }
    else if (target === 'workflow') { router.push('/business/workflow') }
  }

  useEffect(() => {
    if (!supabase) return
    supabase.auth.getUser()
      .then(({ data }) => setAuthUser(data?.user || null))
      .catch(() => setAuthUser(null))
  }, [])

  // Gate the CRM nav item: only show it when this user's Jarvis CRM workspace exists.
  useEffect(() => {
    if (!userId) return
    fetch(`${BACKEND}/api/business/crm/workspace?user_id=${encodeURIComponent(userId)}`)
      .then(r => r.json())
      .then(d => setCrmWorkspace(d))
      .catch(() => setCrmWorkspace({ provisioned: false }))
  }, [userId])

  // Gate the Leads nav item: only show it when the lead engine is configured (env-gated).
  useEffect(() => {
    if (!userId) return
    fetch(`${BACKEND}/api/business/leads/status?user_id=${encodeURIComponent(userId)}`)
      .then(r => r.json())
      .then(d => setLeadsEnabled(!!d?.enabled))
      .catch(() => setLeadsEnabled(false))
  }, [userId])

  useEffect(() => {
    if (!userId) return
    fetch(`${BACKEND}/api/business/morning-queue/unread-count?user_id=${encodeURIComponent(userId)}`)
      .then(r => r.json())
      .then(d => setUnreadCount(d.unread || 0))
      .catch(() => {})
  }, [userId])

  const close = () => setOpenModal(null)
  const openM = (key) => {
    setOpenModal(key)
    onClose?.()
    if (key === 'queue') setUnreadCount(0)
  }

  const switchToPersonal = async () => {
    try { if (userId) await setJarvisMode(userId, 'personal') } catch {}
    router.push('/')
  }

  const displayName =
    authUser?.user_metadata?.full_name ||
    authUser?.user_metadata?.name ||
    authUser?.user_metadata?.display_name ||
    (authUser?.email ? authUser.email.split('@')[0] : 'Guest')
  const email = authUser?.email || 'Not signed in'
  const shortId = authUser?.id ? authUser.id.slice(0, 8) + '...' : '—'
  const joined = authUser?.created_at
    ? new Date(authUser.created_at).toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })
    : '—'

  const items = [
    { label: 'Home', icon: <Home size={17} />,
      hint: 'your command center — what changed overnight, and one tap to act on it',
      onClick: () => { onClose?.(); setHomeOpen(true) } },
    { label: 'Morning Queue',         icon: <Inbox size={17} />,    badge: unreadCount > 0, onClick: () => openM('queue') },
    // CRM cockpit — only when the user's Jarvis CRM workspace is provisioned.
    ...(crmWorkspace?.provisioned ? [{
      label: 'CRM', icon: <Database size={17} />,
      hint: 'your Jarvis CRM — view it and let me edit it live',
      onClick: () => { onClose?.(); setCrmOpen(true) },
    }] : []),
    // Leads cockpit — only when the mgcoleads engine is enabled (LEADS_MAPS_API_KEY / flag).
    ...(leadsEnabled ? [{
      label: 'Leads', icon: <Target size={17} />,
      hint: 'scored B2B leads — find, filter, and push them to your CRM',
      onClick: () => { onClose?.(); setLeadsOpen(true) },
    }] : []),
    { label: 'Knowledge Base',        icon: <BookOpen size={17} />, hint: "stuff you're ready to paste and want me to know right away", onClick: () => openM('knowledge') },
    { label: 'Connections',           icon: <Wrench size={17} />,   onClick: () => openM('connections') },
    { label: 'Brand Personalization', icon: <Star size={17} />,     onClick: () => openM('brand') },
    { label: 'My Profile',            icon: <User size={17} />,     onClick: () => openM('profile') },
  ]

  return (
    <>
      {/* Hamburger — fixed top right (hidden while panel is open; panel has its own) */}
      {!open && (
        <button
          onClick={onToggle}
          className="os1-iconbtn"
          title="Menu"
          style={{ position: 'fixed', top: 20, right: 22, zIndex: 50 }}
        >
          <HamburgerIcon />
          {unreadCount > 0 && <UnreadBadge />}
        </button>
      )}

      {/* Slide-in menu panel */}
      <AnimatePresence>
        {open && (
          <>
            {/* Click-away catcher (transparent — design keeps page visible) */}
            <div
              onClick={onClose}
              style={{ position: 'fixed', inset: 0, zIndex: 54, background: 'transparent' }}
            />
            <motion.div
              key="menu-panel"
              initial={{ x: PANEL_WIDTH + 30, opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
              exit={{ x: PANEL_WIDTH + 30, opacity: 0 }}
              transition={{ duration: 0.25, ease: 'easeOut' }}
              className="os1-panel"
              style={{
                position: 'fixed', top: 12, right: 12, bottom: 12,
                width: PANEL_WIDTH, zIndex: 55,
                display: 'flex', flexDirection: 'column',
                padding: '16px 16px 18px',
              }}
            >
              {/* Top row: profile icon + hamburger (closes) */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
                <span style={{ color: 'var(--os1-text-dim)' }}>
                  <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
                    <circle cx="12" cy="12" r="9.5" />
                    <circle cx="12" cy="9.5" r="3" />
                    <path d="M5.8 19a7.5 7.5 0 0 1 12.4 0" />
                  </svg>
                </span>
                <button onClick={onClose} className="os1-iconbtn" title="Close menu" style={{ marginRight: -6 }}>
                  <HamburgerIcon />
                </button>
              </div>

              {/* Identity block */}
              <div className="os1-display" style={{ fontSize: 21, color: 'var(--os1-text)', marginBottom: 8, lineHeight: 1.15 }}>
                {displayName}
              </div>
              <div className="os1-serif-micro" style={{ fontSize: 8.5, marginBottom: 4, textTransform: 'none', letterSpacing: '0.06em' }}>{email}</div>
              <div className="os1-serif-micro" style={{ fontSize: 8.5, marginBottom: 4 }}>ID {shortId}</div>
              <div className="os1-serif-micro" style={{ fontSize: 8.5 }}>Joined {joined}</div>

              {/* Divider */}
              <div className="os1-hairline" style={{ margin: '18px 0 20px' }} />

              {/* Menu items */}
              <div style={{ flex: 1, minHeight: 0, overflowY: 'auto' }} className="os1-scroll">
                {items.map(item => (
                  <MenuItem key={item.label} icon={item.icon} label={item.label} hint={item.hint} badge={item.badge} onClick={item.onClick} />
                ))}
                {/* FontToggle retired in Batch 72 — the default font IS the readable
                    premium sans now; the pref remains honored via useFontPref. */}
              </div>

              {/* Switch to Personal Jarvis */}
              <button
                onClick={switchToPersonal}
                style={{
                  width: '100%', background: 'transparent', border: 'none',
                  borderTop: '1px solid var(--os1-border-soft)',
                  padding: '12px 2px 2px', marginTop: 6,
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  cursor: 'pointer', color: 'var(--os1-text-faint)',
                  transition: 'color 150ms ease',
                }}
                onMouseEnter={e => e.currentTarget.style.color = 'var(--os1-text)'}
                onMouseLeave={e => e.currentTarget.style.color = 'var(--os1-text-faint)'}
              >
                <span className="font-pixel" style={{ fontSize: 12 }}>Switch to Personal</span>
                <span className="font-pixel" style={{ fontSize: 12 }}>→</span>
              </button>

              {/* Footer: tier + wordmark */}
              <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', paddingTop: 14 }}>
                <span className="os1-label" style={{ fontSize: 8.5 }}>Pro Tier</span>
                <span className="os1-display" style={{ fontSize: 15, color: 'var(--os1-text-faint)' }}>Jarvis</span>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>

      <MorningQueueModal  open={openModal === 'queue'}       onClose={close} userId={userId} onAct={onActPrompt} />
      <BrandModal         open={openModal === 'brand'}       onClose={close} userId={userId} onSaved={onBrandSaved} />
      <ConnectionsModal   open={openModal === 'connections'} onClose={close} userId={userId} />
      <KnowledgeBaseModal open={openModal === 'knowledge'}   onClose={close} userId={userId} userEmail={authUser?.email} />
      <ProfileModal       open={openModal === 'profile'}     onClose={close} />

      {/* Phase 3 — embedded Jarvis CRM cockpit with docked chat */}
      <CrmCockpit open={crmOpen} onClose={() => setCrmOpen(false)} userId={userId} workspace={crmWorkspace} />

      {/* mgcoleads — Leads cockpit (scored pipeline) with the same docked chat */}
      <LeadsCockpit open={leadsOpen} onClose={() => setLeadsOpen(false)} userId={userId} />

      {/* Batch 67 — Jarvis Home: adaptive command center with the same docked chat */}
      <HomeCockpit open={homeOpen} onClose={() => setHomeOpen(false)} userId={userId} onNavigate={handleHomeNavigate} />
    </>
  )
}
