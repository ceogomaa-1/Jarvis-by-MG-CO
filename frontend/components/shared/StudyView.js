'use client'

import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import StudyDrawer from './StudyDrawer'
import { JarvisVoice } from '../../lib/jarvisVoice'
import {
  createStudyNote, createStudyChat, updateStudyChat, getStudyChat, captureStudyNote, updateStudyNote,
} from '../../lib/studyApi'
import { uploadChatAttachment, getAttachmentSignedUrl } from '../../lib/attachments'

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

function dataUrlToFile(dataUrl, name, type) {
  const arr = dataUrl.split(',')
  const bstr = atob(arr[1])
  let n = bstr.length
  const u8 = new Uint8Array(n)
  while (n--) u8[n] = bstr.charCodeAt(n)
  return new File([u8], name, { type: type || 'image/jpeg' })
}

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

  // Capture (one or more photos → one combined note)
  const [captureChoiceOpen, setCaptureChoiceOpen] = useState(false)
  const [capturing, setCapturing] = useState(false)
  const [flash, setFlash] = useState(null) // { subject, title, pages }
  const [trayOpen, setTrayOpen] = useState(false)
  const [capturePages, setCapturePages] = useState([]) // {id, dataUrl, type}
  const camInputRef = useRef(null)
  const libInputRef = useRef(null)

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

    // Upload attachments to storage so they survive a reload (resolved before persist)
    const metaUploadPromise = Promise.all(atts.map(async (a) => {
      let storage_path = null
      const file = a.file || (a.dataUrl ? dataUrlToFile(a.dataUrl, a.name || 'file', a.type) : null)
      if (file) { try { storage_path = await uploadChatAttachment(file, userId) } catch (e) { console.error('[StudyMode] attachment upload failed', e) } }
      return { name: a.name, type: a.type, size: a.size, storage_path }
    }))

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

    // Persist the full turn — with uploaded attachment paths so images survive reload
    const resolvedMeta = await metaUploadPromise.catch(() => attachmentsMeta)
    const persistedUserRow = { ...userRow, attachmentsMeta: resolvedMeta }
    const finalConvo = [...snapshot, persistedUserRow, { role: 'assistant', content: accumulated }]
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
      const restored = await Promise.all((chat.messages || []).map(async (m, i) => {
        const metas = m.attachmentsMeta || []
        const previews = []
        for (const a of metas) {
          if (isImageType(a.type) && a.storage_path) {
            const url = await getAttachmentSignedUrl(a.storage_path).catch(() => null)
            if (url) previews.push(url)
          }
        }
        return { id: 1000 + i, role: m.role, content: m.content, attachmentsMeta: metas, previews }
      }))
      msgIdRef.current = 1000 + restored.length + 1
      setMessages(restored); messagesRef.current = restored
      setCurrentChatId(chatId); chatIdRef.current = chatId
    } catch (e) { console.error('[StudyMode] load chat failed', e) }
  }

  // ── Capture: 1+ photos → extract text + subject → one auto-filed note ────────
  const openTray = () => { setCaptureChoiceOpen(false); setTrayOpen(true) }

  const onPagesPicked = async (e) => {
    const files = Array.from(e.target.files || [])
    e.target.value = ''
    for (const f of files) {
      if (!f.type?.startsWith('image/')) continue
      if (f.size > 25 * 1024 * 1024) { console.warn('[StudyMode] page over 25MB skipped'); continue }
      try {
        const dataUrl = await fileToDataUrl(f)
        setCapturePages(prev => [...prev, { id: `${Date.now()}-${f.name}-${prev.length}`, dataUrl, type: f.type }])
      } catch (err) { console.error('[StudyMode] page read failed', err) }
    }
  }

  const saveCapture = async () => {
    if (capturePages.length === 0) return
    const pages = capturePages
    setTrayOpen(false)
    setCapturing(true)
    try {
      const images = pages.map(p => ({
        base64: p.dataUrl.includes(',') ? p.dataUrl.split(',')[1] : p.dataUrl,
        type: p.type,
      }))
      const res = await captureStudyNote(userId, images)
      // Keep the original page photos in the note (so they're viewable like Apple Notes)
      try {
        const noteImages = []
        for (let i = 0; i < pages.length; i++) {
          const p = pages[i]
          const file = dataUrlToFile(p.dataUrl, `page-${i + 1}.jpg`, p.type)
          const path = await uploadChatAttachment(file, userId)
          if (path) noteImages.push({ path, name: `page-${i + 1}` })
        }
        if (noteImages.length && res?.note?.id) {
          await updateStudyNote(userId, res.note.id, { images: noteImages })
        }
      } catch (e) { console.error('[StudyMode] attach capture images failed', e) }
      setCapturePages([])
      setDrawerRefreshKey(k => k + 1)
      setFlash({ subject: res.subject || 'General', title: res.title || '', pages: images.length })
      setTimeout(() => setFlash(null), 7000)
    } catch (err) {
      console.error('[StudyMode] capture failed', err)
      setFlash({ error: true })
      setTimeout(() => setFlash(null), 6000)
    } finally {
      setCapturing(false)
    }
  }

  // ── Quick actions ──────────────────────────────────────────────────────────
  const actions = {
    note: () => setCaptureChoiceOpen(true),
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
        setAttachments(prev => [...prev, { id: `${Date.now()}-${file.name}`, name: file.name, type: file.type, size: file.size, dataUrl, file }])
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

      {flash && (
        <div
          onClick={() => { if (!flash.error) { setDrawerOpen(true) } setFlash(null) }}
          style={{
            margin: '0 16px 8px', padding: '12px 14px', borderRadius: 14, cursor: flash.error ? 'default' : 'pointer',
            background: flash.error ? 'rgba(90,0,0,0.25)' : 'rgba(255,144,114,0.12)',
            border: `1px solid ${flash.error ? 'rgba(239,68,68,0.4)' : 'rgba(255,144,114,0.35)'}`,
            color: CREAM, fontFamily: 'var(--sans)', fontSize: 13.5, lineHeight: 1.45,
            animation: 'fadeUp 240ms ease both',
          }}
        >
          {flash.error
            ? "Couldn't read those photos — try clearer shots."
            : <>Captured ✓ {flash.pages > 1 ? `${flash.pages} pages → ` : ''}filed under <strong>{flash.subject}</strong>{flash.title ? ` — ${flash.title}` : ''}. Tap to view & edit in your notes.</>}
        </div>
      )}

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
          onCapture={() => setTrayOpen(true)}
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

      {/* Hidden capture inputs — camera (single shot) + library (multi-select) */}
      <input ref={camInputRef} type="file" accept="image/*" capture="environment" style={{ display: 'none' }} onChange={onPagesPicked} />
      <input ref={libInputRef} type="file" accept="image/*" multiple style={{ display: 'none' }} onChange={onPagesPicked} />

      {/* Multi-page capture tray */}
      {trayOpen && (
        <div onClick={() => setTrayOpen(false)} style={{ position: 'absolute', inset: 0, zIndex: 22, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'flex-end', justifyContent: 'center' }}>
          <div onClick={e => e.stopPropagation()} style={{ width: '100%', maxWidth: 480, background: '#232323', borderTopLeftRadius: 22, borderTopRightRadius: 22, padding: '20px 18px calc(20px + env(safe-area-inset-bottom))', animation: 'fadeUp 220ms ease both' }}>
            <div style={{ fontFamily: 'var(--font-display-round), var(--sans)', fontSize: 18, fontWeight: 600, color: CREAM, marginBottom: 4 }}>
              Capture pages{capturePages.length > 0 ? ` · ${capturePages.length}` : ''}
            </div>
            <div style={{ fontFamily: 'var(--sans)', fontSize: 12.5, color: 'rgba(243,234,217,0.55)', marginBottom: 14, lineHeight: 1.45 }}>
              Add as many pages as you want — they’ll be merged into one note, filed under the right subject.
            </div>

            {capturePages.length > 0 && (
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 14 }}>
                {capturePages.map((p, i) => (
                  <div key={p.id} style={{ position: 'relative' }}>
                    <img src={p.dataUrl} alt={`page ${i + 1}`} style={{ width: 64, height: 84, objectFit: 'cover', borderRadius: 8, border: '1px solid rgba(255,255,255,0.15)', display: 'block' }} />
                    <span style={{ position: 'absolute', bottom: 3, left: 3, background: 'rgba(0,0,0,0.65)', color: '#fff', fontFamily: 'var(--sans)', fontSize: 9, borderRadius: 4, padding: '1px 5px' }}>{i + 1}</span>
                    <button onClick={() => setCapturePages(prev => prev.filter(x => x.id !== p.id))} aria-label="remove page"
                      style={{ position: 'absolute', top: -7, right: -7, width: 20, height: 20, borderRadius: '50%', background: '#000', border: '1px solid rgba(255,255,255,0.3)', color: '#fff', cursor: 'pointer', fontSize: 13, lineHeight: 1, padding: 0 }}>×</button>
                  </div>
                ))}
              </div>
            )}

            <div style={{ display: 'flex', gap: 10, marginBottom: 12 }}>
              <button onClick={() => camInputRef.current?.click()}
                style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, padding: '12px', borderRadius: 12, cursor: 'pointer', background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)', color: CREAM, fontFamily: 'var(--sans)', fontSize: 13.5, fontWeight: 500 }}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" /><circle cx="12" cy="13" r="4" /></svg>
                Take photo
              </button>
              <button onClick={() => libInputRef.current?.click()}
                style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, padding: '12px', borderRadius: 12, cursor: 'pointer', background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)', color: CREAM, fontFamily: 'var(--sans)', fontSize: 13.5, fontWeight: 500 }}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="18" height="18" rx="3" /><circle cx="8.5" cy="8.5" r="1.6" /><path d="M21 15l-5-5L5 21" /></svg>
                From library
              </button>
            </div>

            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
              <button onClick={() => { setTrayOpen(false); setCapturePages([]) }} style={{ background: 'none', border: 0, color: 'rgba(243,234,217,0.55)', cursor: 'pointer', fontFamily: 'var(--sans)', fontSize: 14, padding: '10px 14px' }}>Cancel</button>
              <button onClick={saveCapture} disabled={capturePages.length === 0}
                style={{ background: capturePages.length ? 'var(--accent, #ff9072)' : 'rgba(255,255,255,0.1)', color: capturePages.length ? '#1a0e08' : 'rgba(243,234,217,0.4)', border: 0, borderRadius: 999, cursor: capturePages.length ? 'pointer' : 'default', fontFamily: 'var(--sans)', fontSize: 14, fontWeight: 600, padding: '10px 22px' }}>
                Save note{capturePages.length ? ` (${capturePages.length})` : ''}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Capture choice sheet */}
      {captureChoiceOpen && (
        <div onClick={() => setCaptureChoiceOpen(false)} style={{ position: 'absolute', inset: 0, zIndex: 20, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'flex-end', justifyContent: 'center' }}>
          <div onClick={e => e.stopPropagation()} style={{ width: '100%', maxWidth: 480, background: '#232323', borderTopLeftRadius: 22, borderTopRightRadius: 22, padding: '20px 18px calc(20px + env(safe-area-inset-bottom))', animation: 'fadeUp 220ms ease both' }}>
            <div style={{ fontFamily: 'var(--font-display-round), var(--sans)', fontSize: 18, fontWeight: 600, color: CREAM, marginBottom: 6 }}>Capture a note</div>
            <div style={{ fontFamily: 'var(--sans)', fontSize: 13, color: 'rgba(243,234,217,0.55)', marginBottom: 16, lineHeight: 1.45 }}>
              Snap your study material — Jarvis reads it, pulls out the text, and files it under the right subject. Forget about it; it’s saved.
            </div>
            <button
              onClick={openTray}
              style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 12, padding: '14px 16px', borderRadius: 14, marginBottom: 10, cursor: 'pointer', background: 'var(--accent, #ff9072)', border: 0, color: '#1a0e08', fontFamily: 'var(--sans)', fontSize: 15, fontWeight: 600 }}
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" /><circle cx="12" cy="13" r="4" /></svg>
              Snap pages (one or many)
            </button>
            <button
              onClick={() => { setCaptureChoiceOpen(false); setNoteOpen(true) }}
              style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 12, padding: '14px 16px', borderRadius: 14, cursor: 'pointer', background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)', color: CREAM, fontFamily: 'var(--sans)', fontSize: 15, fontWeight: 500 }}
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" /><path d="M18.5 2.5a2.12 2.12 0 0 1 3 3L12 15l-4 1 1-4z" /></svg>
              Write it myself
            </button>
          </div>
        </div>
      )}

      {/* Processing overlay */}
      {capturing && (
        <div style={{ position: 'absolute', inset: 0, zIndex: 25, background: 'rgba(0,0,0,0.72)', backdropFilter: 'blur(4px)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 16 }}>
          <span style={{ width: 12, height: 12, borderRadius: '50%', background: 'var(--accent, #ff9072)', animation: 'inkPulse 1s ease-in-out infinite' }} />
          <div style={{ fontFamily: 'var(--font-display-round), var(--sans)', fontSize: 17, fontWeight: 600, color: CREAM }}>Reading your photo…</div>
          <div style={{ fontFamily: 'var(--sans)', fontSize: 13, color: 'rgba(243,234,217,0.55)', textAlign: 'center', maxWidth: 260, lineHeight: 1.45 }}>
            Extracting the text and filing it under the right subject.
          </div>
        </div>
      )}

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
function StudyInputBar({ input, setInput, onSubmit, onAttach, onCapture, onVoice, voiceOn, voiceConnecting, disabled, textareaRef }) {
  const iconColor = '#5A5A5A'
  const [menuOpen, setMenuOpen] = useState(false)
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
        <div style={{ position: 'relative', display: 'flex' }}>
          <button aria-label="photo or file" onClick={() => setMenuOpen(o => !o)} style={iconBtn}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
              <rect x="3" y="3" width="18" height="18" rx="3" /><circle cx="8.5" cy="8.5" r="1.6" /><path d="M21 15l-5-5L5 21" />
            </svg>
          </button>
          {menuOpen && (
            <>
              <div onClick={() => setMenuOpen(false)} style={{ position: 'fixed', inset: 0, zIndex: 14 }} />
              <div style={{
                position: 'absolute', bottom: 'calc(100% + 10px)', left: 0, zIndex: 15,
                background: '#2A2A2A', border: '1px solid rgba(255,255,255,0.12)', borderRadius: 12,
                padding: 6, width: 188, boxShadow: '0 8px 24px rgba(0,0,0,0.5)', animation: 'fadeUp 160ms ease both',
              }}>
                <button onClick={() => { setMenuOpen(false); onCapture?.() }} style={menuItem}>
                  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" /><circle cx="12" cy="13" r="4" /></svg>
                  Capture to notes
                </button>
                <button onClick={() => { setMenuOpen(false); onAttach?.() }} style={menuItem}>
                  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"><path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48" /></svg>
                  Attach to chat
                </button>
              </div>
            </>
          )}
        </div>
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

const menuItem = {
  width: '100%', display: 'flex', alignItems: 'center', gap: 10,
  padding: '9px 10px', borderRadius: 8, cursor: 'pointer',
  background: 'none', border: 0, color: '#F3EAD9',
  fontFamily: 'var(--sans)', fontSize: 13.5, textAlign: 'left',
}
