'use client'

import { useEffect, useMemo, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { listStudyNotes, deleteStudyNote, updateStudyNote, listStudyChats, deleteStudyChat } from '../../lib/studyApi'

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
  const [openNoteId, setOpenNoteId] = useState(null)   // expanded (view) note
  const [editId, setEditId] = useState(null)           // note being edited
  const [editText, setEditText] = useState('')
  const [editCat, setEditCat] = useState('')
  const [savingEdit, setSavingEdit] = useState(false)

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
  const startEdit = (n) => { setEditId(n.id); setEditText(n.content); setEditCat(n.category || 'General'); setOpenNoteId(n.id) }
  const saveEdit = async (id) => {
    const content = editText.trim()
    const category = editCat.trim() || 'General'
    if (!content) return
    setSavingEdit(true)
    setNotes(prev => prev.map(n => n.id === id ? { ...n, content, category } : n))
    try { await updateStudyNote(userId, id, { content, category }) } catch (e) { console.error(e) }
    setSavingEdit(false); setEditId(null)
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
                {items.map(n => {
                  const expanded = openNoteId === n.id
                  const editing = editId === n.id
                  const preview = (n.content || '').replace(/^#+\s*/gm, '').replace(/\s+/g, ' ').trim()
                  if (editing) {
                    return (
                      <div key={n.id} style={{ marginBottom: 8, background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,144,114,0.3)', borderRadius: 10, padding: 10 }}>
                        <input value={editCat} onChange={e => setEditCat(e.target.value)} placeholder="Subject"
                          style={{ width: '100%', boxSizing: 'border-box', marginBottom: 8, background: '#1A1A1A', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, padding: '7px 10px', color: CREAM, fontFamily: 'var(--sans)', fontSize: 12.5, outline: 'none' }} />
                        <textarea value={editText} onChange={e => setEditText(e.target.value)} rows={8}
                          style={{ width: '100%', boxSizing: 'border-box', resize: 'vertical', background: '#1A1A1A', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, padding: '8px 10px', color: CREAM, fontFamily: 'var(--sans)', fontSize: 13, lineHeight: 1.5, outline: 'none' }} />
                        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 8 }}>
                          <button onClick={() => setEditId(null)} style={{ background: 'none', border: 0, color: 'rgba(243,234,217,0.55)', cursor: 'pointer', fontFamily: 'var(--sans)', fontSize: 13, padding: '6px 10px' }}>Cancel</button>
                          <button onClick={() => saveEdit(n.id)} disabled={savingEdit} style={{ background: ACCENT, border: 0, borderRadius: 999, color: '#1a0e08', cursor: 'pointer', fontFamily: 'var(--sans)', fontSize: 13, fontWeight: 600, padding: '6px 16px' }}>{savingEdit ? 'Saving…' : 'Save'}</button>
                        </div>
                      </div>
                    )
                  }
                  return (
                    <div key={n.id} style={{ marginBottom: 6, background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 10, overflow: 'hidden' }}>
                      <div style={{ position: 'relative', padding: '10px 60px 10px 12px' }}>
                        <div
                          onClick={() => setOpenNoteId(expanded ? null : n.id)}
                          style={{ cursor: 'pointer', color: CREAM, fontFamily: 'var(--sans)' }}
                        >
                          {expanded ? (
                            <div className="study-prose study-note-prose">
                              <ReactMarkdown remarkPlugins={[remarkGfm]}>{n.content || ''}</ReactMarkdown>
                            </div>
                          ) : (
                            <div style={{ fontSize: 13.5, lineHeight: 1.5, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                              {preview || '(empty note)'}
                            </div>
                          )}
                        </div>
                        <button onClick={() => startEdit(n)} aria-label="edit note"
                          style={{ position: 'absolute', top: 8, right: 34, background: 'none', border: 0, color: 'rgba(243,234,217,0.4)', cursor: 'pointer', padding: 2 }}
                          onMouseEnter={e => e.currentTarget.style.color = ACCENT}
                          onMouseLeave={e => e.currentTarget.style.color = 'rgba(243,234,217,0.4)'}>
                          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" /><path d="M18.5 2.5a2.12 2.12 0 0 1 3 3L12 15l-4 1 1-4z" /></svg>
                        </button>
                        <button onClick={() => removeNote(n.id)} aria-label="delete note"
                          style={{ position: 'absolute', top: 8, right: 8, background: 'none', border: 0, color: 'rgba(243,234,217,0.35)', cursor: 'pointer', padding: 2 }}
                          onMouseEnter={e => e.currentTarget.style.color = '#fca5a5'}
                          onMouseLeave={e => e.currentTarget.style.color = 'rgba(243,234,217,0.35)'}>
                          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="3 6 5 6 21 6" /><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" /></svg>
                        </button>
                      </div>
                    </div>
                  )
                })}
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
