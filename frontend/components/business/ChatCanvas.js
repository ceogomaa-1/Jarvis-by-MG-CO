'use client'
import { useState, useRef, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { motion, AnimatePresence } from 'framer-motion'
import { detectShowMeHow } from '../../lib/business/showMeHowDetector'
import Walkthrough from './Walkthrough'
import DownloadPDFButton from './DownloadPDFButton'
import { detectCreation } from '../../lib/business/creationDetector'
import CreationCanvas from './CreationCanvas'
import ProactiveBanner from './ProactiveBanner'
import ChatHeaderMenu from './ChatHeaderMenu'
import ViewToggle from './workflow/ViewToggle'
import WelcomeState from './WelcomeState'
import { PromptInputBox } from '@/components/ui/ai-prompt-box'

const BACKEND = 'https://jarvis-backend-4oz6.onrender.com'

function UserBubble({ content }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 20 }}
    >
      <div style={{
        maxWidth: '70%', padding: '12px 18px',
        borderRadius: '20px 20px 4px 20px',
        background: 'rgba(243,234,217,0.06)',
        border: '1px solid rgba(243,234,217,0.04)',
        color: '#f3ead9', fontSize: 15,
        fontFamily: 'system-ui, sans-serif', lineHeight: 1.6,
      }}>
        {content}
      </div>
    </motion.div>
  )
}

function AssistantBubble({ content, streaming }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      style={{ marginBottom: 28, maxWidth: '85%' }}
    >
      <div
        className="biz-markdown"
        style={{
          fontSize: 15, color: 'rgba(243,234,217,0.9)', lineHeight: 1.7,
          fontFamily: 'system-ui, sans-serif',
        }}
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
    </motion.div>
  )
}

function WalkthroughMessage({ msg }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      style={{ marginBottom: 28, maxWidth: '94%' }}
    >
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
    </motion.div>
  )
}

function StreamingDot() {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      style={{ marginBottom: 12 }}
    >
      <div style={{
        width: 8, height: 8, borderRadius: '50%',
        background: '#c84b31', animation: 'bizDotPulse 1s ease-in-out infinite',
      }} />
    </motion.div>
  )
}

function ThinkingDots() {
  return (
    <div style={{ display: 'flex', gap: 5, marginBottom: 16 }}>
      {[0, 1, 2].map(i => (
        <div key={i} style={{
          width: 6, height: 6, borderRadius: '50%', background: 'rgba(200,75,49,0.7)',
          animation: `bizDot 1.2s ease-in-out ${i * 0.2}s infinite`,
        }} />
      ))}
    </div>
  )
}

export default function ChatCanvas({ userId }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [briefing, setBriefing] = useState(null)
  const msgIdRef = useRef(1)
  const scrollRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
    }
  }, [messages])

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
    const rawText = (overrideText !== null ? overrideText : input).trim()
    let text = rawText
    let routingHint = null
    if (text.startsWith('[Search: ') && text.endsWith(']')) {
      text = text.slice(9, -1).trim()
      routingHint = 'search'
    } else if (text.startsWith('[Operator: ') && text.endsWith(']')) {
      text = text.slice(11, -1).trim()
      if (!/^(build|generate|create|design|draft|produce|write|make|launch|put together)\b/i.test(text)) {
        text = 'Build me ' + text
      }
      routingHint = 'operator'
    } else if (text.startsWith('[ShowMe: ') && text.endsWith(']')) {
      text = text.slice(9, -1).trim()
      if (!/^(show me|walk me through|how (do|to))/i.test(text)) {
        text = 'Show me how to ' + text
      }
      routingHint = 'showme'
    }
    if (!text || loading) return
    if (overrideText === null) setInput('')
    inputRef.current?.focus()

    msgIdRef.current += 1
    const userMsgId = msgIdRef.current
    setMessages(prev => [...prev, { id: userMsgId, role: 'user', content: text }])
    setLoading(true)

    if (detectShowMeHow(text)) {
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
                if (ev.type === 'agent_status') return { ...m, statuses: { ...m.statuses, [ev.id]: ev.status } }
                if (ev.type === 'creation_id') return { ...m, creationId: ev.id }
                if (ev.type === 'artifact') return { ...m, artifact: ev.content }
                if (ev.type === 'complete') return { ...m, complete: true }
                if (ev.type === 'error') return { ...m, error: ev.value, complete: true }
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

    // Regular chat
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

  const handleSuggestion = (text) => {
    sendMessage(text)
  }

  const hasMessages = messages.length > 0

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.96 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 1.04 }}
      transition={{ duration: 0.4, ease: 'easeOut' }}
      style={{ display: 'flex', flexDirection: 'column', height: '100%' }}
    >
      <style>{`
        @keyframes bizBlink { 50% { opacity: 0; } }
        @keyframes bizDot {
          0%, 80%, 100% { opacity: 0.2; transform: scale(0.8); }
          40%            { opacity: 1;   transform: scale(1); }
        }
        @keyframes bizDotPulse {
          0%, 100% { opacity: 0.4; transform: scale(0.9); }
          50%       { opacity: 1;   transform: scale(1); }
        }
      `}</style>

      <ChatHeaderMenu userId={userId} onBrandSaved={() => {}} />
      <ViewToggle />

      {/* Messages or Welcome */}
      <div style={{ flex: 1, minHeight: 0, position: 'relative' }}>
        <AnimatePresence mode="wait">
          {!hasMessages ? (
            <motion.div
              key="welcome"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0, scale: 0.98 }}
              transition={{ duration: 0.3 }}
              style={{ position: 'absolute', inset: 0 }}
            >
              {briefing && (
                <div style={{ position: 'absolute', top: 0, left: 0, right: 0, padding: '20px 40px 0', zIndex: 2 }}>
                  <div style={{ maxWidth: 760, margin: '0 auto' }}>
                    <ProactiveBanner
                      briefing={briefing}
                      onDispatchAction={dispatchBriefingAction}
                      onDismiss={dismissBriefing}
                    />
                  </div>
                </div>
              )}
              <WelcomeState onSuggestion={handleSuggestion} />
            </motion.div>
          ) : (
            <div
              key="messages"
              ref={scrollRef}
              className="biz-chat-scroll"
              style={{
                position: 'absolute', inset: 0,
                overflowY: 'auto',
                padding: '24px 40px 12px',
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
                  return (
                    <AssistantBubble
                      key={m.id ?? i}
                      content={m.content}
                      streaming={m.streaming}
                    />
                  )
                })}
                {loading && messages.length > 0 && messages[messages.length - 1]?.role === 'user' && (
                  <ThinkingDots />
                )}
              </div>
            </div>
          )}
        </AnimatePresence>

        {/* Gradient fade above input */}
        {hasMessages && (
          <div style={{
            position: 'absolute', bottom: 0, left: 0, right: 0, height: 56,
            background: 'linear-gradient(to bottom, transparent, #0a0908)',
            pointerEvents: 'none', zIndex: 1,
          }} />
        )}
      </div>

      {/* Input area */}
      <div style={{ padding: '8px 40px 24px', flexShrink: 0 }}>
        <div style={{ maxWidth: 760, margin: '0 auto' }}>
          <PromptInputBox
            onSend={(message) => sendMessage(message)}
            isLoading={loading}
            placeholder="Message Jarvis..."
            enableVoice={false}
            enableUpload={true}
          />
        </div>
      </div>
    </motion.div>
  )
}
