'use client'

import { useState, useEffect, useRef } from 'react'

const BACKEND = 'https://jarvis-backend-4oz6.onrender.com'

const OPENING_MESSAGE = {
  role: 'assistant',
  content:
    "I'm Jarvis. Before I'm actually useful to you, I need to know you — not through a form, through a conversation. What's the one thing taking up the most space in your head right now?",
}

function getUserId() {
  let id = localStorage.getItem('jarvis_user_id')
  if (!id) {
    id = 'user_' + crypto.randomUUID().replace(/-/g, '').slice(0, 8)
    localStorage.setItem('jarvis_user_id', id)
  }
  return id
}

// ─── Intro splash ─────────────────────────────────────────────────────────────

function IntroSplash({ onDone }) {
  useEffect(() => {
    const t = setTimeout(onDone, 900)
    return () => clearTimeout(t)
  }, [onDone])

  return (
    <div
      className="intro-screen fixed inset-0 flex flex-col items-center justify-center z-50"
      style={{ backgroundColor: '#080808' }}
    >
      <h1 style={{ color: '#f59e0b', fontSize: '3rem', fontWeight: 300, letterSpacing: '0.4em', margin: 0 }}>
        JARVIS
      </h1>
      <p style={{ color: '#f59e0b', opacity: 0.4, fontSize: '0.7rem', letterSpacing: '0.2em', marginTop: '0.5rem' }}>
        by MG&CO
      </p>
    </div>
  )
}

// ─── Knowledge panel ──────────────────────────────────────────────────────────

function KnowledgePanel({ userId, onClose }) {
  const [model, setModel] = useState(null)

  useEffect(() => {
    fetch(`${BACKEND}/api/user/model/${userId}`)
      .then(r => r.json())
      .then(setModel)
      .catch(() => setModel({}))
  }, [userId])

  const Section = ({ title, items }) => {
    if (!items || items.length === 0) return null
    return (
      <div style={{ marginBottom: '1.25rem' }}>
        <p style={{ color: '#f59e0b', fontSize: '0.6rem', letterSpacing: '0.15em', textTransform: 'uppercase', opacity: 0.6, marginBottom: '0.5rem' }}>{title}</p>
        {items.map((item, i) => (
          <p key={i} style={{ color: '#f0ebe0', fontSize: '0.8rem', lineHeight: 1.6, margin: '0.2rem 0', opacity: 0.85 }}>
            <span style={{ color: '#f59e0b', marginRight: '0.4rem' }}>●</span>{item}
          </p>
        ))}
      </div>
    )
  }

  const id = model?.identity || {}
  const focus = model?.current_focus || {}
  const relationship = model?.jarvis_relationship || {}
  const work = model?.work_context || {}

  const identityItems = [
    id.name && `Name: ${id.name}`,
    id.preferred_name && id.preferred_name !== id.name && `Goes by: ${id.preferred_name}`,
    id.role && `Role: ${id.role}`,
    id.company && `Company: ${id.company}`,
    id.location && `Based in: ${id.location}`,
  ].filter(Boolean)

  const trustLabel = relationship.trust_level
    ? `${relationship.trust_level} (${relationship.interaction_count || 0} interactions)`
    : null

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40"
        style={{ backgroundColor: 'rgba(0,0,0,0.4)' }}
        onClick={onClose}
      />
      {/* Panel */}
      <div
        className="panel-slide fixed top-0 right-0 h-full z-50 overflow-y-auto"
        style={{
          width: '320px',
          backgroundColor: '#0f0e0c',
          borderLeft: '1px solid #2a2620',
          padding: '1.5rem',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
          <p style={{ color: '#f59e0b', fontSize: '0.65rem', letterSpacing: '0.2em', textTransform: 'uppercase', margin: 0 }}>
            Jarvis Knows
          </p>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', color: '#4a4540', cursor: 'pointer', fontSize: '1.1rem', lineHeight: 1 }}
          >
            ×
          </button>
        </div>

        {!model ? (
          <p style={{ color: '#4a4540', fontSize: '0.8rem' }}>Loading...</p>
        ) : (
          <>
            <Section title="Identity" items={identityItems} />
            <Section title="Current Focus" items={focus.top_goals} />
            <Section title="Active Projects" items={focus.active_projects} />
            <Section title="Biggest Challenges" items={focus.biggest_challenges} />
            <Section title="Key People" items={work.key_people} />
            <Section title="Never Forget" items={relationship.things_jarvis_should_never_forget} />
            {trustLabel && (
              <div style={{ marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid #1a1814' }}>
                <p style={{ color: '#4a4540', fontSize: '0.7rem', letterSpacing: '0.1em' }}>TRUST LEVEL</p>
                <p style={{ color: '#f0ebe0', fontSize: '0.8rem', opacity: 0.7 }}>{trustLabel}</p>
              </div>
            )}
          </>
        )}
      </div>
    </>
  )
}

// ─── Message components ───────────────────────────────────────────────────────

function ThinkingIndicator() {
  return (
    <div className="flex items-start gap-3 message-enter">
      <div style={{ width: '4px', height: '28px', backgroundColor: '#f59e0b', borderRadius: '2px', flexShrink: 0, opacity: 0.5 }} />
      <div className="flex items-center gap-1 pt-1" style={{ height: '28px' }}>
        <span className="thinking-dot w-1.5 h-1.5 rounded-full" style={{ backgroundColor: '#f59e0b' }} />
        <span className="thinking-dot w-1.5 h-1.5 rounded-full" style={{ backgroundColor: '#f59e0b' }} />
        <span className="thinking-dot w-1.5 h-1.5 rounded-full" style={{ backgroundColor: '#f59e0b' }} />
      </div>
    </div>
  )
}

function Message({ msg }) {
  const isUser = msg.role === 'user'

  if (isUser) {
    return (
      <div className="flex justify-end message-enter">
        <div
          className="max-w-[72%] px-4 py-3 rounded-2xl rounded-tr-sm text-sm leading-relaxed"
          style={{
            backgroundColor: '#1a1814',
            border: '1px solid #2a2620',
            color: '#f0ebe0',
            fontSize: '0.9rem',
            lineHeight: 1.65,
          }}
        >
          {msg.content}
        </div>
      </div>
    )
  }

  const isProactive = msg.proactive

  return (
    <div className="flex flex-col message-enter">
      {isProactive && (
        <span style={{ fontSize: '0.65rem', color: '#f59e0b', opacity: 0.4, paddingLeft: '16px', marginBottom: '4px', letterSpacing: '0.1em' }}>
          Jarvis
        </span>
      )}
      <div className="flex items-start gap-3">
        <div style={{
          width: '4px',
          minHeight: '1.4rem',
          marginTop: '4px',
          flexShrink: 0,
          backgroundColor: isProactive ? '#d97706' : '#f59e0b',
          borderRadius: '2px',
          opacity: 0.7,
        }} />
        <div style={{ color: '#f0ebe0', fontSize: '0.95rem', lineHeight: 1.75, maxWidth: '82%' }}>
          {msg.content}
          {msg.streaming && <span className="cursor" />}
        </div>
      </div>
    </div>
  )
}

// ─── Main ─────────────────────────────────────────────────────────────────────

export default function Home() {
  const [showIntro, setShowIntro] = useState(true)
  const [messages, setMessages] = useState([OPENING_MESSAGE])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [userId, setUserId] = useState(null)
  const [onboardingComplete, setOnboardingComplete] = useState(null)
  const [showPanel, setShowPanel] = useState(false)
  const bottomRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => { setUserId(getUserId()) }, [])

  useEffect(() => {
    if (!userId) return
    fetch(`${BACKEND}/api/user/onboarding-status/${userId}`)
      .then(r => r.json())
      .then(d => setOnboardingComplete(d.onboarding_complete))
      .catch(() => setOnboardingComplete(true))
  }, [userId])

  // Proactive polling — 5 min
  useEffect(() => {
    if (!userId || !onboardingComplete) return
    const poll = async () => {
      try {
        const res = await fetch(`${BACKEND}/api/proactive/check/${userId}`)
        if (!res.ok) return
        const data = await res.json()
        if (data.has_message && data.message) {
          setMessages(prev => [...prev, { role: 'assistant', content: data.message, proactive: true }])
          if (!document.hasFocus()) document.title = 'Jarvis has something for you'
        }
      } catch {}
    }
    const interval = setInterval(poll, 300000)
    return () => clearInterval(interval)
  }, [userId, onboardingComplete])

  useEffect(() => {
    const onFocus = () => { document.title = 'Jarvis — Your Personal AI' }
    window.addEventListener('focus', onFocus)
    return () => window.removeEventListener('focus', onFocus)
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  async function sendMessage() {
    const text = input.trim()
    if (!text || loading) return
    setInput('')
    setError(null)

    const historyForApi = messages.slice(1)
    setMessages(prev => [...prev, { role: 'user', content: text }])
    setLoading(true)

    let addedStreamingMessage = false
    try {
      const res = await fetch(`${BACKEND}/api/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, message: text, conversation_history: historyForApi }),
      })
      if (!res.ok) throw new Error(`${res.status}`)

      addedStreamingMessage = true
      setMessages(prev => [...prev, { role: 'assistant', content: '', streaming: true }])
      setLoading(false)

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let accumulated = ''
      let done = false

      while (!done) {
        const { done: readerDone, value } = await reader.read()
        if (readerDone) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const raw = line.slice(6)
          if (raw === '[DONE]') {
            setMessages(prev => {
              const updated = [...prev]
              updated[updated.length - 1] = { role: 'assistant', content: accumulated }
              return updated
            })
            done = true
            break
          }
          if (raw === '[ERROR]') {
            setMessages(prev => prev.slice(0, -1))
            setError('Jarvis hit an error. Try again.')
            done = true
            break
          }
          try {
            const chunk = JSON.parse(raw)
            accumulated += chunk
            setMessages(prev => {
              const updated = [...prev]
              updated[updated.length - 1] = { ...updated[updated.length - 1], content: accumulated }
              return updated
            })
          } catch {}
        }
      }

      if (!onboardingComplete) {
        fetch(`${BACKEND}/api/user/onboarding-status/${userId}`)
          .then(r => r.json())
          .then(d => setOnboardingComplete(d.onboarding_complete))
          .catch(() => {})
      }
    } catch {
      if (addedStreamingMessage) setMessages(prev => prev.slice(0, -2))
      else setMessages(prev => prev.slice(0, -1))
      setError('Could not reach Jarvis. Check your connection.')
    } finally {
      setLoading(false)
      inputRef.current?.focus()
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  return (
    <>
      {showIntro && <IntroSplash onDone={() => setShowIntro(false)} />}
      {showPanel && userId && <KnowledgePanel userId={userId} onClose={() => setShowPanel(false)} />}

      <div
        className="flex flex-col h-screen"
        style={{ backgroundColor: '#080808', fontFamily: "'Inter', -apple-system, sans-serif" }}
      >
        {/* Header */}
        <div className="flex-shrink-0 flex flex-col items-center pt-8 pb-5" style={{ position: 'relative' }}>
          <h1 style={{ color: '#f59e0b', fontSize: '2.5rem', fontWeight: 300, letterSpacing: '0.3em', margin: 0, textTransform: 'uppercase' }}>
            Jarvis
          </h1>
          <p style={{ color: '#f0ebe0', fontSize: '0.75rem', letterSpacing: '0.15em', opacity: 0.5, marginTop: '0.4rem' }}>
            Your personal AI. Learning you every day.
          </p>
          {onboardingComplete === false && (
            <p className="onboarding-pulse" style={{ color: '#f59e0b', fontSize: '0.7rem', letterSpacing: '0.1em', marginTop: '0.35rem' }}>
              Getting to know you...
            </p>
          )}

          {/* Knowledge panel trigger */}
          {userId && (
            <button
              onClick={() => setShowPanel(true)}
              title="What Jarvis knows"
              style={{
                position: 'absolute',
                right: '1.5rem',
                top: '50%',
                transform: 'translateY(-50%)',
                background: 'none',
                border: '1px solid #2a2620',
                borderRadius: '6px',
                color: '#f59e0b',
                fontSize: '0.8rem',
                padding: '0.35rem 0.55rem',
                cursor: 'pointer',
                opacity: 0.6,
                letterSpacing: '0.05em',
                transition: 'opacity 0.2s',
              }}
              onMouseEnter={e => e.target.style.opacity = 1}
              onMouseLeave={e => e.target.style.opacity = 0.6}
            >
              ◉
            </button>
          )}
        </div>

        {/* Divider */}
        <div style={{ height: '1px', backgroundColor: '#1a1814', flexShrink: 0 }} />

        {/* Messages */}
        <div className="flex-1 overflow-y-auto">
          <div style={{ maxWidth: '760px', margin: '0 auto', padding: '1.75rem 1.25rem', display: 'flex', flexDirection: 'column', gap: '1.75rem' }}>
            {messages.map((msg, i) => <Message key={i} msg={msg} />)}
            {loading && <ThinkingIndicator />}
            {error && (
              <div style={{ color: '#ef4444', fontSize: '0.75rem', textAlign: 'center', padding: '0.5rem 1rem', backgroundColor: '#1a0a0a', borderRadius: '8px' }}>
                {error}
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        </div>

        {/* Input */}
        <div style={{ borderTop: '1px solid #1a1814', flexShrink: 0 }}>
          <div style={{ maxWidth: '760px', margin: '0 auto', padding: '1.25rem 1.25rem 1rem' }}>
            <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'flex-end' }}>
              <textarea
                ref={inputRef}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Say something to Jarvis..."
                rows={1}
                disabled={loading || !userId}
                style={{
                  flex: 1,
                  resize: 'none',
                  borderRadius: '16px',
                  padding: '0.875rem 1.25rem',
                  fontSize: '0.9rem',
                  outline: 'none',
                  backgroundColor: '#0f0e0c',
                  color: '#f0ebe0',
                  border: '1px solid #2a2620',
                  minHeight: '52px',
                  maxHeight: '140px',
                  lineHeight: '1.5',
                  caretColor: '#f59e0b',
                  fontFamily: "'Inter', -apple-system, sans-serif",
                  transition: 'border-color 0.2s',
                }}
                onFocus={e => { e.target.style.borderColor = '#f59e0b40' }}
                onBlur={e => { e.target.style.borderColor = '#2a2620' }}
                onInput={e => {
                  e.target.style.height = 'auto'
                  e.target.style.height = Math.min(e.target.scrollHeight, 140) + 'px'
                }}
              />
              <button
                onClick={sendMessage}
                disabled={loading || !input.trim() || !userId}
                style={{
                  flexShrink: 0,
                  width: '44px',
                  height: '44px',
                  borderRadius: '50%',
                  border: 'none',
                  backgroundColor: loading || !input.trim() ? '#1a1814' : '#f59e0b',
                  color: loading || !input.trim() ? '#4a4540' : '#080808',
                  cursor: loading || !input.trim() ? 'default' : 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  transition: 'background-color 0.2s',
                }}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="22" y1="2" x2="11" y2="13" />
                  <polygon points="22 2 15 22 11 13 2 9 22 2" />
                </svg>
              </button>
            </div>
            <p style={{ marginTop: '0.5rem', textAlign: 'center', fontSize: '0.65rem', color: '#2a2520', letterSpacing: '0.05em' }}>
              Press Enter to send
            </p>
            {userId && (
              <p style={{ marginTop: '0.2rem', textAlign: 'center', fontSize: '0.6rem', color: '#1a1814', letterSpacing: '0.05em' }}>
                id: {userId.slice(0, 8)}
              </p>
            )}
          </div>
        </div>
      </div>
    </>
  )
}
