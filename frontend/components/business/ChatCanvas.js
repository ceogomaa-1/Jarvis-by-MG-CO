'use client'
import { useState, useRef, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { detectShowMeHow } from '../../lib/business/showMeHowDetector'
import Walkthrough from './Walkthrough'
import DownloadPDFButton from './DownloadPDFButton'
import { detectCreation } from '../../lib/business/creationDetector'
import CreationCanvas from './CreationCanvas'
import ProactiveBanner from './ProactiveBanner'
import MetricsModal from './MetricsModal'
import ConnectionsModal from './ConnectionsModal'
import BrandModal from './BrandModal'
import PendingActionsStack from './PendingActionsStack'

const BACKEND = 'https://jarvis-backend-4oz6.onrender.com'

function UserBubble({ content }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 16 }}>
      <div style={{
        maxWidth: '72%', padding: '11px 16px',
        borderRadius: '16px 16px 4px 16px',
        background: 'rgba(200,75,49,0.1)',
        border: '1px solid rgba(200,75,49,0.2)',
        color: '#f3ead9', fontSize: 14,
        fontFamily: 'system-ui, sans-serif', lineHeight: 1.5,
      }}>
        {content}
      </div>
    </div>
  )
}

function AssistantBubble({ content, streaming }) {
  return (
    <div style={{ marginBottom: 18, maxWidth: '84%' }}>
      <div style={{
        fontSize: 14, color: '#f3ead9', lineHeight: 1.7,
        fontFamily: 'system-ui, sans-serif',
      }}
        className="biz-markdown"
      >
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{content || ''}</ReactMarkdown>
        {streaming && (
          <span style={{
            display: 'inline-block', width: 2, height: 14,
            background: '#c84b31', marginLeft: 2, verticalAlign: -2,
            animation: 'bizBlink 1s steps(1) infinite',
          }} />
        )}
      </div>
    </div>
  )
}

function WalkthroughMessage({ msg }) {
  return (
    <div style={{ marginBottom: 24, maxWidth: '94%' }}>
      <Walkthrough
        title={msg.title}
        intro={msg.intro}
        steps={msg.steps || []}
        loading={msg.loading}
        sources={msg.sources || []}
      />
      {msg.complete && msg.walkthroughData && (
        <DownloadPDFButton walkthrough={msg.walkthroughData} />
      )}
    </div>
  )
}

function ThinkingDots() {
  return (
    <div style={{ display: 'flex', gap: 5, marginBottom: 16 }}>
      {[0, 1, 2].map(i => (
        <div key={i} style={{
          width: 7, height: 7, borderRadius: '50%', background: '#c84b31',
          animation: `bizDot 1.2s ease-in-out ${i * 0.2}s infinite`,
        }} />
      ))}
    </div>
  )
}

export default function ChatCanvas({ userId }) {
  const [messages, setMessages] = useState([{
    id: 0,
    role: 'assistant',
    content: "I'm Jarvis for Business. Ask me anything — or say \"show me how to...\" and I'll walk you through it step by step.",
  }])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [briefing, setBriefing] = useState(null)
  const [metricsOpen, setMetricsOpen] = useState(false)
  const [connectionsOpen, setConnectionsOpen] = useState(false)
  const [brandOpen, setBrandOpen] = useState(false)
  const [actionsOpen, setActionsOpen] = useState(false)
  const msgIdRef = useRef(1)
  const scrollRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
    }
  }, [messages])

  // Load latest unread briefing on mount
  useEffect(() => {
    if (!userId) return
    let cancelled = false
    fetch(`${BACKEND}/api/business/proactive/latest?user_id=${encodeURIComponent(userId)}`)
      .then(r => r.json())
      .then(d => { if (!cancelled) setBriefing(d.briefing || null) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [userId])

  const dismissBriefing = async (briefingId) => {
    setBriefing(null)
    if (!briefingId || !userId) return
    try {
      await fetch(`${BACKEND}/api/business/proactive/mark-read`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ briefing_id: briefingId, user_id: userId }),
      })
    } catch {}
  }

  const dispatchBriefingAction = (actionText, briefingId) => {
    if (!actionText) return
    dismissBriefing(briefingId)
    sendMessage(actionText)
  }

  async function sendMessage(overrideText = null) {
    const text = (overrideText !== null ? overrideText : input).trim()
    if (!text || loading) return
    if (overrideText === null) setInput('')
    inputRef.current?.focus()

    msgIdRef.current += 1
    const userMsgId = msgIdRef.current
    setMessages(prev => [...prev, { id: userMsgId, role: 'user', content: text }])
    setLoading(true)

    if (detectShowMeHow(text)) {
      // Walkthrough mode
      msgIdRef.current += 1
      const wId = msgIdRef.current
      setMessages(prev => [...prev, {
        id: wId, role: 'walkthrough',
        title: '', intro: '', steps: [], loading: true, complete: false,
        walkthroughData: null, sources: [],
      }])

      try {
        const res = await fetch(`${BACKEND}/api/business/show-me-how`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query: text, user_id: userId || '' }),
        })
        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buf = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buf += decoder.decode(value, { stream: true })
          const lines = buf.split('\n')
          buf = lines.pop() ?? ''

          for (const line of lines) {
            if (!line.startsWith('data: ')) continue
            const raw = line.slice(6)
            if (raw === '[DONE]') break
            try {
              const ev = JSON.parse(raw)
              setMessages(prev => prev.map(m => {
                if (m.id !== wId) return m
                if (ev.type === 'title') return { ...m, title: ev.value }
                if (ev.type === 'intro') return { ...m, intro: ev.value }
                if (ev.type === 'step') return { ...m, steps: [...m.steps, ev] }
                if (ev.type === 'complete') return {
                  ...m, loading: false, complete: true,
                  walkthroughData: ev.walkthrough,
                  sources: ev.sources || [],
                }
                if (ev.type === 'error') return { ...m, loading: false, intro: ev.value }
                return m
              }))
            } catch {}
          }
        }
        setMessages(prev => prev.map(m => m.id === wId ? { ...m, loading: false } : m))
      } catch (err) {
        console.error('Walkthrough failed:', err)
        setMessages(prev => prev.map(m =>
          m.id === wId ? { ...m, loading: false, intro: 'Could not generate walkthrough. Please try again.' } : m
        ))
      }
      setLoading(false)
      return
    }

    if (detectCreation(text)) {
      // Creation 1.0 — sub-agent orchestration
      msgIdRef.current += 1
      const cId = msgIdRef.current
      setMessages(prev => [...prev, {
        id: cId, role: 'creation',
        title: '', intro: '', agents: [], statuses: {},
        artifact: '', error: '', complete: false,
      }])

      try {
        const res = await fetch(`${BACKEND}/api/business/create`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: text, user_id: userId || '' }),
        })
        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buf = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buf += decoder.decode(value, { stream: true })
          const lines = buf.split('\n')
          buf = lines.pop() ?? ''

          for (const line of lines) {
            if (!line.startsWith('data: ')) continue
            const raw = line.slice(6)
            if (raw === '[DONE]') break
            try {
              const ev = JSON.parse(raw)
              setMessages(prev => prev.map(m => {
                if (m.id !== cId) return m
                if (ev.type === 'plan') {
                  const initialStatuses = {}
                  for (const a of ev.agents) initialStatuses[a.id] = 'pending'
                  return { ...m, title: ev.title, intro: ev.intro, agents: ev.agents, statuses: initialStatuses }
                }
                if (ev.type === 'agent_status') {
                  return { ...m, statuses: { ...m.statuses, [ev.id]: ev.status } }
                }
                if (ev.type === 'creation_id') {
                  return { ...m, creationId: ev.id }
                }
                if (ev.type === 'artifact') {
                  return { ...m, artifact: ev.content }
                }
                if (ev.type === 'complete') {
                  return { ...m, complete: true }
                }
                if (ev.type === 'error') {
                  return { ...m, error: ev.value, complete: true }
                }
                return m
              }))
            } catch {}
          }
        }
      } catch (err) {
        console.error('Creation failed:', err)
        setMessages(prev => prev.map(m =>
          m.id === cId ? { ...m, error: 'Creation failed. Please try again.', complete: true } : m
        ))
      }
      setLoading(false)
      return
    }

    // Regular chat mode
    const history = messages
      .filter(m => m.role !== 'walkthrough' && m.role !== 'creation' && typeof m.content === 'string')
      .map(m => ({ role: m.role === 'user' ? 'user' : 'assistant', content: m.content }))

    msgIdRef.current += 1
    const aId = msgIdRef.current
    setMessages(prev => [...prev, { id: aId, role: 'assistant', content: '', streaming: true }])

    try {
      const res = await fetch(`${BACKEND}/api/business/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, user_id: userId || '', conversation_history: history }),
      })
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buf = ''
      let acc = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const lines = buf.split('\n')
        buf = lines.pop() ?? ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const raw = line.slice(6)
          if (raw === '[DONE]') break
          try {
            acc += JSON.parse(raw)
            setMessages(prev => prev.map(m => m.id === aId ? { ...m, content: acc } : m))
          } catch {}
        }
      }
      setMessages(prev => prev.map(m => m.id === aId ? { ...m, streaming: false } : m))
    } catch (err) {
      console.error('Chat failed:', err)
      setMessages(prev => prev.map(m =>
        m.id === aId ? { ...m, content: 'Something went wrong. Please try again.', streaming: false } : m
      ))
    }
    setLoading(false)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <style>{`
        @keyframes bizBlink { 50% { opacity: 0; } }
        @keyframes bizDot {
          0%, 80%, 100% { opacity: 0.2; transform: scale(0.8); }
          40%            { opacity: 1;   transform: scale(1); }
        }
      `}</style>

      <MetricsModal
        open={metricsOpen}
        onClose={() => setMetricsOpen(false)}
        userId={userId}
      />

      <ConnectionsModal
        open={connectionsOpen}
        onClose={() => setConnectionsOpen(false)}
        userId={userId}
      />

      <BrandModal
        open={brandOpen}
        onClose={() => setBrandOpen(false)}
        userId={userId}
      />

      <PendingActionsStack
        open={actionsOpen}
        onClose={() => setActionsOpen(false)}
        userId={userId}
      />

      {/* Top toolbar */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, padding: '14px 40px 0' }}>
        <button
          onClick={() => setActionsOpen(true)}
          onMouseEnter={e => (e.currentTarget.style.background = 'rgba(243,234,217,0.08)')}
          onMouseLeave={e => (e.currentTarget.style.background = 'rgba(243,234,217,0.04)')}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 7,
            background: 'rgba(243,234,217,0.04)',
            border: '1px solid rgba(243,234,217,0.12)',
            borderRadius: 8, padding: '7px 14px',
            color: 'rgba(243,234,217,0.85)', fontSize: 12, fontWeight: 500,
            fontFamily: 'system-ui, sans-serif', cursor: 'pointer',
            transition: 'background 180ms ease',
          }}
        >
          <span>📋</span>
          <span>Morning Queue</span>
        </button>
        <button
          onClick={() => setBrandOpen(true)}
          onMouseEnter={e => (e.currentTarget.style.background = 'rgba(243,234,217,0.08)')}
          onMouseLeave={e => (e.currentTarget.style.background = 'rgba(243,234,217,0.04)')}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 7,
            background: 'rgba(243,234,217,0.04)',
            border: '1px solid rgba(243,234,217,0.12)',
            borderRadius: 8, padding: '7px 14px',
            color: 'rgba(243,234,217,0.85)', fontSize: 12, fontWeight: 500,
            fontFamily: 'system-ui, sans-serif', cursor: 'pointer',
            transition: 'background 180ms ease',
          }}
        >
          <span>⚙️</span>
          <span>Brand</span>
        </button>
        <button
          onClick={() => setConnectionsOpen(true)}
          onMouseEnter={e => (e.currentTarget.style.background = 'rgba(243,234,217,0.08)')}
          onMouseLeave={e => (e.currentTarget.style.background = 'rgba(243,234,217,0.04)')}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 7,
            background: 'rgba(243,234,217,0.04)',
            border: '1px solid rgba(243,234,217,0.12)',
            borderRadius: 8, padding: '7px 14px',
            color: 'rgba(243,234,217,0.85)', fontSize: 12, fontWeight: 500,
            fontFamily: 'system-ui, sans-serif', cursor: 'pointer',
            transition: 'background 180ms ease',
          }}
        >
          <span>🔌</span>
          <span>Connections</span>
        </button>
        <button
          onClick={() => setMetricsOpen(true)}
          onMouseEnter={e => (e.currentTarget.style.background = 'rgba(243,234,217,0.08)')}
          onMouseLeave={e => (e.currentTarget.style.background = 'rgba(243,234,217,0.04)')}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 7,
            background: 'rgba(243,234,217,0.04)',
            border: '1px solid rgba(243,234,217,0.12)',
            borderRadius: 8, padding: '7px 14px',
            color: 'rgba(243,234,217,0.85)', fontSize: 12, fontWeight: 500,
            fontFamily: 'system-ui, sans-serif', cursor: 'pointer',
            transition: 'background 180ms ease',
          }}
        >
          <span>📊</span>
          <span>Update my numbers</span>
        </button>
      </div>

      {/* Messages */}
      <div
        ref={scrollRef}
        style={{
          flex: 1, overflowY: 'auto', padding: '20px 40px 12px',
          maskImage: 'linear-gradient(to bottom, transparent 0, #000 40px, #000 100%)',
          WebkitMaskImage: 'linear-gradient(to bottom, transparent 0, #000 40px, #000 100%)',
        }}
      >
        <div style={{ maxWidth: 760, margin: '0 auto' }}>
          {briefing && (
            <ProactiveBanner
              briefing={briefing}
              onDispatchAction={dispatchBriefingAction}
              onDismiss={dismissBriefing}
            />
          )}
          {messages.map((m, i) => {
            if (m.role === 'user') return <UserBubble key={m.id ?? i} content={m.content} />
            if (m.role === 'walkthrough') return <WalkthroughMessage key={m.id ?? i} msg={m} />
            if (m.role === 'creation') return (
              <CreationCanvas
                key={m.id ?? i}
                msg={m}
                onArtifactUpdate={(artifact) => {
                  setMessages(prev => prev.map(x => x.id === m.id ? { ...x, artifact } : x))
                }}
              />
            )
            return <AssistantBubble key={m.id ?? i} content={m.content} streaming={m.streaming} />
          })}
          {loading && !['walkthrough','creation'].includes(messages[messages.length - 1]?.role) && <ThinkingDots />}
        </div>
      </div>

      {/* Input bar */}
      <div style={{
        padding: '14px 40px 28px',
        borderTop: '1px solid rgba(243,234,217,0.07)',
      }}>
        <div style={{ maxWidth: 760, margin: '0 auto', display: 'flex', gap: 10 }}>
          <input
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage() } }}
            placeholder='Ask anything, or "show me how to export invoices in QuickBooks..."'
            disabled={loading}
            style={{
              flex: 1,
              background: 'rgba(243,234,217,0.04)',
              border: '1px solid rgba(243,234,217,0.1)',
              borderRadius: 8, padding: '12px 16px',
              color: '#f3ead9', fontFamily: 'system-ui, sans-serif',
              fontSize: 14, outline: 'none',
              transition: 'border-color 200ms',
            }}
            onFocus={e => e.target.style.borderColor = 'rgba(200,75,49,0.4)'}
            onBlur={e => e.target.style.borderColor = 'rgba(243,234,217,0.1)'}
          />
          <button
            onClick={() => sendMessage()}
            disabled={!input.trim() || loading}
            style={{
              background: input.trim() && !loading ? '#c84b31' : 'rgba(200,75,49,0.12)',
              border: 'none', borderRadius: 8, padding: '12px 22px',
              color: input.trim() && !loading ? 'white' : 'rgba(200,75,49,0.4)',
              cursor: input.trim() && !loading ? 'pointer' : 'default',
              fontFamily: 'system-ui, sans-serif', fontSize: 13, fontWeight: 500,
              transition: 'all 200ms ease', flexShrink: 0,
            }}
          >
            Send
          </button>
        </div>
      </div>
    </div>
  )
}
