'use client'
import { useState, useMemo } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { PanelLeft, Search, Settings, Maximize2, X } from 'lucide-react'
import TetrisLoader from '../ui/TetrisLoader'

const SIDEBAR_WIDTH = 222

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
  if (diffDays < 7) return `${diffDays}d ago`
  return `${diffDays}d ago`
}

function trimTitle(title) {
  if (!title) return 'New chats'
  return title.length > 21 ? `${title.slice(0, 19)}...` : title
}

function ConversationCard({ conv, isActive, onSelect, onDelete }) {
  return (
    <button
      onClick={() => onSelect(conv.id)}
      className={`os1-conversation-card ${isActive ? 'is-active' : ''}`}
    >
      <div>
        <div className="os1-conversation-title">{trimTitle(conv.title || 'New chats')}</div>
        <div className="os1-conversation-time">{relativeTime(conv.updated_at || conv.created_at)}</div>
      </div>
      <span
        role="button"
        tabIndex={0}
        className="os1-conversation-remove"
        onClick={(e) => {
          e.stopPropagation()
          onDelete(conv.id)
        }}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            e.stopPropagation()
            onDelete(conv.id)
          }
        }}
        aria-label="Delete conversation"
      >
        <X size={12} strokeWidth={3} />
      </span>
    </button>
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

  const cards = filtered.slice(0, 7)

  const sidebarContent = (
    <aside className="os1-left-panel" style={{ width: SIDEBAR_WIDTH }}>
      <div className="os1-sidebar-top">
        <PanelLeft size={28} strokeWidth={2.7} />
      </div>

      <label className="os1-search-shell">
        <Search size={18} />
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search"
        />
      </label>

      <div className="os1-new-session-row">
        <button onClick={onNewChat}>New Session</button>
        <Maximize2 size={14} />
      </div>

      <div className="os1-session-rule" />

      <div className="os1-conversation-list">
        {loading ? (
          <div className="os1-sidebar-loader">
            <TetrisLoader size="sm" speed="fast" showLoadingText={false} />
          </div>
        ) : cards.length === 0 ? (
          <div className="os1-empty-card">{search ? 'No matches' : 'No conversations yet'}</div>
        ) : (
          cards.map(conv => (
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

      <div className="os1-sidebar-footer">
        <Settings size={20} />
        <span>{memoryCount > 0 ? `${memoryCount} Memories Saved` : 'No Memories Saved'}</span>
      </div>
    </aside>
  )

  return (
    <>
      <div className="business-sidebar-desktop">{sidebarContent}</div>

      <AnimatePresence>
        {isMobileOpen && (
          <>
            <motion.div
              key="overlay"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={onClose}
              className="os1-mobile-overlay"
            />
            <motion.div
              key="sidebar"
              initial={{ x: -SIDEBAR_WIDTH - 24 }}
              animate={{ x: 0 }}
              exit={{ x: -SIDEBAR_WIDTH - 24 }}
              transition={{ duration: 0.25, ease: 'easeOut' }}
              className="os1-mobile-sidebar"
            >
              {sidebarContent}
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </>
  )
}
