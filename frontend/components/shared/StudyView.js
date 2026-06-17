'use client'

import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import StudyDrawer from './StudyDrawer'
import { JarvisVoice } from '../../lib/jarvisVoice'
import {
  createStudyNote, createStudyChat, updateStudyChat, getStudyChat,
} from '../../lib/studyApi'

// ─────────────────────────────────────────────────────────────────────────────
// Study Mode — Jarvis Personal
//
//   • Multi-chat (new chat + saved history) — its own study_chats store.
//   • Captured notes saved to a SEPARATE study_notes store, categorized,
//     viewed via the hamburger drawer (StudyDrawer).
//   • Tutor brain via /api/chat/stream { study_mode:true }.
//   • Voice tutoring (JarvisVoice), image + file attachments, auto-grow input.
// ─────────────────────────────────────────────────────────────────────────────

const CREAM = '#F3EAD9'

// ─── Toggle pill ──────────────────────────────────────────────────────────────
export function StudyToggle({ studyMode, onToggle }) {
  const label = studyMode ? 'Normal Chat' : 'Study Mode'
  const on = studyMode
  return (
    <button
      onClick={onToggle}
      aria-label={studyMode ? 'Switch to Normal Chat' : 'Switch to Study Mode'}
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 9,
        padding: '6px 10px 6px 14px', background: '#2A2A2A',
        border: '1px solid rgba(255,255,255,0.12)', borderRadius: 999,
        cursor: 'pointer', userSelect: 'none', whiteSpace: 'nowrap',
      }}
    >
      <span style={{ fontFamily: 'var(--sans)', fontSize: 12.5, color: CREAM, letterSpacing: '0.01em', fontWeight: 400 }}>
        {label}
      </span>
      <span style={{
        position: 'relative', width: 34, height: 20, borderRadius: 999,
        background: on ? 'var(--accent, #ff9072)' : 'rgba(255,255,255,0.18)',
        transition: 'background 220ms ease', flexShrink: 0,
      }}>
        <span style={{
          position: 'absolute', top: 2, left: on ? 16 : 2, width: 16, height: 16, borderRadius: '50%',
          background: '#fff', transition: 'left 220ms cubic-bezier(0.4,0,0.2,1)', boxShadow: '0 1px 3px rgba(0,0,0,0.35)',
        }} />
      </span>
    </button>
  )
}

function ActionButton({ label, onClick }) {
  return (
    <button
      onClick={onClick}
      style={{
        width: 150, height: 58, background: 'rgba(255,255,255,0.06)',
        border: '1px solid rgba(255,255,255,0.05)', borderRadius: 18, color: CREAM,
        fontFamily: 'var(--sans)', fontSize: 15, fontWeight: 500, letterSpacing: '0.01em',
        cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
        transition: 'background 180ms ease',
      }}
      onMouseEnter={e => { e.currentTarget.style.background = 'rgba(255,255,255,0.10)' }}
      onMouseLeave={e => { e.currentTarget.style.background = 'rgba(255,255,255,0.06)' }}
    >
      {label}
    </button>
  )
}

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

const isImageType = (t) => (t || '').startsWith('image/')

// Strip heavy data URLs before persisting a chat row
function serializeMessages(msgs) {
  return msgs
    .filter(m => (typeof m.content === 'string' && m.content.trim()) || (m.attachmentsMeta?.length))
    .map(m => ({ role: m.role, content: m.content || '', attachmentsMeta: m.attachmentsMeta || [] }))
}

export default function StudyView({ name, onToggle, userId, backend }) {
  const displayName = name || 'there'
  const BACKEND = backend

  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [attachments, setAttachments] = useState([]) // {id,name,type,size,dataUrl}
  const [currentChatId, setCurrentChatId] = useState(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [drawerRefreshKey, setDrawerRefreshKey] = useState(0)

  // Voice
  const [voiceOn, setVoiceOn] = useState(false)
  const [voiceConnecting, setVoiceConnecting] = useState(false)
  const [jarvisSpeaking, setJarvisSpeaking] = useState(false)

  // Note composer
  const [noteOpen, setNoteOpen] = useState(false)
  const [noteText, setNoteText] = useState('')
  const [noteCategory, setNoteCategory] = useState('')
  const [noteRemind, setNoteRemind] = useState('')
  const [noteSaving, setNoteSaving] = useState(false)

  const msgIdRef = useRef(1)
  const messagesRef = useRef([])
  const chatIdRef = useRef(null)
  const scrollRef = useRef(null)
  const fileInputRef = useRef(null)
  const voiceRef = useRef(null)
  const textareaRef = useRef(null)
  const hasConversation = messages.length > 0

  useEffect(() => { messagesRef.current = messages }, [messages])
  useEffect(() => { chatIdRef.current = currentChatId }, [currentChatId])

  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }, [messages, loading])

  // Tear down voice when leaving Study Mode (component unmount)
  useEffect(() => () => { voiceRef.current?.destroy?.() }, [])

  // ── Persist chat ───────────────────────────────────────────────────────────
  async function persistChat(convo) {
    const payload = serializeMessages(convo)
    if (!payload.length) return
    try {
      if (chatIdRef.current) {
        await updateStudyChat(userId, chatIdRef.current, { messages: payload })
      } else {
        const firstUser = convo.find(m => m.role === 'user' && m.content?.trim())
        const title = (firstUser?.content || 'New chat').slice(0, 60)
        const chat = await createStudyChat(userId, { title, messages: payload })
        chatIdRef.current = chat.id
        setCurrentChatId(chat.id)
      }
      setDrawerRefreshKey(k => k + 1)
    } catch (e) {
      console.error('[StudyMode] persist chat failed', e)
    }
  }

  // ── Stream a message to the tutor brain ───────────────────────────────────
  async function send(text, opts = {}) {
    const apiText = (text ?? '').trim()
    const atts = opts.attachments ?? attachments
    if ((!apiText && atts.length === 0) || loading) return

    const attachmentsMeta = atts.map(a => ({ name: a.name, type: a.type, size: a.size }))
    const previews = atts.filter(a => isImageType(a.type)).map(a => a.dataUrl)

    msgIdRef.current += 1
    const userRowId = msgIdRef.current
    const userRow = { id: userRowId, role: 'user', content: apiText, attachmentsMeta, previews }
    const snapshot = messagesRef.current
    setMessages(prev => [...prev, userRow])
    setInput('')
    setAttachments([])
    if (textareaRef.current) { textareaRef.current.style.height = 'auto' }
    setLoading(true)

    const historyForApi = snapshot
      .filter(m => typeof m.content === 'string' && m.content.trim().length > 0)
      .map(({ role, content }) => ({ role, content }))

    const body = {
      user_id: userId,
      message: apiText || 'Please look at this and help me study it.',
      conversation_history: historyForApi,
      study_mode: true,
    }
    if (opts.voice) body.voice_mode = true
    if (atts.length > 0) {
      body.attachments = atts.map(a => ({
        base64: a.dataUrl.includes(',') ? a.dataUrl.split(',')[1] : a.dataUrl,
        type: a.type, name: a.name, size: a.size,
      }))
    }

    let streamId = null
    let accumulated = ''
    let voiceFired = false
    try {
      const res = await fetch(`${BACKEND}/api/chat/stream`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      })
      if (!res.ok) throw new Error(`${res.status}`)

      msgIdRef.current += 1
      streamId = msgIdRef.current
      setMessages(prev => [...prev, { id: streamId, role: 'assistant', content: '', streaming: true }])
      setLoading(false)

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
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
            if (opts.voice && !voiceFired && accumulated.trim()) voiceRef.current?.speak(accumulated)
            done = true
            break
          }
          if (raw === '[ERROR]') { setMessages(prev => prev.filter(m => m.id !== streamId)); done = true; break }
          if (raw.startsWith('[DEBUG:')) continue
          try {
            const chunk = JSON.parse(raw)
            if (chunk && typeof chunk === 'object') {
              if (chunk.__vs) { if (opts.voice && chunk.__vs.trim()) { voiceRef.current?.speak(chunk.__vs); voiceFired = true } continue }
              if (Array.isArray(chunk.__sources) || chunk.type === 'usage') continue
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
      setMessages(prev => [...prev, { id: msgIdRef.current, role: 'assistant', content: 'Hit a snag reaching the tutor. Try that again?' }])
      setLoading(false)
      return
    } finally {
      setLoading(false)
    }

    // Persist the full turn
    const finalConvo = [...snapshot, userRow, { role: 'assistant', content: accumulated }]
    persistChat(finalConvo)
  }

  // ── Chat session controls ──────────────────────────────────────────────────
  const newChat = () => {
    setMessages([]); messagesRef.current = []
    setCurrentChatId(null); chatIdRef.current = null
    setInput(''); setAttachments([])
  }
  const selectChat = async (chatId) => {
    try {
      const chat = await getStudyChat(userId, chatId)
      const restored = (chat.messages || []).map((m, i) => ({
        id: 1000 + i, role: m.role, content: m.content,
        attachmentsMeta: m.attachmentsMeta || [],
      }))
      msgIdRef.current = 1000 + restored.length + 1
      setMessages(restored); messagesRef.current = restored
      setCurrentChatId(chatId); chatIdRef.current = chatId
    } catch (e) { console.error('[StudyMode] load chat failed', e) }
  }

  // ── Quick actions ──────────────────────────────────────────────────────────
  const actions = {
    note: () => setNoteOpen(true),
    quiz: () => send('Quiz me. Ask one question at a time, wait for my answer, then give feedback before the next one.'),
    summarize: () => send('Summarize the key points of what we have been studying into tight, easy-to-revise notes.'),
    research: () => send('I want to research a topic. Ask me what I want to learn about, then give me a clear, sourced overview.'),
  }

  // ── Attachments (images AND files) ──────────────────────────────────────────
  const onFilesPicked = async (e) => {
    const files = Array.from(e.target.files || [])
    e.target.value = ''
    for (const file of files) {
      if (file.size > 25 * 1024 * 1024) { console.warn('[StudyMode] file over 25MB skipped', file.name); continue }
      try {
        const dataUrl = await fileToDataUrl(file)
        setAttachments(prev => [...prev, { id: `${Date.now()}-${file.name}`, name: file.name, type: file.type, size: file.size, dataUrl }])
      } catch (err) { console.error('[StudyMode] file read failed', err) }
    }
  }

  // ── Voice tutoring ──────────────────────────────────────────────────────────
  const toggleVoice = async () => {
    if (voiceOn) {
      voiceRef.current?.destroy?.()
      voiceRef.current = null
      setVoiceOn(false); setJarvisSpeaking(false)
      return
    }
    setVoiceConnecting(true)
    try {
      if (!voiceRef.current) {
        voiceRef.current = new JarvisVoice({
          userId,
          onSpeakingStart: () => setJarvisSpeaking(true),
          onSpeakingEnd: () => setJarvisSpeaking(false),
          onError: (m) => console.error('[StudyMode] voice', m),
        })
      }
      await voiceRef.current.resumeAudio()
      await voiceRef.current.startHandsFree((text) => send(text, { voice: true }))
      setVoiceOn(true)
    } catch (err) {
      console.error('[StudyMode] voice start failed', err)
      voiceRef.current = null
    } finally {
      setVoiceConnecting(false)
    }
  }

  // ── Save a categorized study note ───────────────────────────────────────────
  const saveNote = async () => {
    const content = noteText.trim()
    if (!content || noteSaving) return
    setNoteSaving(true)
    try {
      await createStudyNote(userId, content, noteCategory.trim() || 'General')
      // Optional reminder still uses the existing personal reminder system
      if (noteRemind.trim()) {
        await fetch(`${BACKEND}/api/notes/${userId}`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ note: `[Study] ${content}`, remind_at: noteRemind.trim() }),
        }).catch(() => {})
      }
      setNoteOpen(false); setNoteText(''); setNoteCategory(''); setNoteRemind('')
      setDrawerRefreshKey(k => k + 1)
    } catch (err) {
      console.error('[StudyMode] save note failed', err)
    } finally {
      setNoteSaving(false)
    }
  }

  const submit = () => send(input)

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 5, background: '#1A1A1A',
      display: 'flex', flexDirection: 'column', animation: 'fadeUp 300ms ease both',
    }}>
      {/* Header */}
      <div style={{ height: 56, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 18px' }}>
        <button
          onClick={() => setDrawerOpen(true)} aria-label="study menu"
          style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 6, display: 'flex', flexDirection: 'column', gap: 5, alignItems: 'center' }}
        >
          <span style={{ display: 'block', width: 22, height: 2, background: CREAM, borderRadius: 1 }} />
          <span style={{ display: 'block', width: 22, height: 2, background: CREAM, borderRadius: 1 }} />
          <span style={{ display: 'block', width: 22, height: 2, background: CREAM, borderRadius: 1 }} />
        </button>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {hasConversation && (
            <button
              onClick={newChat} aria-label="new chat" title="New chat"
              style={{ background: 'none', border: '1px solid rgba(255,255,255,0.12)', borderRadius: 999, width: 32, height: 32, color: CREAM, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M12 5v14M5 12h14" /></svg>
            </button>
          )}
          <StudyToggle studyMode={true} onToggle={onToggle} />
        </div>
      </div>

      {!hasConversation ? (
        <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', paddingTop: 32, overflowY: 'auto' }}>
          <img src="/jarvis-logo-mono.png" alt="" style={{ width: 77, height: 77, objectFit: 'contain', userSelect: 'none' }} draggable={false} />
          <div style={{ marginTop: 22, fontFamily: 'var(--font-display-round), var(--sans)', fontSize: 24, fontWeight: 600, color: CREAM, textAlign: 'center', letterSpacing: '0.01em' }}>
            {timeOfDay()}, {displayName}
          </div>
          <div style={{ marginTop: 56, display: 'grid', gridTemplateColumns: 'repeat(2, 150px)', gap: 16 }}>
            <ActionButton label="Capture a note" onClick={actions.note} />
            <ActionButton label="Quick Quiz" onClick={actions.quiz} />
            <ActionButton label="Summarize" onClick={actions.summarize} />
            <ActionButton label="Research" onClick={actions.research} />
          </div>
        </div>
      ) : (
        <div ref={scrollRef} style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '8px 18px 16px' }}>
          <div style={{ maxWidth: 640, margin: '0 auto' }}>
            {messages.map(m => <StudyMessage key={m.id} msg={m} />)}
            {loading && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'rgba(243,234,217,0.5)', fontFamily: 'var(--sans)', fontSize: 13, margin: '8px 0' }}>
                <span style={{ width: 7, height: 7, borderRadius: '50%', background: 'var(--accent, #ff9072)', animation: 'inkPulse 1s ease-in-out infinite' }} />
                thinking…
              </div>
            )}
          </div>
        </div>
      )}

      {/* Voice banner */}
      {(voiceOn || voiceConnecting) && (
        <div style={{ display: 'flex', justifyContent: 'center', paddingBottom: 8 }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontFamily: 'var(--sans)', fontSize: 11, letterSpacing: '0.18em', textTransform: 'uppercase', color: 'var(--accent, #ff9072)' }}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--accent, #ff9072)', animation: 'inkPulse 1.2s ease-in-out infinite' }} />
            {voiceConnecting ? 'Connecting…' : jarvisSpeaking ? 'Speaking' : 'Listening'}
          </span>
        </div>
      )}

      {/* Input */}
      <div style={{ flexShrink: 0, padding: '0 16px 20px' }}>
        {attachments.length > 0 && (
          <div style={{ maxWidth: 480, margin: '0 auto 8px', display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {attachments.map(a => (
              <div key={a.id} style={{ position: 'relative' }}>
                {isImageType(a.type) ? (
                  <img src={a.dataUrl} alt={a.name} style={{ height: 56, borderRadius: 10, objectFit: 'cover', display: 'block', border: '1px solid rgba(255,255,255,0.15)' }} />
                ) : (
                  <div style={{ height: 56, minWidth: 96, maxWidth: 150, padding: '0 12px', borderRadius: 10, background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.12)', display: 'flex', alignItems: 'center', color: CREAM, fontFamily: 'var(--sans)', fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    📄 {a.name}
                  </div>
                )}
                <button onClick={() => setAttachments(prev => prev.filter(x => x.id !== a.id))} aria-label="remove" style={{ position: 'absolute', top: -7, right: -7, width: 20, height: 20, borderRadius: '50%', background: '#000', border: '1px solid rgba(255,255,255,0.3)', color: '#fff', cursor: 'pointer', fontSize: 13, lineHeight: 1, padding: 0 }}>×</button>
              </div>
            ))}
          </div>
        )}
        <StudyInputBar
          input={input} setInput={setInput} onSubmit={submit}
          onAttach={() => fileInputRef.current?.click()}
          onVoice={toggleVoice} voiceOn={voiceOn} voiceConnecting={voiceConnecting}
          disabled={loading} textareaRef={textareaRef}
        />
        <input ref={fileInputRef} type="file" accept="image/*,application/pdf,.txt,.md,.csv,.doc,.docx,.xlsx" multiple style={{ display: 'none' }} onChange={onFilesPicked} />
      </div>

      {/* Study drawer (hamburger) */}
      <StudyDrawer
        open={drawerOpen} onClose={() => setDrawerOpen(false)} userId={userId}
        currentChatId={currentChatId} onSelectChat={selectChat} onNewChat={newChat}
        refreshKey={drawerRefreshKey}
      />

      {/* Note composer */}
      {noteOpen && (
        <div onClick={() => !noteSaving && setNoteOpen(false)} style={{ position: 'absolute', inset: 0, zIndex: 20, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'flex-end', justifyContent: 'center' }}>
          <div onClick={e => e.stopPropagation()} style={{ width: '100%', maxWidth: 480, background: '#232323', borderTopLeftRadius: 22, borderTopRightRadius: 22, padding: '20px 18px calc(20px + env(safe-area-inset-bottom))', animation: 'fadeUp 220ms ease both' }}>
            <div style={{ fontFamily: 'var(--font-display-round), var(--sans)', fontSize: 18, fontWeight: 600, color: CREAM, marginBottom: 14 }}>Capture a note</div>
            <textarea autoFocus value={noteText} onChange={e => setNoteText(e.target.value)} placeholder="What do you want to remember?" rows={3}
              style={{ width: '100%', boxSizing: 'border-box', resize: 'none', background: '#1A1A1A', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 12, padding: '12px 14px', color: CREAM, fontFamily: 'var(--sans)', fontSize: 15, outline: 'none' }} />
            <input value={noteCategory} onChange={e => setNoteCategory(e.target.value)} placeholder="Category / subject (e.g. Biology) — optional"
              style={{ width: '100%', boxSizing: 'border-box', marginTop: 10, background: '#1A1A1A', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 12, padding: '10px 14px', color: CREAM, fontFamily: 'var(--sans)', fontSize: 13, outline: 'none' }} />
            <input value={noteRemind} onChange={e => setNoteRemind(e.target.value)} placeholder='Remind me… (optional, e.g. "tomorrow at 7pm")'
              style={{ width: '100%', boxSizing: 'border-box', marginTop: 10, background: '#1A1A1A', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 12, padding: '10px 14px', color: CREAM, fontFamily: 'var(--sans)', fontSize: 13, outline: 'none' }} />
            <div style={{ display: 'flex', gap: 10, marginTop: 16, justifyContent: 'flex-end' }}>
              <button onClick={() => setNoteOpen(false)} disabled={noteSaving} style={{ background: 'none', border: 0, color: 'rgba(243,234,217,0.55)', cursor: 'pointer', fontFamily: 'var(--sans)', fontSize: 14, padding: '10px 14px' }}>Cancel</button>
              <button onClick={saveNote} disabled={!noteText.trim() || noteSaving}
                style={{ background: noteText.trim() ? 'var(--accent, #ff9072)' : 'rgba(255,255,255,0.1)', color: noteText.trim() ? '#1a0e08' : 'rgba(243,234,217,0.4)', border: 0, borderRadius: 999, cursor: noteText.trim() ? 'pointer' : 'default', fontFamily: 'var(--sans)', fontSize: 14, fontWeight: 600, padding: '10px 22px' }}>
                {noteSaving ? 'Saving…' : 'Save'}
              </button>
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
    const fileMeta = (msg.attachmentsMeta || []).filter(a => !isImageType(a.type))
    return (
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 14 }}>
        <div style={{ maxWidth: '80%', display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 6 }}>
          {(msg.previews || []).map((src, i) => (
            <img key={i} src={src} alt="" style={{ maxHeight: 200, maxWidth: 260, borderRadius: 12, objectFit: 'cover', border: '1px solid rgba(255,255,255,0.12)' }} />
          ))}
          {fileMeta.map((a, i) => (
            <div key={i} style={{ padding: '8px 12px', borderRadius: 12, background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.12)', color: CREAM, fontFamily: 'var(--sans)', fontSize: 13 }}>📄 {a.name}</div>
          ))}
          {msg.content && (
            <div style={{ padding: '10px 16px', borderRadius: '18px 18px 4px 18px', background: 'rgba(255,255,255,0.08)', color: CREAM, fontFamily: 'var(--sans)', fontSize: 15, lineHeight: 1.5, whiteSpace: 'pre-wrap' }}>
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

// ─── Light input bar — auto-growing textarea ───────────────────────────────────
function StudyInputBar({ input, setInput, onSubmit, onAttach, onVoice, voiceOn, voiceConnecting, disabled, textareaRef }) {
  const iconColor = '#5A5A5A'
  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); onSubmit() }
  }
  const handleChange = (e) => {
    setInput(e.target.value)
    const ta = e.target
    ta.style.height = 'auto'
    ta.style.height = Math.min(ta.scrollHeight, 160) + 'px'
    ta.style.overflowY = ta.scrollHeight > 160 ? 'auto' : 'hidden'
  }
  const micColor = voiceOn ? '#fff' : iconColor
  const micBg = voiceOn ? 'var(--accent, #ff9072)' : 'transparent'
  return (
    <div style={{
      width: '100%', maxWidth: 480, margin: '0 auto', display: 'flex', alignItems: 'flex-end', gap: 12,
      padding: '10px 12px', background: '#ECECEC', borderRadius: 20,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0, color: iconColor, paddingBottom: 5 }}>
        <button aria-label="attach image or file" onClick={onAttach} style={iconBtn}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
            <rect x="3" y="3" width="18" height="18" rx="3" /><circle cx="8.5" cy="8.5" r="1.6" /><path d="M21 15l-5-5L5 21" />
          </svg>
        </button>
        <button aria-label="code" onClick={() => setInput(input + '\n```\n\n```')} style={iconBtn}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M8 6l-5 6 5 6M16 6l5 6-5 6" /></svg>
        </button>
        <button aria-label={voiceOn ? 'stop voice' : 'start voice'} onClick={onVoice} disabled={voiceConnecting}
          style={{ ...iconBtn, width: 30, height: 30, borderRadius: '50%', background: micBg, color: micColor, transition: 'background 200ms ease' }}>
          {voiceConnecting ? (
            <span style={{ width: 7, height: 7, borderRadius: '50%', background: 'var(--accent, #ff9072)', animation: 'inkPulse 0.8s ease-in-out infinite', display: 'inline-block' }} />
          ) : (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
              <rect x="9" y="3" width="6" height="12" rx="3" /><path d="M5 11a7 7 0 0 0 14 0" /><line x1="12" y1="18" x2="12" y2="22" />
            </svg>
          )}
        </button>
      </div>
      <textarea
        ref={textareaRef} value={input} onChange={handleChange} onKeyDown={handleKey}
        placeholder="Ask Jarvis" rows={1}
        style={{
          flex: 1, minWidth: 0, background: 'transparent', border: 0, outline: 'none', resize: 'none',
          color: '#1A1A1A', fontFamily: 'var(--sans)', fontSize: 16, fontWeight: 400,
          lineHeight: '22px', maxHeight: 160, overflowY: 'hidden', padding: '5px 0',
        }}
      />
      <button aria-label="send" onClick={onSubmit} disabled={disabled}
        style={{ width: 36, height: 36, borderRadius: '50%', flexShrink: 0, background: '#1A1A1A', border: 0, cursor: disabled ? 'default' : 'pointer', opacity: disabled ? 0.6 : 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 19V5M6 11l6-6 6 6" /></svg>
      </button>
    </div>
  )
}

const iconBtn = {
  background: 'none', border: 0, padding: 0, cursor: 'pointer',
  display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'inherit',
}
