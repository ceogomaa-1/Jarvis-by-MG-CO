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
import WelcomeState from './WelcomeState'
import JarvisAvatar from './JarvisAvatar'
import ReadinessBar from './ReadinessBar'
import AutonomousToggle from './AutonomousToggle'
import ConfirmActionButton from './ConfirmActionButton'
import { PromptInputBox } from '@/components/ui/ai-prompt-box'
import UsageCounter from './UsageCounter'
import { supabase } from '../../lib/supabase'
import TetrisLoader from '../ui/TetrisLoader'

const BACKEND = 'https://jarvis-backend-4oz6.onrender.com'

function UserBubble({ content, attachments }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 20, flexDirection: 'column', alignItems: 'flex-end', gap: 6 }}
    >
      {attachments && attachments.length > 0 && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
          {attachments.map((att, i) => att.preview_url && (
            <img
              key={i}
              src={att.preview_url}
              alt=""
              style={{ width: 120, height: 120, objectFit: 'cover', borderRadius: 12, border: '1px solid rgba(243,234,217,0.1)' }}
            />
          ))}
        </div>
      )}
      {content && (
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
      )}
    </motion.div>
  )
}

function ThinkingDots() {
  return (
    <div style={{ display: 'flex', gap: 5, marginBottom: 16, paddingTop: 4 }}>
      {[0, 1, 2].map(i => (
        <motion.div
          key={i}
          style={{ width: 6, height: 6, borderRadius: '50%', background: '#c84b31' }}
          animate={{ opacity: [0.3, 1, 0.3], scale: [0.85, 1.1, 0.85] }}
          transition={{ duration: 1, repeat: Infinity, ease: 'easeInOut', delay: i * 0.15 }}
        />
      ))}
    </div>
  )
}

function ToolStatusPill({ toolName }) {
  // Format "google__list_calendar_events" → "google → list calendar events"
  const pretty = toolName
    .replace('__', ' → ')
    .replace(/_/g, ' ')
  return (
    <motion.div
      initial={{ opacity: 0, y: -4 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -4 }}
      transition={{ duration: 0.2 }}
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 6,
        padding: '4px 10px', marginBottom: 8,
        borderRadius: 20,
        background: 'rgba(200,75,49,0.08)',
        border: '1px solid rgba(200,75,49,0.18)',
      }}
    >
      <motion.div
        style={{ width: 6, height: 6, borderRadius: '50%', background: '#c84b31', flexShrink: 0 }}
        animate={{ opacity: [0.4, 1, 0.4] }}
        transition={{ duration: 1.2, repeat: Infinity, ease: 'easeInOut' }}
      />
      <span style={{
        fontFamily: 'var(--font-arcade), monospace',
        fontSize: 10, letterSpacing: '0.08em',
        color: 'rgba(200,75,49,0.8)', textTransform: 'uppercase',
      }}>
        {pretty}…
      </span>
    </motion.div>
  )
}

function AssistantBubble({ content, chunks, streaming, toolStatus }) {
  const hasChunks = chunks && chunks.length > 0

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      style={{ marginBottom: 28, maxWidth: '85%' }}
    >
      <AnimatePresence>
        {streaming && toolStatus && (
          <ToolStatusPill key={toolStatus} toolName={toolStatus} />
        )}
      </AnimatePresence>
      <div
        className="biz-markdown"
        style={{ fontSize: 15, color: 'rgba(243,234,217,0.9)', lineHeight: 1.7, fontFamily: 'system-ui, sans-serif' }}
      >
        {streaming && !hasChunks ? (
          <ThinkingDots />
        ) : streaming && hasChunks ? (
          <p style={{ margin: 0, whiteSpace: 'pre-wrap', lineHeight: 1.7, wordBreak: 'break-word' }}>
            {chunks.slice(0, -1).map(c => c.text).join('')}
            <span key={chunks[chunks.length - 1].key} className="chunk-fade-in">
              {chunks[chunks.length - 1].text}
            </span>
            <span className="streaming-cursor" />
          </p>
        ) : (
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{content || ''}</ReactMarkdown>
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
        title={msg.title} intro={msg.intro}
        steps={msg.steps || []} loading={msg.loading}
        sources={msg.sources || []}
      />
      {msg.complete && msg.walkthroughData && (
        <DownloadPDFButton walkthrough={msg.walkthroughData} />
      )}
    </motion.div>
  )
}

export default function ChatCanvas({
  userId,
  activeConversationId,
  onConversationCreated,
  onConversationsUpdated,
  onMemoryCountUpdate,
}) {
  const [messages, setMessages] = useState([])
  const [messagesLoading, setMessagesLoading] = useState(false)
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [briefing, setBriefing] = useState(null)
  const [toolStatus, setToolStatus] = useState(null)  // active tool name during execution
  const [readiness, setReadiness] = useState(null)
  const [autonomousEnabled, setAutonomousEnabled] = useState(false)
  const [usage, setUsage] = useState(null)
  const msgIdRef = useRef(1)
  const scrollRef = useRef(null)
  const inputRef = useRef(null)
  // Track current conversation ID in a ref so the send handler always has the latest value
  const activeConvRef = useRef(activeConversationId)

  const isActivelyStreaming = messages.some(m => m.streaming === true)

  // Keep ref in sync with prop
  useEffect(() => {
    activeConvRef.current = activeConversationId
  }, [activeConversationId])

  // Check sessionStorage for prefill from workflow canvas "Open in Chat"
  useEffect(() => {
    const prefill = sessionStorage.getItem('jarvis_prefill')
    if (prefill) {
      setInput(prefill)
      sessionStorage.removeItem('jarvis_prefill')
    }
  }, [])

  // Load messages when conversation changes
  useEffect(() => {
    if (activeConversationId === null || activeConversationId === undefined) {
      setMessages([])
      setMessagesLoading(false)
      return
    }
    if (!supabase) return
    setMessagesLoading(true)
    const load = async () => {
      const { data: msgs } = await supabase
        .from('business_messages')
        .select('id, role, content, created_at')
        .eq('conversation_id', activeConversationId)
        .order('created_at', { ascending: true })
      // Normalize DB messages to match in-memory format
      setMessages((msgs || []).map(m => ({
        ...m,
        streaming: false,
        chunks: [],
      })))
      setMessagesLoading(false)
    }
    load().catch(e => { console.error(e); setMessagesLoading(false) })
  }, [activeConversationId])

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
    }
  }, [messages])

  // Fetch usage on mount and on userId change
  useEffect(() => {
    if (!userId) return
    let cancelled = false
    fetch(`${BACKEND}/api/business/usage?user_id=${encodeURIComponent(userId)}`)
      .then(r => r.json())
      .then(d => { if (!cancelled) setUsage(d) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [userId])

  useEffect(() => {
    if (!userId) return
    let cancelled = false
    fetch(`${BACKEND}/api/business/proactive/latest?user_id=${encodeURIComponent(userId)}`)
      .then(r => r.json())
      .then(d => { if (!cancelled) setBriefing(d.briefing || null) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [userId])

  // Poll for proactive insights when autonomous mode is on
  useEffect(() => {
    if (!autonomousEnabled || !userId) return
    const pollProactive = async () => {
      try {
        const res = await fetch(`${BACKEND}/api/business/proactive/unread?user_id=${encodeURIComponent(userId)}`)
        const data = await res.json()
        if (data.messages && data.messages.length > 0) {
          const msg = data.messages[0]
          msgIdRef.current += 1
          setMessages(prev => [...prev, {
            id: msgIdRef.current,
            role: 'assistant',
            content: msg.message,
            is_proactive: true,
            streaming: false,
            chunks: [],
          }])
          await fetch(`${BACKEND}/api/business/proactive/${msg.id}/read`, { method: 'PATCH' })
        }
      } catch {}
    }
    const interval = setInterval(pollProactive, 60000)
    pollProactive()
    return () => clearInterval(interval)
  }, [autonomousEnabled, userId])

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

  const updateMessage = (id, updates) => {
    setMessages(prev => prev.map(m => m.id === id ? { ...m, ...updates } : m))
  }

  const handleActionConfirm = () => {
    sendMessage('Yes, please go ahead.')
  }

  const executeConfirmedAction = async (pendingAction, msgId) => {
    if (!pendingAction?.tool_name) {
      // Legacy text-only pending_action — fall back to re-sending "Yes"
      handleActionConfirm()
      updateMessage(msgId, { action_resolved: true, action_status: 'confirmed' })
      return
    }
    updateMessage(msgId, { action_resolved: true, action_status: 'confirmed' })
    try {
      const res = await fetch(`${BACKEND}/api/business/chat/confirm-action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: userId || '',
          tool_name: pendingAction.tool_name,
          tool_input: pendingAction.tool_input,
          conversation_id: activeConvRef.current || null,
        }),
      })
      const result = await res.json()
      msgIdRef.current += 1
      setMessages(prev => [...prev, {
        id: msgIdRef.current,
        role: 'assistant',
        content: result.response || 'Done.',
        streaming: false,
        chunks: [],
      }])
      onConversationsUpdated?.()
    } catch (err) {
      console.error('Confirm action failed:', err)
      // Fallback: send as a new chat message so Claude can retry
      handleActionConfirm()
    }
  }

  async function fileToAttachment(file) {
    return new Promise((resolve) => {
      const reader = new FileReader()
      reader.onload = (e) => {
        const dataUrl = e.target.result
        const base64 = dataUrl.split(',')[1]
        const isImage = file.type.startsWith('image/')
        const isPdf = file.type === 'application/pdf'
        resolve({
          type: isImage ? 'image' : isPdf ? 'document' : 'text_file',
          media_type: file.type || 'application/octet-stream',
          data: base64,
          name: file.name,
          preview_url: isImage ? dataUrl : null,
        })
      }
      reader.readAsDataURL(file)
    })
  }

  async function sendMessage(overrideText = null, overrideFiles = null) {
    const rawText = (overrideText !== null ? overrideText : input).trim()
    let text = rawText
    if (text.startsWith('[Search: ') && text.endsWith(']')) {
      text = text.slice(9, -1).trim()
    } else if (text.startsWith('[Operator: ') && text.endsWith(']')) {
      text = text.slice(11, -1).trim()
      if (!/^(build|generate|create|design|draft|produce|write|make|launch|put together)\b/i.test(text)) {
        text = 'Build me ' + text
      }
    } else if (text.startsWith('[ShowMe: ') && text.endsWith(']')) {
      text = text.slice(9, -1).trim()
      if (!/^(show me|walk me through|how (do|to))/i.test(text)) {
        text = 'Show me how to ' + text
      }
    }
    const files = overrideFiles || []
    if (!text && files.length === 0) return
    if (loading) return

    // Client-side limit guard (backend also enforces this)
    if (usage && !usage.is_admin && usage.remaining <= 0) {
      msgIdRef.current += 1
      setMessages(prev => [...prev, {
        id: msgIdRef.current,
        role: 'assistant',
        content: `You've reached your daily limit of ${usage.limit} messages. Come back in ${usage.resets_in} — Jarvis will be here.`,
        streaming: false, chunks: [],
      }])
      return
    }
    if (overrideText === null) setInput('')
    inputRef.current?.focus()

    // Convert File objects to base64 attachments
    const attachments = files.length > 0
      ? await Promise.all(files.map(fileToAttachment))
      : []

    msgIdRef.current += 1
    const userMsgId = msgIdRef.current
    setMessages(prev => [...prev, { id: userMsgId, role: 'user', content: text, attachments }])
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
                  walkthroughData: ev.walkthrough, sources: ev.sources || [],
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

    // Regular chat — with 50ms chunk batching for smooth fade-in
    const history = messages
      .filter(m => m.role !== 'walkthrough' && m.role !== 'creation' && typeof m.content === 'string')
      .map(m => ({ role: m.role === 'user' ? 'user' : 'assistant', content: m.content }))

    msgIdRef.current += 1
    const aId = msgIdRef.current
    setMessages(prev => [...prev, { id: aId, role: 'assistant', content: '', streaming: true, chunks: [] }])

    try {
      const res = await fetch(`${BACKEND}/api/business/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text,
          user_id: userId || '',
          conversation_history: history,
          conversation_id: activeConvRef.current || null,
          attachments: attachments.map(a => ({ type: a.type, media_type: a.media_type, data: a.data })),
        }),
      })
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buf = ''
      let acc = ''
      let pendingBatch = ''
      let batchTimer = null
      const allChunks = []

      function flushBatch() {
        if (!pendingBatch) { batchTimer = null; return }
        const batchText = pendingBatch
        const batchKey = Date.now() + Math.random()
        pendingBatch = ''
        batchTimer = null
        allChunks.push({ text: batchText, key: batchKey })
        const chunksSnapshot = [...allChunks]
        const currentContent = acc
        setMessages(prev => prev.map(m =>
          m.id === aId ? { ...m, content: currentContent, chunks: chunksSnapshot } : m
        ))
      }

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
            const chunk = JSON.parse(raw)

            // Handle special event objects
            if (typeof chunk === 'object' && chunk !== null) {
              if (chunk.type === 'conv_id' && chunk.value) {
                if (!activeConvRef.current) {
                  activeConvRef.current = chunk.value
                  onConversationCreated?.(chunk.value)
                }
              } else if (chunk.type === 'tool_call') {
                if (chunk.status === 'executing') {
                  setToolStatus(chunk.name)
                } else if (chunk.status === 'complete') {
                  setToolStatus(null)
                }
              } else if (chunk.type === 'pending_action') {
                setMessages(prev => prev.map(m =>
                  m.id === aId ? { ...m, pending_action: chunk.action, action_resolved: false } : m
                ))
              } else if (chunk.type === 'usage') {
                setUsage(chunk.data)
              }
              continue
            }

            // Regular text chunk
            acc += chunk
            pendingBatch += chunk
            if (!batchTimer) {
              batchTimer = setTimeout(flushBatch, 50)
            }
          } catch {}
        }
      }

      // Flush remaining buffered text
      if (batchTimer) clearTimeout(batchTimer)
      if (pendingBatch) {
        allChunks.push({ text: pendingBatch, key: Date.now() + Math.random() })
      }
      setToolStatus(null)
      setMessages(prev => prev.map(m =>
        m.id === aId ? { ...m, content: acc, chunks: [...allChunks], streaming: false } : m
      ))

      // Notify parent to refresh sidebar (new title may have been generated)
      onConversationsUpdated?.()

    } catch (err) {
      console.error('Chat failed:', err)
      setMessages(prev => prev.map(m =>
        m.id === aId ? { ...m, content: 'Something went wrong. Please try again.', streaming: false } : m
      ))
    }
    setLoading(false)
  }

  const handleSuggestion = (text) => sendMessage(text)

  const hasMessages = messages.length > 0 || messagesLoading

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.96 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 1.04 }}
      transition={{ duration: 0.4, ease: 'easeOut' }}
      style={{ display: 'flex', flexDirection: 'column', height: '100%' }}
    >
      <ChatHeaderMenu userId={userId} onBrandSaved={() => {}} />

      <ReadinessBar
        userId={userId}
        apiUrl={BACKEND}
        onReadinessUpdate={(data) => {
          setReadiness(data)
          if (data?.memory_count != null) onMemoryCountUpdate?.(data.memory_count)
        }}
      />

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
              <WelcomeState onSuggestion={handleSuggestion} isStreaming={loading} />
            </motion.div>
          ) : messagesLoading ? (
            <div
              key="loading"
              style={{
                position: 'absolute', inset: 0,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}
            >
              <TetrisLoader size="sm" speed="fast" loadingText="Loading conversation..." />
            </div>
          ) : (
            <div
              key="messages"
              ref={scrollRef}
              className="biz-chat-scroll"
              style={{
                position: 'absolute', inset: 0,
                overflowY: 'auto',
                padding: '64px 40px 12px',
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
                  if (m.role === 'user') return <UserBubble key={m.id ?? i} content={m.content} attachments={m.attachments} />
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
                    <div key={m.id ?? i}>
                      {m.is_proactive && (
                        <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginBottom: 6 }}>
                          <span style={{ fontSize: 10, color: '#c84b31' }}>⚡</span>
                          <span style={{
                            fontFamily: 'var(--font-arcade), monospace',
                            fontSize: 8,
                            letterSpacing: '0.1em',
                            textTransform: 'uppercase',
                            color: 'rgba(200,75,49,0.55)',
                          }}>
                            Proactive Insight
                          </span>
                        </div>
                      )}
                      <AssistantBubble
                        content={m.content}
                        chunks={m.chunks}
                        streaming={m.streaming}
                        toolStatus={m.streaming ? toolStatus : null}
                      />
                      {m.pending_action && !m.action_resolved && (
                        <ConfirmActionButton
                          action={m.pending_action.description || m.pending_action}
                          onConfirm={() => executeConfirmedAction(m.pending_action, m.id)}
                          onCancel={() => {
                            updateMessage(m.id, { action_resolved: true, action_status: 'cancelled' })
                          }}
                        />
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </AnimatePresence>

        {/* Mini Jarvis avatar — persistent during conversation */}
        {hasMessages && (
          <div style={{
            position: 'absolute', top: 12, left: 0, right: 0, zIndex: 3,
            display: 'flex', justifyContent: 'center',
            pointerEvents: 'none',
          }}>
            <motion.div
              animate={{ opacity: isActivelyStreaming ? 1 : 0.55 }}
              transition={{ duration: 0.4, ease: 'easeInOut' }}
            >
              <JarvisAvatar size={32} isStreaming={isActivelyStreaming || loading} />
            </motion.div>
          </div>
        )}

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
        <div style={{ maxWidth: 760, margin: '0 auto', position: 'relative' }}>
          {/* Usage counter — top-right of input area */}
          {usage && (
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 4 }}>
              <UsageCounter usage={usage} />
            </div>
          )}
          {/* Toggle floats to the left, outside layout flow, keeping input centered */}
          <div style={{ position: 'absolute', left: -68, bottom: 12 }}>
            <AutonomousToggle
              userId={userId}
              apiUrl={BACKEND}
              isReady={readiness?.is_ready === true}
              onToggle={setAutonomousEnabled}
            />
          </div>
          <PromptInputBox
            onSend={(message, files) => sendMessage(message, files)}
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
