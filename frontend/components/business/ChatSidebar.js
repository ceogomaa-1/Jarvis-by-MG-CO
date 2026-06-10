'use client'
import { useState, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import TetrisLoader from '../ui/TetrisLoader'

const SIDEBAR_WIDTH = 232

function relativeTime(dateStr) {
  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now - date
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMs / 3600000)
  const diffDays = Math.floor(diffMs / 86400000)
  if (diffMins < 1) return 'Just Now'
  if (diffMins < 60) return `${diffMins}min ago`
  if (diffHours < 24) return `${diffHours}h ago`
  if (diffDays === 1) return '1d ago'
  if (diffDays < 30) return `${diffDays}d ago`
  return date.toLocaleDateString()
}

function ConversationCard({ conv, isActive, onSelect, onDelete }) {
  return (
    <div
      onClick={() => onSelect(conv.id)}
      className={`os1-card${isActive ? ' active' : ''}`}
      style={{
        padding: '10px 12px 8px',
        cursor: 'pointer',
        marginBottom: 10,
        position: 'relative',
      }}
    >
      {/* Title row + × */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 6 }}>
        <div className="font-pixel" style={{
          flex: 1, minWidth: 0,
          fontSize: 13,
          color: isActive ? 'var(--os1-text)' : 'var(--os1-text-dim)',
          whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
          lineHeight: 1.4,
        }}>
          {conv.title || 'New chat'}
        </div>
        <button
          onClick={(e) => { e.stopPropagation(); onDelete(conv.id) }}
          title="Delete conversation"
          style={{
            flexShrink: 0, width: 16, height: 16,
            background: 'transparent', border: 'none', cursor: 'pointer',
            color: 'var(--os1-text-faint)', fontSize: 13, lineHeight: 1,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            padding: 0, fontFamily: 'var(--pixel)',
            transition: 'color 150ms',
          }}
          onMouseEnter={e => e.currentTarget.style.color = 'var(--os1-text)'}
          onMouseLeave={e => e.currentTarget.style.color = 'var(--os1-text-faint)'}
        >
          ×
        </button>
      </div>

      {/* Bottom row: time + Remove */}
      <div style={{
        display: 'flex', alignItems: 'baseline', justifyContent: 'space-between',
        marginTop: 8,
      }}>
        <span className="os1-serif-micro" style={{ fontSize: 9 }}>
          {relativeTime(conv.updated_at || conv.created_at)}
        </span>
        <button
          onClick={(e) => { e.stopPropagation(); onDelete(conv.id) }}
          className="os1-serif-micro"
          style={{
            background: 'transparent', border: 'none', cursor: 'pointer',
            fontSize: 9, padding: 0,
            color: 'var(--os1-text-faint)',
            transition: 'color 150ms',
          }}
          onMouseEnter={e => e.currentTarget.style.color = 'var(--os1-text-dim)'}
          onMouseLeave={e => e.currentTarget.style.color = 'var(--os1-text-faint)'}
        >
          Remove
        </button>
      </div>
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
      {/* Collapse toggle */}
      <div style={{ padding: '14px 14px 4px' }}>
        <button onClick={onCollapse} className="os1-iconbtn" title="Hide sidebar" style={{ marginLeft: -4 }}>
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
            <rect x="3" y="4" width="18" height="16" rx="3" />
            <line x1="9" y1="4" x2="9" y2="20" />
          </svg>
        </button>
      </div>

      {/* Search pill */}
      <div style={{ padding: '8px 14px 4px', position: 'relative' }}>
        <svg
          width="14" height="14" viewBox="0 0 24 24" fill="none"
          stroke="var(--os1-text-faint)" strokeWidth="2"
          style={{ position: 'absolute', left: 27, top: '50%', transform: 'translateY(-46%)', pointerEvents: 'none' }}
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
      <div style={{ padding: '12px 14px 0' }}>
        <button
          onClick={onNewChat}
          style={{
            width: '100%', background: 'transparent', border: 'none',
            borderBottom: '1px solid var(--os1-border-soft)',
            padding: '4px 2px 9px',
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            cursor: 'pointer', color: 'var(--os1-text)',
            transition: 'color 150ms',
          }}
          onMouseEnter={e => e.currentTarget.style.color = '#ffffff'}
          onMouseLeave={e => e.currentTarget.style.color = 'var(--os1-text)'}
        >
          <span className="font-pixel" style={{ fontSize: 14, letterSpacing: '0.04em' }}>New Session</span>
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
            <rect x="3" y="3" width="18" height="18" rx="4" />
            <line x1="12" y1="8" x2="12" y2="16" />
            <line x1="8" y1="12" x2="16" y2="12" />
          </svg>
        </button>
      </div>

      {/* Conversation cards */}
      <div className="os1-scroll" style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden', padding: '14px 14px 4px' }}>
        {loading ? (
          <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 32 }}>
            <TetrisLoader size="sm" speed="fast" showLoadingText={false} />
          </div>
        ) : filtered.length === 0 ? (
          <div className="font-pixel" style={{
            padding: '24px 8px',
            color: 'var(--os1-text-faint)',
            fontSize: 12, textAlign: 'center',
          }}>
            {search ? 'No matches' : 'No sessions yet'}
          </div>
        ) : (
          filtered.map(conv => (
            <ConversationCard
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
      <div style={{
        padding: '12px 14px 14px',
        display: 'flex', alignItems: 'center', gap: 10,
      }}>
        <button onClick={onOpenSettings} className="os1-iconbtn" title="Settings" style={{ padding: 4, marginLeft: -2 }}>
          <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7">
            <circle cx="12" cy="12" r="3.2" />
            <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1.03 1.56V21a2 2 0 1 1-4 0v-.09a1.7 1.7 0 0 0-1.11-1.56 1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.7 1.7 0 0 0 .34-1.87 1.7 1.7 0 0 0-1.56-1.03H3a2 2 0 1 1 0-4h.09a1.7 1.7 0 0 0 1.56-1.11 1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.7 1.7 0 0 0 1.87.34h.01a1.7 1.7 0 0 0 1.02-1.56V3a2 2 0 1 1 4 0v.09a1.7 1.7 0 0 0 1.03 1.56 1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.7 1.7 0 0 0-.34 1.87v.01a1.7 1.7 0 0 0 1.56 1.02H21a2 2 0 1 1 0 4h-.09a1.7 1.7 0 0 0-1.51 1.03z" />
          </svg>
        </button>
        <span className="font-pixel" style={{ fontSize: 11, color: 'var(--os1-text-dim)' }}>
          {memoryCount > 0 ? `${memoryCount} Memories Saved` : 'No Memories Yet'}
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
                background: 'rgba(0,0,0,0.6)',
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
