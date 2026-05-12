'use client'

import { useState, useEffect, useRef } from 'react'

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

function ThinkingIndicator() {
  return (
    <div className="flex items-start gap-3 message-enter">
      <div
        className="flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold"
        style={{ backgroundColor: '#1c1a16', color: '#f59e0b', fontSize: '11px' }}
      >
        J
      </div>
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
          className="max-w-[75%] px-4 py-3 rounded-2xl rounded-tr-sm text-sm leading-relaxed"
          style={{ backgroundColor: '#1c1a16', color: '#ffffff' }}
        >
          {msg.content}
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col message-enter">
      {msg.proactive && (
        <span
          style={{ fontSize: '10px', color: '#78350f', paddingLeft: '40px', marginBottom: '2px', letterSpacing: '0.05em' }}
        >
          Jarvis
        </span>
      )}
      <div className="flex items-start gap-3">
        <div
          className="flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold mt-0.5"
          style={{ backgroundColor: '#1c1a16', color: '#f59e0b', fontSize: '11px' }}
        >
          J
        </div>
        <div
          className="max-w-[82%] text-sm leading-relaxed pt-0.5"
          style={{ color: '#f5f0e8', fontSize: '15px', lineHeight: '1.7' }}
        >
          {msg.content}
          {msg.streaming && <span className="cursor" />}
        </div>
      </div>
    </div>
  )
}

export default function Home() {
  const [messages, setMessages] = useState([OPENING_MESSAGE])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [userId, setUserId] = useState(null)
  const [onboardingComplete, setOnboardingComplete] = useState(null)
  const bottomRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    setUserId(getUserId())
  }, [])

  useEffect(() => {
    if (!userId) return
    fetch(`https://web-production-ba9c1.up.railway.app/api/user/onboarding-status/${userId}`)
      .then((r) => r.json())
      .then((data) => setOnboardingComplete(data.onboarding_complete))
      .catch(() => setOnboardingComplete(true))
  }, [userId])

  // Poll for proactive messages / reminders every 5 minutes
  useEffect(() => {
    if (!userId || !onboardingComplete) return

    const poll = async () => {
      try {
        const res = await fetch(`https://web-production-ba9c1.up.railway.app/api/proactive/check/${userId}`)
        if (!res.ok) return
        const data = await res.json()
        if (data.has_message && data.message) {
          setMessages((prev) => [
            ...prev,
            { role: 'assistant', content: data.message, proactive: true },
          ])
          if (!document.hasFocus()) {
            document.title = 'Jarvis has something for you'
          }
        }
      } catch {
        // silent
      }
    }

    const interval = setInterval(poll, 300000)
    return () => clearInterval(interval)
  }, [userId, onboardingComplete])

  useEffect(() => {
    const onFocus = () => { document.title = 'JARVIS' }
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

    // Capture history BEFORE state update
    const historyForApi = messages.slice(1)

    // Show user message immediately
    setMessages((prev) => [...prev, { role: 'user', content: text }])
    setLoading(true)

    let addedStreamingMessage = false

    try {
      const res = await fetch(`https://web-production-ba9c1.up.railway.app/api/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: userId,
          message: text,
          conversation_history: historyForApi,
        }),
      })

      if (!res.ok) throw new Error(`Server error: ${res.status}`)

      // Connection established — add empty streaming message, hide ThinkingIndicator
      addedStreamingMessage = true
      setMessages((prev) => [...prev, { role: 'assistant', content: '', streaming: true }])
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
          const rawData = line.slice(6)

          if (rawData === '[DONE]') {
            // Finalize the streaming message
            setMessages((prev) => {
              const updated = [...prev]
              updated[updated.length - 1] = { role: 'assistant', content: accumulated }
              return updated
            })
            done = true
            break
          }

          if (rawData === '[ERROR]') {
            setMessages((prev) => prev.slice(0, -1))
            setError('Jarvis hit an error mid-stream. Try again.')
            done = true
            break
          }

          try {
            const chunk = JSON.parse(rawData)
            accumulated += chunk
            setMessages((prev) => {
              const updated = [...prev]
              updated[updated.length - 1] = {
                ...updated[updated.length - 1],
                content: accumulated,
              }
              return updated
            })
          } catch {
            // Malformed SSE chunk — skip
          }
        }
      }

      // Re-check onboarding after response
      if (!onboardingComplete) {
        fetch(`https://web-production-ba9c1.up.railway.app/api/user/onboarding-status/${userId}`)
          .then((r) => r.json())
          .then((d) => setOnboardingComplete(d.onboarding_complete))
          .catch(() => {})
      }
    } catch (err) {
      if (addedStreamingMessage) {
        // Remove both user message and empty streaming message
        setMessages((prev) => prev.slice(0, -2))
      } else {
        // Only user message was added
        setMessages((prev) => prev.slice(0, -1))
      }
      setError('Could not reach Jarvis. Make sure the backend is running on port 8000.')
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
    <div
      className="flex flex-col h-screen"
      style={{ backgroundColor: '#0a0a0a', fontFamily: "'Inter', -apple-system, sans-serif" }}
    >
      {/* Header */}
      <div className="flex-shrink-0 flex flex-col items-center pt-8 pb-4">
        <h1
          className="text-3xl font-light tracking-widest uppercase"
          style={{ color: '#f59e0b', letterSpacing: '0.25em' }}
        >
          Jarvis
        </h1>
        <p className="mt-1.5 text-xs tracking-wider" style={{ color: '#4a4540' }}>
          Your personal AI. Learning you every day.
        </p>
        {onboardingComplete === false && (
          <p className="mt-1 text-xs tracking-wider" style={{ color: '#78350f', fontSize: '11px' }}>
            Getting to know you...
          </p>
        )}
      </div>

      {/* Divider */}
      <div className="flex-shrink-0 mx-auto w-full max-w-[760px] px-4">
        <div style={{ height: '1px', backgroundColor: '#1a1814' }} />
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-[760px] px-4 py-6 flex flex-col gap-6">
          {messages.map((msg, i) => (
            <Message key={i} msg={msg} />
          ))}
          {loading && <ThinkingIndicator />}
          {error && (
            <div
              className="text-xs text-center py-2 px-4 rounded-lg"
              style={{ color: '#ef4444', backgroundColor: '#1a0a0a' }}
            >
              {error}
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      {/* Input */}
      <div className="flex-shrink-0" style={{ borderTop: '1px solid #1a1814' }}>
        <div className="mx-auto w-full max-w-[760px] px-4 py-4">
          <div className="flex gap-3 items-end">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Say something..."
              rows={1}
              disabled={loading || !userId}
              className="flex-1 resize-none rounded-2xl px-4 py-3 text-sm outline-none transition-colors duration-200"
              style={{
                backgroundColor: '#111110',
                color: '#f5f0e8',
                border: '1px solid #2a2520',
                minHeight: '48px',
                maxHeight: '140px',
                lineHeight: '1.5',
                caretColor: '#f59e0b',
              }}
              onFocus={(e) => { e.target.style.borderColor = '#f59e0b' }}
              onBlur={(e) => { e.target.style.borderColor = '#2a2520' }}
              onInput={(e) => {
                e.target.style.height = 'auto'
                e.target.style.height = Math.min(e.target.scrollHeight, 140) + 'px'
              }}
            />
            <button
              onClick={sendMessage}
              disabled={loading || !input.trim() || !userId}
              className="flex-shrink-0 w-11 h-11 rounded-full flex items-center justify-center transition-all duration-200"
              style={{
                backgroundColor: loading || !input.trim() ? '#1c1a16' : '#f59e0b',
                color: loading || !input.trim() ? '#4a4540' : '#0a0a0a',
              }}
              aria-label="Send message"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="22" y1="2" x2="11" y2="13" />
                <polygon points="22 2 15 22 11 13 2 9 22 2" />
              </svg>
            </button>
          </div>
          <p className="mt-2 text-center text-xs" style={{ color: '#2a2520' }}>
            Press Enter to send
          </p>
          <div className="flex gap-4 justify-center mt-1">
            {['🔍 Search', '📅 Date', '📝 Notes'].map((tool) => (
              <span key={tool} style={{ fontSize: '10px', color: '#1e1c18', letterSpacing: '0.04em' }}>
                {tool}
              </span>
            ))}
          </div>
          {userId && (
            <p className="mt-1 text-center" style={{ color: '#1e1c18', fontSize: '10px', letterSpacing: '0.05em' }}>
              id: {userId.slice(0, 8)}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
