'use client'
import { useState, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import TetrisLoader from '../ui/TetrisLoader'

const SIDEBAR_WIDTH = 244

function relativeTime(dateStr) {
  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now - date
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMs / 3600000)
  const diffDays = Math.floor(diffMs / 86400000)
  if (diffMins < 1) return 'now'
  if (diffMins < 60) return `${diffMins}m`
  if (diffHours < 24) return `${diffHours}h`
  if (diffDays === 1) return '1d'
  if (diffDays < 30) return `${diffDays}d`
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function ConversationRow({ conv, isActive, onSelect, onDelete }) {
  return (
    <div
      onClick={() => onSelect(conv.id)}
      className={`os1-row os1-conv-row${isActive ? ' active' : ''}`}
      style={{
        padding: '9px 10px',
        cursor: 'pointer',
        marginBottom: 2,
        display: 'flex', alignItems: 'center', gap: 8,
      }}
    >
      <div style={{
        flex: 1, minWidth: 0,
        fontSize: 13,
        fontFamily: 'var(--pixel)',
        color: isActive ? 'var(--os1-text)' : 'var(--os1-text-dim)',
        whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
        lineHeight: 1.4,
      }}>
        {conv.title || 'New session'}
      </div>
      <span className="os1-serif-micro os1-conv-time" style={{ fontSize: 8, flexShrink: 0 }}>
        {relativeTime(conv.updated_at || conv.created_at)}
      </span>
      <button
        onClick={(e) => { e.stopPropagation(); onDelete(conv.id) }}
        title="Delete conversation"
        className="os1-conv-x"
        style={{
          flexShrink: 0, width: 16, height: 16,
          background: 'transparent', border: 'none', cursor: 'pointer',
          color: 'var(--os1-text-faint)', fontSize: 14, lineHeight: 1,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          padding: 0, fontFamily: 'var(--pixel)',
          transition: 'color 150ms, opacity 150ms',
        }}
        onMouseEnter={e => e.currentTarget.style.color = 'var(--os1-text)'}
        onMouseLeave={e => e.currentTarget.style.color = 'var(--os1-text-faint)'}
      >
        ×
      </button>
    </div>
  )
}

export default function ChatSidebar({
  conversations = [],
  loading = false,
  activeConversationId,
  onSelectConversation,
  onNewChat,
  onDeleteConversation,
  memoryCount = 0,
  isMobileOpen,
  onClose,
  collapsed = false,
  onCollapse,
  onOpenSettings,
}) {
  const [search, setSearch] = useState('')

  const filtered = useMemo(() => {
    if (!search.trim()) return conversations
    const q = search.toLowerCase()
    return conversations.filter(c => (c.title || '').toLowerCase().includes(q))
  }, [conversations, search])

  const sidebarContent = (
    <div className="os1-panel" style={{
      width: SIDEBAR_WIDTH,
      height: '100%',
      display: 'flex', flexDirection: 'column',
      flexShrink: 0,
      overflow: 'hidden',
    }}>
      {/* Delete × appears on row hover only */}
      <style>{`
        .os1-conv-row .os1-conv-x { opacity: 0; }
        .os1-conv-row:hover .os1-conv-x { opacity: 1; }
        .os1-conv-row:hover .os1-conv-time { opacity: 0; position: absolute; }
      `}</style>

      {/* Brand lockup + collapse */}
      <div style={{
        padding: '18px 18px 0',
        display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
      }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
            <img
              src="/jarvis-logo-mono.png"
              alt=""
              width={22}
              height={22}
              style={{ display: 'block', filter: 'drop-shadow(0 0 8px rgba(255,46,81,0.3))' }}
            />
            <span className="os1-display" style={{ fontSize: 15, lineHeight: 1, color: 'var(--os1-text)', letterSpacing: '0.06em' }}>
              JARVIS OS1
            </span>
          </div>
          <div className="os1-label" style={{ marginTop: 8, fontSize: 8.5 }}>
            Business
          </div>
        </div>
        <button onClick={onCollapse} className="os1-iconbtn" title="Hide sidebar" style={{ marginTop: -2, marginRight: -4 }}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
            <rect x="3" y="4" width="18" height="16" rx="3" />
            <line x1="9" y1="4" x2="9" y2="20" />
          </svg>
        </button>
      </div>

      <div className="os1-hairline" style={{ margin: '16px 18px 0' }} />

      {/* Search */}
      <div style={{ padding: '14px 14px 4px', position: 'relative' }}>
        <svg
          width="13" height="13" viewBox="0 0 24 24" fill="none"
          stroke="var(--os1-text-faint)" strokeWidth="2"
          style={{ position: 'absolute', left: 28, top: '50%', transform: 'translateY(-38%)', pointerEvents: 'none' }}
        >
          <circle cx="11" cy="11" r="7" />
          <line x1="16.5" y1="16.5" x2="21" y2="21" />
        </svg>
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search"
          className="os1-search"
        />
      </div>

      {/* New Session row */}
      <div style={{ padding: '10px 14px 0' }}>
        <button
          onClick={onNewChat}
          style={{
            width: '100%', background: 'transparent', border: 'none',
            borderBottom: '1px solid var(--os1-border-soft)',
            padding: '4px 4px 10px',
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            cursor: 'pointer', color: 'var(--os1-text)',
            transition: 'color 150ms',
          }}
          onMouseEnter={e => e.currentTarget.style.color = '#ffffff'}
          onMouseLeave={e => e.currentTarget.style.color = 'var(--os1-text)'}
        >
          <span className="os1-label" style={{ color: 'inherit', fontSize: 9.5 }}>New Session</span>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
        </button>
      </div>

      {/* Conversation rows */}
      <div className="os1-scroll" style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden', padding: '10px 10px 4px' }}>
        {loading ? (
          <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 36 }}>
            <TetrisLoader size="sm" speed="fast" showLoadingText={false} />
          </div>
        ) : filtered.length === 0 ? (
          <div style={{
            padding: '28px 8px',
            color: 'var(--os1-text-faint)',
            fontSize: 12, textAlign: 'center',
            fontFamily: 'var(--pixel)',
          }}>
            {search ? 'No matches' : 'No sessions yet'}
          </div>
        ) : (
          filtered.map(conv => (
            <ConversationRow
              key={conv.id}
              conv={conv}
              isActive={conv.id === activeConversationId}
              onSelect={onSelectConversation}
              onDelete={onDeleteConversation}
            />
          ))
        )}
      </div>

      {/* Footer: settings gear + memories saved */}
      <div className="os1-hairline" style={{ margin: '0 18px' }} />
      <div style={{
        padding: '10px 14px 14px',
        display: 'flex', alignItems: 'center', gap: 10,
      }}>
        <button onClick={onOpenSettings} className="os1-iconbtn" title="Settings" style={{ padding: 4, marginLeft: -2 }}>
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
            <circle cx="12" cy="12" r="3.2" />
            <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1.03 1.56V21a2 2 0 1 1-4 0v-.09a1.7 1.7 0 0 0-1.11-1.56 1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.7 1.7 0 0 0 .34-1.87 1.7 1.7 0 0 0-1.56-1.03H3a2 2 0 1 1 0-4h.09a1.7 1.7 0 0 0 1.56-1.11 1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.7 1.7 0 0 0 1.87.34h.01a1.7 1.7 0 0 0 1.02-1.56V3a2 2 0 1 1 4 0v.09a1.7 1.7 0 0 0 1.03 1.56 1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.7 1.7 0 0 0-.34 1.87v.01a1.7 1.7 0 0 0 1.56 1.02H21a2 2 0 1 1 0 4h-.09a1.7 1.7 0 0 0-1.51 1.03z" />
          </svg>
        </button>
        <span className="os1-label" style={{ fontSize: 8.5 }}>
          {memoryCount > 0 ? `${memoryCount} Memories` : 'No Memories Yet'}
        </span>
      </div>
    </div>
  )

  // Desktop: floating panel with margins (hidden when collapsed)
  // Mobile: overlay slide-in
  return (
    <>
      {/* Desktop sidebar */}
      {!collapsed && (
        <div
          className="business-sidebar-desktop"
          style={{ display: 'flex', padding: '14px 0 14px 14px', height: '100%' }}
        >
          <style>{`
            @media (max-width: 768px) {
              .business-sidebar-desktop { display: none !important; }
            }
          `}</style>
          {sidebarContent}
        </div>
      )}

      {/* Mobile overlay */}
      <AnimatePresence>
        {isMobileOpen && (
          <>
            <motion.div
              key="overlay"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              onClick={onClose}
              style={{
                position: 'fixed', inset: 0,
                background: 'rgba(5,4,3,0.65)',
                backdropFilter: 'blur(4px)',
                zIndex: 39,
                display: 'none',
              }}
              className="mobile-sidebar-overlay"
            />
            <motion.div
              key="sidebar"
              initial={{ x: -SIDEBAR_WIDTH - 20 }}
              animate={{ x: 0 }}
              exit={{ x: -SIDEBAR_WIDTH - 20 }}
              transition={{ duration: 0.3, ease: 'easeOut' }}
              style={{
                position: 'fixed', top: 10, left: 10, bottom: 10,
                zIndex: 40, display: 'none',
              }}
              className="mobile-sidebar-panel"
            >
              {sidebarContent}
            </motion.div>
          </>
        )}
      </AnimatePresence>
      <style>{`
        @media (max-width: 768px) {
          .mobile-sidebar-overlay { display: block !important; }
          .mobile-sidebar-panel { display: block !important; }
        }
      `}</style>
    </>
  )
}
