'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { supabase } from '../../lib/supabase'

const BACKEND = 'https://jarvis-backend-4oz6.onrender.com'

const SNOOZE_PRESETS = [
  { label: '+15m', value: 'in 15 minutes' },
  { label: '+1h', value: 'in 1 hour' },
  { label: 'Tonight', value: 'tonight' },
  { label: 'Tomorrow', value: 'tomorrow' },
  { label: '+1wk', value: 'in 1 week' },
]

function formatRemindAt(iso) {
  if (!iso) return null
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return null
  const now = new Date()
  const sameDay = d.toDateString() === now.toDateString()
  const opts = sameDay
    ? { hour: 'numeric', minute: '2-digit' }
    : { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }
  return d.toLocaleString(undefined, opts)
}

function isOverdue(note) {
  if (!note.remind_at || note.done) return false
  return new Date(note.remind_at).getTime() < Date.now()
}

function computeStreak(notes) {
  const days = new Set(
    notes.filter(n => n.done_at).map(n => new Date(n.done_at).toDateString())
  )
  if (days.size === 0) return 0
  let streak = 0
  const cursor = new Date()
  if (!days.has(cursor.toDateString())) cursor.setDate(cursor.getDate() - 1)
  while (days.has(cursor.toDateString())) {
    streak += 1
    cursor.setDate(cursor.getDate() - 1)
  }
  return streak
}

export default function NotesPanel({ userId, onClose }) {
  const [notes, setNotes] = useState([])
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState('active') // 'active' | 'done'
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState('newest') // 'newest' | 'reminder'
  const [newNote, setNewNote] = useState('')
  const [newRemind, setNewRemind] = useState('')
  const [adding, setAdding] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [editText, setEditText] = useState('')
  const [snoozeOpenId, setSnoozeOpenId] = useState(null)
  const [undoState, setUndoState] = useState(null) // { note }
  const undoTimeoutRef = useRef(null)
  const listRef = useRef(null)

  useEffect(() => {
    if (!userId) return
    let cancelled = false
    fetch(`${BACKEND}/api/notes/${userId}?include_done=true`)
      .then(r => r.json())
      .then(data => { if (!cancelled) setNotes(data.notes || []) })
      .catch(err => console.error('NotesPanel: load failed', err))
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [userId])

  // Realtime sync — keep panel live across tabs/devices
  useEffect(() => {
    if (!userId || !supabase) return
    const channel = supabase
      .channel(`personal_notes_${userId}`)
      .on('postgres_changes', {
        event: '*', schema: 'public', table: 'personal_notes', filter: `user_id=eq.${userId}`,
      }, (payload) => {
        setNotes(prev => {
          if (payload.eventType === 'INSERT') {
            if (prev.some(n => n.id === payload.new.id)) return prev
            return [payload.new, ...prev]
          }
          if (payload.eventType === 'UPDATE') {
            return prev.map(n => n.id === payload.new.id ? payload.new : n)
          }
          if (payload.eventType === 'DELETE') {
            return prev.filter(n => n.id !== payload.old.id)
          }
          return prev
        })
      })
      .subscribe()
    return () => { supabase.removeChannel(channel) }
  }, [userId])

  // Deep-link — open straight to a note via #notes=<id>
  useEffect(() => {
    if (loading || typeof window === 'undefined') return
    const hash = window.location.hash
    const m = hash.match(/^#notes=(.+)$/)
    if (!m) return
    const target = notes.find(n => n.id === m[1])
    if (target && target.done) setTab('done')
    const el = listRef.current?.querySelector(`[data-note-id="${m[1]}"]`)
    if (el) {
      el.scrollIntoView({ block: 'center' })
      el.style.transition = 'background 1.2s ease'
      el.style.background = 'rgba(255,144,114,0.18)'
      setTimeout(() => { el.style.background = 'transparent' }, 100)
    }
  }, [loading, notes])

  const streak = useMemo(() => computeStreak(notes), [notes])

  const visible = useMemo(() => {
    let list = notes.filter(n => tab === 'done' ? n.done : !n.done)
    if (search.trim()) {
      const q = search.trim().toLowerCase()
      list = list.filter(n => n.note.toLowerCase().includes(q))
    }
    list = [...list]
    if (sort === 'reminder') {
      list.sort((a, b) => {
        if (!a.remind_at && !b.remind_at) return new Date(b.created_at) - new Date(a.created_at)
        if (!a.remind_at) return 1
        if (!b.remind_at) return -1
        return new Date(a.remind_at) - new Date(b.remind_at)
      })
    } else {
      list.sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
    }
    return list
  }, [notes, tab, search, sort])

  const activeCount = notes.filter(n => !n.done).length
  const doneCount = notes.filter(n => n.done).length

  const handleAdd = async (e) => {
    e.preventDefault()
    const note = newNote.trim()
    if (!note || adding) return
    setAdding(true)
    try {
      const res = await fetch(`${BACKEND}/api/notes/${userId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ note, remind_at: newRemind.trim() || null }),
      })
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      setNotes(prev => prev.some(n => n.id === data.note.id) ? prev : [data.note, ...prev])
      setNewNote('')
      setNewRemind('')
    } catch (err) {
      console.error('NotesPanel: add failed', err)
    } finally {
      setAdding(false)
    }
  }

  const toggleDone = async (note) => {
    const done = !note.done
    const prevNote = note
    setNotes(prev => prev.map(n => n.id === note.id ? { ...n, done, done_at: done ? new Date().toISOString() : null } : n))
    try {
      const res = await fetch(`${BACKEND}/api/notes/${userId}/${note.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ done }),
      })
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      setNotes(prev => prev.map(n => n.id === note.id ? data.note : n))
    } catch (err) {
      console.error('NotesPanel: toggle done failed', err)
      setNotes(prev => prev.map(n => n.id === note.id ? prevNote : n))
    }
  }

  const startEdit = (note) => {
    setEditingId(note.id)
    setEditText(note.note)
  }

  const saveEdit = async (note) => {
    const text = editText.trim()
    setEditingId(null)
    if (!text || text === note.note) return
    setNotes(prev => prev.map(n => n.id === note.id ? { ...n, note: text } : n))
    try {
      const res = await fetch(`${BACKEND}/api/notes/${userId}/${note.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ note: text }),
      })
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      setNotes(prev => prev.map(n => n.id === note.id ? data.note : n))
    } catch (err) {
      console.error('NotesPanel: edit failed', err)
    }
  }

  const snooze = async (note, value) => {
    setSnoozeOpenId(null)
    try {
      const res = await fetch(`${BACKEND}/api/notes/${userId}/${note.id}/snooze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ remind_at: value }),
      })
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      setNotes(prev => prev.map(n => n.id === note.id ? data.note : n))
    } catch (err) {
      console.error('NotesPanel: snooze failed', err)
    }
  }

  const deleteNote = (note) => {
    setNotes(prev => prev.filter(n => n.id !== note.id))
    if (undoTimeoutRef.current) clearTimeout(undoTimeoutRef.current)
    setUndoState({ note })
    undoTimeoutRef.current = setTimeout(async () => {
      try {
        await fetch(`${BACKEND}/api/notes/${userId}/${note.id}`, { method: 'DELETE' })
      } catch (err) {
        console.error('NotesPanel: delete failed', err)
      }
      setUndoState(curr => curr?.note.id === note.id ? null : curr)
    }, 5000)
  }

  const undoDelete = () => {
    if (!undoState) return
    if (undoTimeoutRef.current) clearTimeout(undoTimeoutRef.current)
    setNotes(prev => prev.some(n => n.id === undoState.note.id) ? prev : [undoState.note, ...prev])
    setUndoState(null)
  }

  return (
    <>
      <div className="fixed inset-0 z-40" style={{ backgroundColor: 'rgba(0,0,0,0.4)' }} onClick={onClose} />
      <div className="panel-slide fixed top-0 right-0 h-full z-50 overflow-y-auto" style={{
        width: '360px', maxWidth: '100vw', backgroundColor: '#0f0e0c',
        borderLeft: '1px solid var(--line)', padding: '1.5rem',
        display: 'flex', flexDirection: 'column',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <p style={{ fontFamily: 'var(--sans)', color: 'var(--accent)', fontSize: '0.65rem', letterSpacing: '0.2em', textTransform: 'uppercase', margin: 0 }}>
              Jarvis Notes
            </p>
            {streak > 0 && (
              <span style={{
                fontFamily: 'var(--sans)', fontSize: '0.65rem', color: 'var(--ink)',
                background: 'rgba(255,144,114,0.1)', border: '1px solid rgba(255,144,114,0.25)',
                borderRadius: 999, padding: '0.1rem 0.5rem', opacity: 0.85,
              }}>
                🔥 {streak}-day streak
              </span>
            )}
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'var(--ink-mute)', cursor: 'pointer', fontSize: '1.1rem', lineHeight: 1 }}>
            ×
          </button>
        </div>

        {/* Quick add */}
        <form onSubmit={handleAdd} style={{ marginBottom: '1rem', display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
          <input
            type="text"
            value={newNote}
            onChange={e => setNewNote(e.target.value)}
            placeholder="Add a note..."
            style={{
              width: '100%', background: 'rgba(243,234,217,0.04)', border: '1px solid var(--line)',
              borderRadius: 8, padding: '0.5rem 0.7rem', color: 'var(--ink)',
              fontFamily: 'var(--sans)', fontSize: '0.82rem', outline: 'none',
            }}
          />
          <div style={{ display: 'flex', gap: '0.4rem' }}>
            <input
              type="text"
              value={newRemind}
              onChange={e => setNewRemind(e.target.value)}
              placeholder='Remind me... (optional, e.g. "tomorrow at 9am")'
              style={{
                flex: 1, background: 'rgba(243,234,217,0.04)', border: '1px solid var(--line)',
                borderRadius: 8, padding: '0.45rem 0.7rem', color: 'var(--ink-mute)',
                fontFamily: 'var(--sans)', fontSize: '0.72rem', outline: 'none',
              }}
            />
            <button
              type="submit"
              disabled={!newNote.trim() || adding}
              style={{
                flexShrink: 0, padding: '0.45rem 0.9rem', borderRadius: 8,
                background: newNote.trim() ? 'var(--accent)' : 'rgba(243,234,217,0.06)',
                color: newNote.trim() ? '#1a0e08' : 'var(--ink-mute)',
                border: 0, cursor: newNote.trim() ? 'pointer' : 'default',
                fontFamily: 'var(--sans)', fontSize: '0.72rem', letterSpacing: '0.1em', textTransform: 'uppercase',
              }}
            >
              Add
            </button>
          </div>
        </form>

        {/* Tabs */}
        <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.6rem' }}>
          {[['active', `Active (${activeCount})`], ['done', `Done (${doneCount})`]].map(([key, label]) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              style={{
                flex: 1, padding: '0.4rem 0.5rem', borderRadius: 8,
                background: tab === key ? 'rgba(255,144,114,0.1)' : 'transparent',
                border: `1px solid ${tab === key ? 'rgba(255,144,114,0.25)' : 'var(--line)'}`,
                color: tab === key ? 'var(--accent)' : 'var(--ink-mute)',
                cursor: 'pointer', fontFamily: 'var(--sans)', fontSize: '0.68rem',
                letterSpacing: '0.1em', textTransform: 'uppercase',
              }}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Search + sort */}
        <div style={{ display: 'flex', gap: '0.4rem', marginBottom: '0.75rem' }}>
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search notes..."
            style={{
              flex: 1, background: 'rgba(243,234,217,0.04)', border: '1px solid var(--line)',
              borderRadius: 8, padding: '0.35rem 0.6rem', color: 'var(--ink)',
              fontFamily: 'var(--sans)', fontSize: '0.72rem', outline: 'none',
            }}
          />
          <select
            value={sort}
            onChange={e => setSort(e.target.value)}
            style={{
              background: 'rgba(243,234,217,0.04)', border: '1px solid var(--line)',
              borderRadius: 8, padding: '0.35rem 0.4rem', color: 'var(--ink-mute)',
              fontFamily: 'var(--sans)', fontSize: '0.68rem', outline: 'none',
            }}
          >
            <option value="newest">Newest</option>
            <option value="reminder">By reminder</option>
          </select>
        </div>

        {/* Notes list */}
        <div ref={listRef} style={{ flex: 1, overflowY: 'auto' }}>
          {loading ? (
            <p style={{ fontFamily: 'var(--sans)', color: 'var(--ink-mute)', fontSize: '0.8rem' }}>Loading...</p>
          ) : visible.length === 0 ? (
            <p style={{ fontFamily: 'var(--sans)', color: 'var(--ink-mute)', fontSize: '0.8rem' }}>
              {tab === 'done' ? 'Nothing completed yet.' : 'No active notes — add one above.'}
            </p>
          ) : visible.map(note => {
            const remindLabel = formatRemindAt(note.remind_at)
            const overdue = isOverdue(note)
            return (
              <div
                key={note.id}
                data-note-id={note.id}
                style={{
                  display: 'flex', alignItems: 'flex-start', gap: '0.6rem',
                  padding: '0.6rem 0.4rem', borderBottom: '1px solid rgba(243,234,217,0.05)',
                  borderRadius: 6,
                }}
              >
                <input
                  type="checkbox"
                  checked={!!note.done}
                  onChange={() => toggleDone(note)}
                  style={{ marginTop: '0.2rem', accentColor: 'var(--accent)', cursor: 'pointer', flexShrink: 0 }}
                />
                <div style={{ flex: 1, minWidth: 0 }}>
                  {editingId === note.id ? (
                    <input
                      autoFocus
                      type="text"
                      value={editText}
                      onChange={e => setEditText(e.target.value)}
                      onBlur={() => saveEdit(note)}
                      onKeyDown={e => {
                        if (e.key === 'Enter') saveEdit(note)
                        if (e.key === 'Escape') setEditingId(null)
                      }}
                      style={{
                        width: '100%', background: 'rgba(243,234,217,0.06)', border: '1px solid var(--line)',
                        borderRadius: 6, padding: '0.2rem 0.4rem', color: 'var(--ink)',
                        fontFamily: 'var(--sans)', fontSize: '0.8rem', outline: 'none',
                      }}
                    />
                  ) : (
                    <p
                      onClick={() => !note.done && startEdit(note)}
                      style={{
                        fontFamily: 'var(--sans)', fontSize: '0.8rem', color: 'var(--ink)',
                        margin: 0, lineHeight: 1.5, opacity: note.done ? 0.45 : 0.9,
                        textDecoration: note.done ? 'line-through' : 'none',
                        cursor: note.done ? 'default' : 'text',
                        wordBreak: 'break-word',
                      }}
                    >
                      {note.note}
                    </p>
                  )}

                  {(remindLabel || !note.done) && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginTop: '0.3rem', flexWrap: 'wrap' }}>
                      {remindLabel && (
                        <span style={{
                          fontFamily: 'var(--sans)', fontSize: '0.62rem',
                          color: overdue ? '#fca5a5' : 'var(--ink-mute)',
                          letterSpacing: '0.05em',
                        }}>
                          {overdue ? '⏰ overdue · ' : '⏰ '}{remindLabel}
                        </span>
                      )}
                      {!note.done && (
                        <div style={{ position: 'relative' }}>
                          <button
                            onClick={() => setSnoozeOpenId(snoozeOpenId === note.id ? null : note.id)}
                            style={{
                              background: 'none', border: 'none', color: 'var(--ink-mute)',
                              cursor: 'pointer', fontFamily: 'var(--sans)', fontSize: '0.62rem',
                              letterSpacing: '0.05em', padding: 0,
                            }}
                          >
                            snooze ▾
                          </button>
                          {snoozeOpenId === note.id && (
                            <div style={{
                              position: 'absolute', top: '1.2rem', left: 0, zIndex: 10,
                              background: '#1a1815', border: '1px solid var(--line)',
                              borderRadius: 8, padding: '0.3rem', display: 'flex', gap: '0.25rem',
                              boxShadow: '0 4px 12px rgba(0,0,0,0.4)',
                            }}>
                              {SNOOZE_PRESETS.map(p => (
                                <button
                                  key={p.label}
                                  onClick={() => snooze(note, p.value)}
                                  style={{
                                    background: 'rgba(243,234,217,0.05)', border: '1px solid var(--line)',
                                    borderRadius: 6, padding: '0.2rem 0.4rem', color: 'var(--ink)',
                                    cursor: 'pointer', fontFamily: 'var(--sans)', fontSize: '0.62rem', whiteSpace: 'nowrap',
                                  }}
                                >
                                  {p.label}
                                </button>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
                <button
                  onClick={() => deleteNote(note)}
                  aria-label="Delete note"
                  style={{
                    background: 'none', border: 'none', color: 'var(--ink-mute)',
                    cursor: 'pointer', flexShrink: 0, padding: '0.1rem',
                    opacity: 0.6,
                  }}
                  onMouseEnter={e => e.currentTarget.style.color = '#fca5a5'}
                  onMouseLeave={e => e.currentTarget.style.color = 'var(--ink-mute)'}
                >
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="3 6 5 6 21 6" />
                    <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                  </svg>
                </button>
              </div>
            )
          })}
        </div>

        {/* Undo toast */}
        {undoState && (
          <div style={{
            position: 'absolute', bottom: '1rem', left: '1rem', right: '1rem',
            background: '#1a1815', border: '1px solid var(--line)', borderRadius: 8,
            padding: '0.6rem 0.8rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            boxShadow: '0 4px 16px rgba(0,0,0,0.5)',
          }}>
            <span style={{ fontFamily: 'var(--sans)', fontSize: '0.72rem', color: 'var(--ink-mute)' }}>
              Note deleted
            </span>
            <button
              onClick={undoDelete}
              style={{
                background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer',
                fontFamily: 'var(--sans)', fontSize: '0.72rem', letterSpacing: '0.1em', textTransform: 'uppercase',
              }}
            >
              Undo
            </button>
          </div>
        )}
      </div>
    </>
  )
}
