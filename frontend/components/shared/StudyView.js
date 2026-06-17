'use client'

import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

// ─────────────────────────────────────────────────────────────────────────────
// Study Mode — Jarvis Personal
//
// A self-contained study surface that streams to the SAME chat backend with
// study_mode:true (the tutor brain). Normal chat is left untouched.
//   • Capture a note → real note saved to /api/notes (shows in Jarvis Notes)
//   • Quick Quiz / Summarize / Research → tutor starter prompts
//   • Photo-capture → snap/attach an image (textbook page, problem, handwriting)
//     and the tutor reads + teaches from it
// ─────────────────────────────────────────────────────────────────────────────

const CREAM = '#F3EAD9'

// ─── Toggle pill ──────────────────────────────────────────────────────────────
// Stays in the SAME top-right position in both views. Only its label + switch
// state change. studyMode=false → "Study Mode" (OFF). studyMode=true → "Normal Chat" (ON).
export function StudyToggle({ studyMode, onToggle }) {
  const label = studyMode ? 'Normal Chat' : 'Study Mode'
  const on = studyMode
  return (
    <button
      onClick={onToggle}
      aria-label={studyMode ? 'Switch to Normal Chat' : 'Switch to Study Mode'}
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 9,
        padding: '6px 10px 6px 14px',
        background: '#2A2A2A',
        border: '1px solid rgba(255,255,255,0.12)',
        borderRadius: 999,
        cursor: 'pointer',
        userSelect: 'none',
        whiteSpace: 'nowrap',
      }}
    >
      <span style={{
        fontFamily: 'var(--sans)', fontSize: 12.5, color: CREAM,
        letterSpacing: '0.01em', fontWeight: 400,
      }}>
        {label}
      </span>
      <span style={{
        position: 'relative', width: 34, height: 20, borderRadius: 999,
        background: on ? 'var(--accent, #ff9072)' : 'rgba(255,255,255,0.18)',
        transition: 'background 220ms ease', flexShrink: 0,
      }}>
        <span style={{
          position: 'absolute', top: 2, left: on ? 16 : 2,
          width: 16, height: 16, borderRadius: '50%',
          background: '#fff',
          transition: 'left 220ms cubic-bezier(0.4,0,0.2,1)',
          boxShadow: '0 1px 3px rgba(0,0,0,0.35)',
        }} />
      </span>
    </button>
  )
}

// ─── Quick action button ──────────────────────────────────────────────────────
function ActionButton({ label, onClick }) {
  return (
    <button
      onClick={onClick}
      style={{
        width: 150, height: 58,
        background: 'rgba(255,255,255,0.06)',
        border: '1px solid rgba(255,255,255,0.05)',
        borderRadius: 18,
        color: CREAM,
        fontFamily: 'var(--sans)', fontSize: 15, fontWeight: 500,
        letterSpacing: '0.01em',
        cursor: 'pointer',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        transition: 'background 180ms ease',
      }}
      onMouseEnter={e => { e.currentTarget.style.background = 'rgba(255,255,255,0.10)' }}
      onMouseLeave={e => { e.currentTarget.style.background = 'rgba(255,255,255,0.06)' }}
    >
      {label}
    </button>
  )
}

// ─── Greeting helper ──────────────────────────────────────────────────────────
function timeOfDay() {
  const h = new Date().getHours()
  if (h < 12) return 'Good Morning'
  if (h < 18) return 'Good Afternoon'
  return 'Good Evening'
}

const fileToDataUrl = (file) => new Promise((resolve, reject) => {
  const r = new FileReader()
  r.onload = () => resolve(r.result)
  r.onerror = reject
  r.readAsDataURL(file)
})

// ─── Study view ───────────────────────────────────────────────────────────────
export default function StudyView({ name, onToggle, onMenu, userId, backend }) {
  const displayName = name || 'there'
  const BACKEND = backend

  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [pendingPhoto, setPendingPhoto] = useState(null) // { dataUrl, type }

  // Note composer
  const [noteOpen, setNoteOpen] = useState(false)
  const [noteText, setNoteText] = useState('')
  const [noteRemind, setNoteRemind] = useState('')
  const [noteSaving, setNoteSaving] = useState(false)

  const msgIdRef = useRef(1)
  const abortRef = useRef(null)
  const scrollRef = useRef(null)
  const photoInputRef = useRef(null)
  const hasConversation = messages.length > 0

  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }, [messages, loading])

  // ── Stream a message to the tutor brain ───────────────────────────────────
  async function send(text, photo) {
    const apiText = (text ?? '').trim()
    if ((!apiText && !photo) || loading) return

    msgIdRef.current += 1
    const userId_ = msgIdRef.current
    setMessages(prev => [...prev, {
      id: userId_, role: 'user', content: apiText, imagePreview: photo?.dataUrl ?? null,
    }])
    setInput('')
    setPendingPhoto(null)
    setLoading(true)

    const historyForApi = messages
      .filter(m => typeof m.content === 'string' && m.content.trim().length > 0)
      .map(({ role, content }) => ({ role, content }))

    const body = {
      user_id: userId,
      message: apiText || 'Please look at this and help me study it.',
      conversation_history: historyForApi,
      study_mode: true,
    }
    if (photo) {
      body.image_base64 = photo.dataUrl
      body.image_type = photo.type || 'image/png'
    }

    let streamId = null
    try {
      const controller = new AbortController()
      abortRef.current = controller
      const res = await fetch(`${BACKEND}/api/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: controller.signal,
      })
      if (!res.ok) throw new Error(`${res.status}`)

      msgIdRef.current += 1
      streamId = msgIdRef.current
      setMessages(prev => [...prev, { id: streamId, role: 'assistant', content: '', streaming: true }])
      setLoading(false)

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let accumulated = ''
      let done = false

      while (!done) {
        const { done: rDone, value } = await reader.read()
        if (rDone) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const raw = line.slice(6)
          if (raw === '[DONE]') {
            setMessages(prev => prev.map(m => m.id === streamId ? { ...m, content: accumulated, streaming: false } : m))
            done = true
            break
          }
          if (raw === '[ERROR]') {
            setMessages(prev => prev.filter(m => m.id !== streamId))
            done = true
            break
          }
          if (raw.startsWith('[DEBUG:')) continue
          try {
            const chunk = JSON.parse(raw)
            if (chunk && typeof chunk === 'object') {
              if (chunk.__vs || Array.isArray(chunk.__sources) || chunk.type === 'usage') continue
            }
            accumulated += chunk
            setMessages(prev => prev.map(m => m.id === streamId ? { ...m, content: accumulated } : m))
          } catch {}
        }
      }
    } catch (err) {
      console.error('[StudyMode] send failed', err)
      if (streamId) setMessages(prev => prev.filter(m => m.id !== streamId))
      msgIdRef.current += 1
      setMessages(prev => [...prev, {
        id: msgIdRef.current, role: 'assistant',
        content: "Hit a snag reaching the tutor. Try that again?",
      }])
    } finally {
      setLoading(false)
    }
  }

  // ── Quick actions ──────────────────────────────────────────────────────────
  const actions = {
    note: () => setNoteOpen(true),
    quiz: () => send('Quiz me. Ask one question at a time, wait for my answer, then give feedback before the next one.'),
    summarize: () => send('Summarize the key points of what we have been studying into tight, easy-to-revise notes.'),
    research: () => send('I want to research a topic. Ask me what I want to learn about, then give me a clear, sourced overview.'),
  }

  // ── Photo capture (camera button) ──────────────────────────────────────────
  const onPhotoPicked = async (e) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    try {
      const dataUrl = await fileToDataUrl(file)
      setPendingPhoto({ dataUrl, type: file.type })
    } catch (err) {
      console.error('[StudyMode] photo read failed', err)
    }
  }

  // ── Save a structured note ─────────────────────────────────────────────────
  const saveNote = async () => {
    const note = noteText.trim()
    if (!note || noteSaving) return
    setNoteSaving(true)
    try {
      const res = await fetch(`${BACKEND}/api/notes/${userId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ note, remind_at: noteRemind.trim() || null }),
      })
      if (!res.ok) throw new Error(await res.text())
      setNoteOpen(false)
      setNoteText('')
      setNoteRemind('')
      msgIdRef.current += 1
      setMessages(prev => [...prev, {
        id: msgIdRef.current, role: 'assistant',
        content: `Saved to your notes ✓${noteRemind.trim() ? ` — I'll remind you ${noteRemind.trim()}.` : ''}\n\nWant me to quiz you on it or break it down?`,
      }])
    } catch (err) {
      console.error('[StudyMode] save note failed', err)
    } finally {
      setNoteSaving(false)
    }
  }

  const submit = () => send(input, pendingPhoto)

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 5,
      background: '#1A1A1A',
      display: 'flex', flexDirection: 'column',
      animation: 'fadeUp 300ms ease both',
    }}>
      {/* Header */}
      <div style={{
        height: 56, flexShrink: 0,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '0 18px',
      }}>
        <button
          onClick={onMenu}
          aria-label="menu"
          style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 6, display: 'flex', flexDirection: 'column', gap: 5, alignItems: 'center' }}
        >
          <span style={{ display: 'block', width: 22, height: 2, background: CREAM, borderRadius: 1 }} />
          <span style={{ display: 'block', width: 22, height: 2, background: CREAM, borderRadius: 1 }} />
          <span style={{ display: 'block', width: 22, height: 2, background: CREAM, borderRadius: 1 }} />
        </button>
        <StudyToggle studyMode={true} onToggle={onToggle} />
      </div>

      {!hasConversation ? (
        /* ── Empty state: orb + greeting + 2×2 actions ───────────────────── */
        <div style={{
          flex: 1, minHeight: 0,
          display: 'flex', flexDirection: 'column', alignItems: 'center',
          paddingTop: 32, overflowY: 'auto',
        }}>
          <img
            src="/jarvis-logo-mono.png"
            alt=""
            style={{ width: 77, height: 77, objectFit: 'contain', userSelect: 'none' }}
            draggable={false}
          />
          <div style={{
            marginTop: 22,
            fontFamily: 'var(--font-display-round), var(--sans)',
            fontSize: 24, fontWeight: 600, color: CREAM,
            textAlign: 'center', letterSpacing: '0.01em',
          }}>
            {timeOfDay()}, {displayName}
          </div>
          <div style={{
            marginTop: 56,
            display: 'grid', gridTemplateColumns: 'repeat(2, 150px)', gap: 16,
          }}>
            <ActionButton label="Capture a note" onClick={actions.note} />
            <ActionButton label="Quick Quiz" onClick={actions.quiz} />
            <ActionButton label="Summarize" onClick={actions.summarize} />
            <ActionButton label="Research" onClick={actions.research} />
          </div>
        </div>
      ) : (
        /* ── Conversation thread ─────────────────────────────────────────── */
        <div ref={scrollRef} style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '8px 18px 16px' }}>
          <div style={{ maxWidth: 640, margin: '0 auto' }}>
            {messages.map(m => (
              <StudyMessage key={m.id} msg={m} />
            ))}
            {loading && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'rgba(243,234,217,0.5)', fontFamily: 'var(--sans)', fontSize: 13, margin: '8px 0' }}>
                <span style={{ width: 7, height: 7, borderRadius: '50%', background: 'var(--accent, #ff9072)', animation: 'inkPulse 1s ease-in-out infinite' }} />
                thinking…
              </div>
            )}
          </div>
        </div>
      )}

      {/* Light input bar pinned to bottom */}
      <div style={{ flexShrink: 0, padding: '0 16px 20px' }}>
        {pendingPhoto && (
          <div style={{ maxWidth: 393, margin: '0 auto 8px', display: 'flex' }}>
            <div style={{ position: 'relative' }}>
              <img src={pendingPhoto.dataUrl} alt="" style={{ height: 64, borderRadius: 10, objectFit: 'cover', display: 'block', border: '1px solid rgba(255,255,255,0.15)' }} />
              <button
                onClick={() => setPendingPhoto(null)}
                aria-label="remove photo"
                style={{ position: 'absolute', top: -7, right: -7, width: 20, height: 20, borderRadius: '50%', background: '#000', border: '1px solid rgba(255,255,255,0.3)', color: '#fff', cursor: 'pointer', fontSize: 13, lineHeight: 1, padding: 0 }}
              >×</button>
            </div>
          </div>
        )}
        <StudyInputBar
          input={input}
          setInput={setInput}
          onSubmit={submit}
          onPhoto={() => photoInputRef.current?.click()}
          disabled={loading}
        />
        <input
          ref={photoInputRef}
          type="file"
          accept="image/*"
          capture="environment"
          style={{ display: 'none' }}
          onChange={onPhotoPicked}
        />
      </div>

      {/* Note composer sheet */}
      {noteOpen && (
        <div
          onClick={() => !noteSaving && setNoteOpen(false)}
          style={{ position: 'absolute', inset: 0, zIndex: 10, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'flex-end', justifyContent: 'center' }}
        >
          <div
            onClick={e => e.stopPropagation()}
            style={{
              width: '100%', maxWidth: 480, background: '#232323',
              borderTopLeftRadius: 22, borderTopRightRadius: 22,
              padding: '20px 18px calc(20px + env(safe-area-inset-bottom))',
              animation: 'fadeUp 220ms ease both',
            }}
          >
            <div style={{ fontFamily: 'var(--font-display-round), var(--sans)', fontSize: 18, fontWeight: 600, color: CREAM, marginBottom: 14 }}>
              Capture a note
            </div>
            <textarea
              autoFocus
              value={noteText}
              onChange={e => setNoteText(e.target.value)}
              placeholder="What do you want to remember?"
              rows={3}
              style={{
                width: '100%', boxSizing: 'border-box', resize: 'none',
                background: '#1A1A1A', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 12,
                padding: '12px 14px', color: CREAM, fontFamily: 'var(--sans)', fontSize: 15, outline: 'none',
              }}
            />
            <input
              value={noteRemind}
              onChange={e => setNoteRemind(e.target.value)}
              placeholder='Remind me… (optional, e.g. "tomorrow at 7pm")'
              style={{
                width: '100%', boxSizing: 'border-box', marginTop: 10,
                background: '#1A1A1A', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 12,
                padding: '10px 14px', color: CREAM, fontFamily: 'var(--sans)', fontSize: 13, outline: 'none',
              }}
            />
            <div style={{ display: 'flex', gap: 10, marginTop: 16, justifyContent: 'flex-end' }}>
              <button
                onClick={() => setNoteOpen(false)}
                disabled={noteSaving}
                style={{ background: 'none', border: 0, color: 'rgba(243,234,217,0.55)', cursor: 'pointer', fontFamily: 'var(--sans)', fontSize: 14, padding: '10px 14px' }}
              >Cancel</button>
              <button
                onClick={saveNote}
                disabled={!noteText.trim() || noteSaving}
                style={{
                  background: noteText.trim() ? 'var(--accent, #ff9072)' : 'rgba(255,255,255,0.1)',
                  color: noteText.trim() ? '#1a0e08' : 'rgba(243,234,217,0.4)',
                  border: 0, borderRadius: 999, cursor: noteText.trim() ? 'pointer' : 'default',
                  fontFamily: 'var(--sans)', fontSize: 14, fontWeight: 600, padding: '10px 22px',
                }}
              >{noteSaving ? 'Saving…' : 'Save'}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Single message ───────────────────────────────────────────────────────────
function StudyMessage({ msg }) {
  if (msg.role === 'user') {
    return (
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 14 }}>
        <div style={{ maxWidth: '80%', display: 'flex', flexDirection: 'column', alignItems: 'flex-end' }}>
          {msg.imagePreview && (
            <img src={msg.imagePreview} alt="" style={{ maxHeight: 200, maxWidth: 260, borderRadius: 12, marginBottom: 6, objectFit: 'cover', border: '1px solid rgba(255,255,255,0.12)' }} />
          )}
          {msg.content && (
            <div style={{
              padding: '10px 16px', borderRadius: '18px 18px 4px 18px',
              background: 'rgba(255,255,255,0.08)', color: CREAM,
              fontFamily: 'var(--sans)', fontSize: 15, lineHeight: 1.5,
            }}>
              {msg.content}
            </div>
          )}
        </div>
      </div>
    )
  }
  return (
    <div className="study-prose" style={{ marginBottom: 20, color: CREAM, fontFamily: 'var(--sans)', fontSize: 15.5, lineHeight: 1.6 }}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content || ''}</ReactMarkdown>
      {msg.streaming && (
        <span style={{ display: 'inline-block', width: 7, height: 16, marginLeft: 3, background: 'var(--accent, #ff9072)', verticalAlign: -2, animation: 'jarvisBlink 1s steps(1) infinite', borderRadius: 1 }} />
      )}
    </div>
  )
}

// ─── Light input bar (intentionally light, unlike normal chat's dark bar) ──────
function StudyInputBar({ input, setInput, onSubmit, onPhoto, disabled }) {
  const iconColor = '#5A5A5A'
  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); onSubmit() }
  }
  return (
    <div style={{
      width: '100%', maxWidth: 393, margin: '0 auto',
      display: 'flex', alignItems: 'center', gap: 14,
      padding: '12px 14px', background: '#ECECEC', borderRadius: 20,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexShrink: 0, color: iconColor }}>
        <button aria-label="add image" onClick={onPhoto} style={iconBtn}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
            <rect x="3" y="3" width="18" height="18" rx="3" />
            <circle cx="8.5" cy="8.5" r="1.6" />
            <path d="M21 15l-5-5L5 21" />
          </svg>
        </button>
        <button aria-label="code" onClick={() => setInput(input + '\n```\n\n```')} style={iconBtn}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M8 6l-5 6 5 6M16 6l5 6-5 6" />
          </svg>
        </button>
        <button aria-label="voice" onClick={() => console.log('[StudyMode] voice — next batch')} style={iconBtn}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
            <rect x="9" y="3" width="6" height="12" rx="3" />
            <path d="M5 11a7 7 0 0 0 14 0" />
            <line x1="12" y1="18" x2="12" y2="22" />
          </svg>
        </button>
      </div>
      <input
        value={input}
        onChange={e => setInput(e.target.value)}
        onKeyDown={handleKey}
        placeholder="Ask Jarvis"
        style={{
          flex: 1, minWidth: 0, background: 'transparent', border: 0, outline: 'none',
          color: '#1A1A1A', fontFamily: 'var(--sans)', fontSize: 16, fontWeight: 400,
        }}
      />
      <button
        aria-label="send"
        onClick={onSubmit}
        disabled={disabled}
        style={{
          width: 36, height: 36, borderRadius: '50%', flexShrink: 0,
          background: '#1A1A1A', border: 0, cursor: disabled ? 'default' : 'pointer',
          opacity: disabled ? 0.6 : 1,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 19V5M6 11l6-6 6 6" />
        </svg>
      </button>
    </div>
  )
}

const iconBtn = {
  background: 'none', border: 0, padding: 0, cursor: 'pointer',
  display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'inherit',
}
