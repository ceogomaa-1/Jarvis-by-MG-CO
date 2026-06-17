'use client'

import { useEffect, useMemo, useState } from 'react'
import { listStudyNotes, deleteStudyNote, listStudyChats, deleteStudyChat } from '../../lib/studyApi'

const CREAM = '#F3EAD9'
const ACCENT = 'var(--accent, #ff9072)'

// Left side drawer for Study Mode (opened by the hamburger).
// Two tabs: Notes (categorized) and Chats (history + new chat).
export default function StudyDrawer({
  open, onClose, userId,
  currentChatId, onSelectChat, onNewChat,
  refreshKey,
}) {
  const [tab, setTab] = useState('notes')
  const [notes, setNotes] = useState([])
  const [chats, setChats] = useState([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!open || !userId) return
    let cancelled = false
    setLoading(true)
    Promise.all([listStudyNotes(userId), listStudyChats(userId)])
      .then(([n, c]) => { if (!cancelled) { setNotes(n); setChats(c) } })
      .catch(err => console.error('[StudyDrawer] load failed', err))
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [open, userId, refreshKey])

  // Group notes by category
  const grouped = useMemo(() => {
    const map = new Map()
    for (const n of notes) {
      const cat = n.category || 'General'
      if (!map.has(cat)) map.set(cat, [])
      map.get(cat).push(n)
    }
    return [...map.entries()].sort((a, b) => a[0].localeCompare(b[0]))
  }, [notes])

  const removeNote = async (id) => {
    setNotes(prev => prev.filter(n => n.id !== id))
    try { await deleteStudyNote(userId, id) } catch (e) { console.error(e) }
  }
  const removeChat = async (id) => {
    setChats(prev => prev.filter(c => c.id !== id))
    try { await deleteStudyChat(userId, id) } catch (e) { console.error(e) }
    if (id === currentChatId) onNewChat?.()
  }

  if (!open) return null

  return (
    <>
      <div onClick={onClose} style={{ position: 'fixed', inset: 0, zIndex: 30, background: 'rgba(0,0,0,0.5)' }} />
      <div style={{
        position: 'fixed', top: 0, left: 0, bottom: 0, zIndex: 31,
        width: 320, maxWidth: '88vw', background: '#202020',
        borderRight: '1px solid rgba(255,255,255,0.08)',
        display: 'flex', flexDirection: 'column',
        animation: 'slideInLeft 240ms ease both',
      }}>
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px 16px 8px' }}>
          <span style={{ fontFamily: 'var(--font-display-round), var(--sans)', fontSize: 18, fontWeight: 600, color: CREAM }}>
            Study
          </span>
          <button onClick={onClose} aria-label="close" style={{ background: 'none', border: 0, color: 'rgba(243,234,217,0.6)', fontSize: 22, lineHeight: 1, cursor: 'pointer' }}>×</button>
        </div>

        {/* New chat */}
        <div style={{ padding: '4px 12px 10px' }}>
          <button
            onClick={() => { onNewChat?.(); onClose?.() }}
            style={{
              width: '100%', display: 'flex', alignItems: 'center', gap: 10,
              padding: '11px 14px', borderRadius: 12, cursor: 'pointer',
              background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.08)',
              color: CREAM, fontFamily: 'var(--sans)', fontSize: 14, fontWeight: 500,
            }}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M12 5v14M5 12h14" />
            </svg>
            New chat
          </button>
        </div>

        {/* Tabs */}
        <div style={{ display: 'flex', gap: 6, padding: '0 12px 10px' }}>
          {[['notes', 'Notes'], ['chats', 'Chats']].map(([key, label]) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              style={{
                flex: 1, padding: '7px 0', borderRadius: 9, cursor: 'pointer',
                background: tab === key ? 'rgba(255,144,114,0.14)' : 'transparent',
                border: `1px solid ${tab === key ? 'rgba(255,144,114,0.3)' : 'rgba(255,255,255,0.08)'}`,
                color: tab === key ? ACCENT : 'rgba(243,234,217,0.55)',
                fontFamily: 'var(--sans)', fontSize: 12, letterSpacing: '0.08em', textTransform: 'uppercase',
              }}
            >{label}</button>
          ))}
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: '0 12px 16px' }}>
          {loading && <p style={{ color: 'rgba(243,234,217,0.4)', fontFamily: 'var(--sans)', fontSize: 13, padding: '8px 4px' }}>Loading…</p>}

          {/* ── NOTES ── */}
          {tab === 'notes' && !loading && (
            grouped.length === 0 ? (
              <p style={{ color: 'rgba(243,234,217,0.4)', fontFamily: 'var(--sans)', fontSize: 13, padding: '8px 4px', lineHeight: 1.5 }}>
                No notes yet. Tap “Capture a note” to save one — they’ll appear here, grouped by subject.
              </p>
            ) : grouped.map(([cat, items]) => (
              <div key={cat} style={{ marginBottom: 16 }}>
                <div style={{ fontFamily: 'var(--sans)', fontSize: 10.5, letterSpacing: '0.16em', textTransform: 'uppercase', color: ACCENT, opacity: 0.85, margin: '6px 4px 8px' }}>
                  {cat} · {items.length}
                </div>
                {items.map(n => (
                  <div key={n.id} style={{
                    position: 'relative', padding: '10px 32px 10px 12px', marginBottom: 6,
                    background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.06)',
                    borderRadius: 10, color: CREAM, fontFamily: 'var(--sans)', fontSize: 13.5, lineHeight: 1.5,
                    whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                  }}>
                    {n.content}
                    <button
                      onClick={() => removeNote(n.id)}
                      aria-label="delete note"
                      style={{ position: 'absolute', top: 8, right: 8, background: 'none', border: 0, color: 'rgba(243,234,217,0.35)', cursor: 'pointer', padding: 2 }}
                      onMouseEnter={e => e.currentTarget.style.color = '#fca5a5'}
                      onMouseLeave={e => e.currentTarget.style.color = 'rgba(243,234,217,0.35)'}
                    >
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="3 6 5 6 21 6" /><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                      </svg>
                    </button>
                  </div>
                ))}
              </div>
            ))
          )}

          {/* ── CHATS ── */}
          {tab === 'chats' && !loading && (
            chats.length === 0 ? (
              <p style={{ color: 'rgba(243,234,217,0.4)', fontFamily: 'var(--sans)', fontSize: 13, padding: '8px 4px' }}>
                No chats yet. Start one and it’ll be saved here.
              </p>
            ) : chats.map(c => (
              <div key={c.id} style={{ position: 'relative', marginBottom: 4 }}>
                <button
                  onClick={() => { onSelectChat?.(c.id); onClose?.() }}
                  style={{
                    width: '100%', textAlign: 'left', padding: '11px 32px 11px 12px', borderRadius: 10, cursor: 'pointer',
                    background: c.id === currentChatId ? 'rgba(255,144,114,0.12)' : 'rgba(255,255,255,0.03)',
                    border: `1px solid ${c.id === currentChatId ? 'rgba(255,144,114,0.28)' : 'rgba(255,255,255,0.06)'}`,
                    color: CREAM, fontFamily: 'var(--sans)', fontSize: 13.5,
                    whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                  }}
                >
                  {c.title || 'New chat'}
                </button>
                <button
                  onClick={() => removeChat(c.id)}
                  aria-label="delete chat"
                  style={{ position: 'absolute', top: '50%', right: 8, transform: 'translateY(-50%)', background: 'none', border: 0, color: 'rgba(243,234,217,0.3)', cursor: 'pointer', padding: 2 }}
                  onMouseEnter={e => e.currentTarget.style.color = '#fca5a5'}
                  onMouseLeave={e => e.currentTarget.style.color = 'rgba(243,234,217,0.3)'}
                >
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="3 6 5 6 21 6" /><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                  </svg>
                </button>
              </div>
            ))
          )}
        </div>
      </div>
    </>
  )
}
