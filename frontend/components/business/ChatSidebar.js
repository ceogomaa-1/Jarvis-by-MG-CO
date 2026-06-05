'use client'
import { useState, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import TetrisLoader from '../ui/TetrisLoader'

const SIDEBAR_WIDTH = 280

function relativeTime(dateStr) {
  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now - date
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMs / 3600000)
  const diffDays = Math.floor(diffMs / 86400000)
  if (diffMins < 1) return 'just now'
  if (diffMins < 60) return `${diffMins}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  if (diffDays === 1) return 'Yesterday'
  if (diffDays < 7) return `${diffDays}d ago`
  return date.toLocaleDateString()
}

function groupConversations(conversations) {
  const now = new Date()
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const yesterdayStart = new Date(todayStart - 86400000)
  const weekStart = new Date(todayStart - 6 * 86400000)
  const groups = { today: [], yesterday: [], week: [], older: [] }
  for (const conv of conversations) {
    const d = new Date(conv.updated_at || conv.created_at)
    if (d >= todayStart) groups.today.push(conv)
    else if (d >= yesterdayStart) groups.yesterday.push(conv)
    else if (d >= weekStart) groups.week.push(conv)
    else groups.older.push(conv)
  }
  return groups
}

function GroupLabel({ label }) {
  return (
    <div className="font-arcade" style={{
      fontSize: 9, letterSpacing: '0.2em',
      color: 'rgba(243,234,217,0.3)', textTransform: 'uppercase',
      padding: '8px 16px 4px',
    }}>
      {label}
    </div>
  )
}

function ConversationItem({ conv, isActive, onSelect, onDelete }) {
  const [hovered, setHovered] = useState(false)
  const [showDelete, setShowDelete] = useState(false)

  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => { setHovered(false); setShowDelete(false) }}
      onClick={() => onSelect(conv.id)}
      style={{
        padding: '10px 16px',
        cursor: 'pointer',
        background: isActive
          ? 'rgba(200,75,49,0.08)'
          : hovered ? 'rgba(243,234,217,0.04)' : 'transparent',
        borderLeft: isActive ? '2px solid #c84b31' : '2px solid transparent',
        transition: 'all 150ms ease',
        display: 'flex', alignItems: 'flex-start', gap: 8, position: 'relative',
      }}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="font-arcade" style={{
          fontSize: 12,
          color: isActive ? '#f3ead9' : 'rgba(243,234,217,0.75)',
          whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
          lineHeight: 1.6,
        }}>
          {conv.title || 'New conversation'}
        </div>
        <div style={{
          fontSize: 10, color: 'rgba(243,234,217,0.25)',
          fontFamily: 'system-ui, sans-serif', marginTop: 2,
        }}>
          {relativeTime(conv.updated_at || conv.created_at)}
        </div>
      </div>

      {/* Delete button — shows on hover */}
      {hovered && (
        <button
          onClick={(e) => { e.stopPropagation(); onDelete(conv.id) }}
          style={{
            flexShrink: 0,
            width: 20, height: 20,
            background: 'transparent',
            border: 'none', cursor: 'pointer',
            color: 'rgba(243,234,217,0.25)',
            fontSize: 14, lineHeight: 1,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            borderRadius: 4,
            transition: 'color 150ms',
          }}
          onMouseEnter={e => e.currentTarget.style.color = 'rgba(200,75,49,0.7)'}
          onMouseLeave={e => e.currentTarget.style.color = 'rgba(243,234,217,0.25)'}
          title="Delete conversation"
        >
          ×
        </button>
      )}
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
}) {
  const [search, setSearch] = useState('')

  const filtered = useMemo(() => {
    if (!search.trim()) return conversations
    const q = search.toLowerCase()
    return conversations.filter(c => (c.title || '').toLowerCase().includes(q))
  }, [conversations, search])

  const groups = useMemo(() => groupConversations(filtered), [filtered])

  const renderGroup = (label, items) => {
    if (!items.length) return null
    return (
      <div key={label}>
        <GroupLabel label={label} />
        {items.map(conv => (
          <ConversationItem
            key={conv.id}
            conv={conv}
            isActive={conv.id === activeConversationId}
            onSelect={onSelectConversation}
            onDelete={onDeleteConversation}
          />
        ))}
      </div>
    )
  }

  const sidebarContent = (
    <div style={{
      width: SIDEBAR_WIDTH,
      height: '100%',
      background: 'rgba(10,10,10,0.97)',
      borderRight: '1px solid rgba(243,234,217,0.06)',
      display: 'flex', flexDirection: 'column',
      backdropFilter: 'blur(20px)',
      WebkitBackdropFilter: 'blur(20px)',
      flexShrink: 0,
    }}>
      {/* New chat button */}
      <div style={{ padding: '16px 12px 8px' }}>
        <button
          onClick={onNewChat}
          style={{
            width: '100%',
            background: 'rgba(243,234,217,0.04)',
            border: '1px solid rgba(243,234,217,0.08)',
            borderRadius: 12, padding: '10px 14px',
            color: 'rgba(243,234,217,0.65)',
            cursor: 'pointer',
            fontSize: 8,
            display: 'flex', alignItems: 'center', gap: 8,
            transition: 'all 200ms ease',
          }}
          onMouseEnter={e => {
            e.currentTarget.style.background = 'rgba(243,234,217,0.08)'
            e.currentTarget.style.color = 'rgba(243,234,217,0.9)'
          }}
          onMouseLeave={e => {
            e.currentTarget.style.background = 'rgba(243,234,217,0.04)'
            e.currentTarget.style.color = 'rgba(243,234,217,0.65)'
          }}
        >
          <span style={{ fontSize: 16, lineHeight: 1 }}>+</span>
          <span className="font-arcade" style={{ fontSize: 11, letterSpacing: '0.1em', textTransform: 'uppercase' }}>New chat</span>
        </button>
      </div>

      {/* Search */}
      <div style={{ padding: '4px 12px 8px' }}>
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search conversations…"
          style={{
            width: '100%', boxSizing: 'border-box',
            background: 'transparent',
            border: 'none',
            borderBottom: '1px solid rgba(243,234,217,0.06)',
            padding: '6px 4px',
            color: 'rgba(243,234,217,0.6)',
            fontFamily: 'var(--font-arcade), monospace', fontSize: 10,
            outline: 'none',
          }}
        />
      </div>

      {/* Conversation list */}
      <div style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden' }}
        className="biz-chat-scroll"
      >
        {loading ? (
          <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 32 }}>
            <TetrisLoader size="sm" speed="fast" showLoadingText={false} />
          </div>
        ) : filtered.length === 0 ? (
          <div style={{
            padding: '24px 16px',
            color: 'rgba(243,234,217,0.2)',
            fontSize: 10, fontFamily: 'var(--font-arcade), monospace',
            textAlign: 'center',
          }}>
            {search ? 'No matches' : 'No conversations yet'}
          </div>
        ) : (
          <>
            {renderGroup('Today', groups.today)}
            {renderGroup('Yesterday', groups.yesterday)}
            {renderGroup('Previous 7 days', groups.week)}
            {renderGroup('Older', groups.older)}
          </>
        )}
      </div>

      {/* Memory counter */}
      <div style={{
        padding: '12px 16px',
        borderTop: '1px solid rgba(243,234,217,0.04)',
        fontSize: 9, color: 'rgba(243,234,217,0.22)',
        fontFamily: 'var(--font-arcade), monospace',
      }}>
        {memoryCount > 0 ? `${memoryCount} memories learned` : 'No memories yet'}
      </div>
    </div>
  )

  // Desktop: always visible inline
  // Mobile: overlay slide-in
  return (
    <>
      {/* Desktop sidebar */}
      <div style={{ display: 'flex' }} className="business-sidebar-desktop">
        <style>{`
          @media (max-width: 768px) {
            .business-sidebar-desktop { display: none !important; }
          }
        `}</style>
        {sidebarContent}
      </div>

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
              initial={{ x: -SIDEBAR_WIDTH }}
              animate={{ x: 0 }}
              exit={{ x: -SIDEBAR_WIDTH }}
              transition={{ duration: 0.3, ease: 'easeOut' }}
              style={{
                position: 'fixed', top: 56, left: 0, bottom: 0,
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
