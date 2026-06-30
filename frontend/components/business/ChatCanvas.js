'use client'
import { useState, useRef, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { motion, AnimatePresence } from 'framer-motion'
import Walkthrough from './Walkthrough'
import DownloadPDFButton from './DownloadPDFButton'
import { findActiveAgentId } from '../../lib/business/agentEditDetector'
import CreationCanvas from './CreationCanvas'
import ProactiveBanner from './ProactiveBanner'
import WelcomeState from './WelcomeState'
import JarvisAvatar from './JarvisAvatar'
import ReadinessBar from './ReadinessBar'
import AutonomousToggle from './AutonomousToggle'
import ConfirmActionButton from './ConfirmActionButton'
import { PromptInputBox } from '@/components/ui/ai-prompt-box'
import UsageCounter from './UsageCounter'
import { supabase } from '../../lib/supabase'
import TetrisLoader from '../ui/TetrisLoader'
import ThinkingIndicator from './ThinkingIndicator'
import UniqueLoading from '@/components/ui/morph-loading'
import { uploadChatAttachment } from '../../lib/business/attachments'
import { AttachmentsRow } from './AttachmentDisplay'

const BACKEND = 'https://jarvis-backend-4oz6.onrender.com'
const DEPLOY_POLL_MS = 5000
const DEPLOY_POLL_MAX_MS = 6 * 60 * 1000
const DIRECT_DEPLOY_RE = /^\s*(?:(?:deploy|publish|ship|launch|push)\s+(?:it|this|the\s+(?:site|website|page))(?:\s+to\s+(?:vercel|github))?|(?:deploy|publish|push)\s+(?:(?:my|the)\s+)?(?:site|website|page)(?:\s+to\s+(?:vercel|github))?|deploy\s+to\s+(?:vercel|github)|(?:make|take|put)\s+(?:it|this|the\s+(?:site|website|page))\s+(?:live|online)|go\s+live|redeploy(?:\s+it)?|deploy)\s*[!?.]*\s*$/i

function cleanProgressLabel(value = '') {
  return value.replace(/\s*\(\d+s(?:\s+elapsed)?(?:,\s*[^)]*)?\)\s*$/i, '').trim()
}

function appendUniqueStage(stages = [], value = '') {
  const next = cleanProgressLabel(value)
  if (!next) return stages
  const cleaned = stages.map(cleanProgressLabel).filter(Boolean)
  if (cleaned[cleaned.length - 1] === next) return cleaned
  return [...cleaned.slice(-7), next]
}

function pendingDeployStorageKey(userId) {
  return `jarvis_pending_deploys_${userId || 'anon'}`
}

function nodeContextSummary(ctx) {
  if (!ctx) return ''
  if (ctx.mode === 'gap') return ctx.label || 'Knowledge gap'
  if (ctx.mode === 'synapse') return ctx.insight || 'Golden synapse'
  return ctx.memory_text || 'Memory'
}

function isActiveCreationMessage(message) {
  if (message?.role !== 'creation') return false
  // A finished standalone page is rehydrated from the DB on reload (via its saved marker),
  // so don't also preserve the in-memory copy — that would double-render it.
  if (message.kind === 'standalone' && message.complete && !message.deploying && !message.deploymentId) {
    return false
  }
  return (
    message.deploying ||
    message.deploymentStatus ||
    message.deploymentId ||
    (message.deploymentStages && message.deploymentStages.length > 0) ||
    (!message.liveUrl && !message.deploymentError)
  )
}

function UserBubble({ content, attachments }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 24, flexDirection: 'column', alignItems: 'flex-end', gap: 6 }}
    >
      <AttachmentsRow attachments={attachments} />
      {content && (
        <div className="os1-bubble-user" style={{
          maxWidth: '70%', padding: '14px 18px 8px',
          fontSize: 14,
          fontFamily: 'var(--pixel)', lineHeight: 1.55,
        }}>
          {content}
          <div className="os1-serif-micro" style={{
            fontSize: 8.5, textAlign: 'right', marginTop: 8,
            color: 'var(--os1-text-faint)',
          }}>
            Just Now
          </div>
        </div>
      )}
    </motion.div>
  )
}

// Morph loader shown while Jarvis is laying down a response (before the first
// token arrives). `.dark` forces the loader squares to render in light (white)
// so they're visible on the dark OS1 chat surface.
function ThinkingDots() {
  return (
    <div
      className="dark"
      style={{
        display: 'flex',
        alignItems: 'center',
        minHeight: 56,
        paddingLeft: 20,
        marginBottom: 8,
        overflow: 'visible',
      }}
    >
      <UniqueLoading variant="morph" size="sm" />
    </div>
  )
}

function ToolStatusPill({ toolName, progress }) {
  // Prefer a human-readable progress message (e.g. "Checking 6 sources…") when
  // the tool is streaming one; otherwise format the tool name nicely.
  // "google__list_calendar_events" → "google → list calendar events"
  const pretty = progress
    ? progress
    : toolName
        .replace('__', ' → ')
        .replace(/_/g, ' ') + '…'
  return (
    <motion.div
      initial={{ opacity: 0, y: -4 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -4 }}
      transition={{ duration: 0.2 }}
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 6,
        padding: '4px 10px', marginBottom: 8,
        borderRadius: 999,
        background: 'var(--os1-blue-soft)',
        border: '1px solid rgba(45,127,249,0.3)',
      }}
    >
      <motion.div
        style={{ width: 6, height: 6, background: 'var(--os1-blue)', flexShrink: 0 }}
        animate={{ opacity: [0.4, 1, 0.4] }}
        transition={{ duration: 1.2, repeat: Infinity, ease: 'easeInOut' }}
      />
      <span className="font-pixel" style={{
        fontSize: 11, letterSpacing: '0.05em',
        color: 'var(--os1-blue)', textTransform: progress ? 'none' : 'lowercase',
      }}>
        {pretty}
      </span>
    </motion.div>
  )
}

function AssistantBubble({ content, chunks, streaming, toolStatus, toolProgress }) {
  const hasChunks = chunks && chunks.length > 0

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      style={{ marginBottom: 30, maxWidth: '80%', display: 'flex', gap: 10 }}
    >
      {/* Pixel bullet point — per Figma */}
      <span className="font-pixel" style={{
        color: 'var(--os1-text-dim)', fontSize: 14, lineHeight: 1.8, flexShrink: 0,
        paddingTop: 1,
      }}>
        ·
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <AnimatePresence>
          {streaming && (toolStatus || toolProgress) && (
            <ToolStatusPill
              key={toolProgress || toolStatus}
              toolName={toolStatus || ''}
              progress={toolProgress}
            />
          )}
        </AnimatePresence>
        <div
          className="os1-markdown"
          style={{ fontSize: 14, color: 'var(--os1-text)', lineHeight: 1.8 }}
        >
          {streaming && !hasChunks ? (
            <ThinkingDots />
          ) : streaming && hasChunks ? (
            <p style={{ margin: 0, whiteSpace: 'pre-wrap', lineHeight: 1.8, wordBreak: 'break-word' }}>
              {chunks.slice(0, -1).map(c => c.text).join('')}
              <span key={chunks[chunks.length - 1].key} className="chunk-fade-in">
                {chunks[chunks.length - 1].text}
              </span>
              <span className="os1-cursor" />
            </p>
          ) : (
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{content || ''}</ReactMarkdown>
          )}
        </div>
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
  injectPrompt,
  onCrmChanged,   // Phase 3: fired after a successful Jarvis CRM write so the cockpit can refresh
  onLeadsChanged, // mgcoleads: fired after a find/push so the Leads cockpit panel can refresh
  onHomeChanged,  // Batch 67: fired after a Home layout command so the Home cockpit can refresh
  surface = null, // Batch 67: 'home' tags the docked Home chat so layout commands route correctly
  compact = false, // Phase 3: docked in the narrow CRM cockpit panel — tighter padding, no side dock
}) {
  // Horizontal padding shrinks when docked so text/controls aren't clipped in the panel.
  const hPad = compact ? 14 : 40
  const [messages, setMessages] = useState([])
  const [messagesLoading, setMessagesLoading] = useState(false)
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [briefing, setBriefing] = useState(null)
  const [toolStatus, setToolStatus] = useState(null)  // active tool name during execution
  const [toolProgress, setToolProgress] = useState(null)  // human-readable progress (e.g. web research)
  const [readiness, setReadiness] = useState(null)
  const [readinessRefresh, setReadinessRefresh] = useState(0)
  const [autonomousEnabled, setAutonomousEnabled] = useState(false)
  const [usage, setUsage] = useState(null)
  const [isThinking, setIsThinking] = useState(false)
  const [nodeContext, setNodeContext] = useState(null)
  // Jarvis GO (Batch 70): opt-in toggle that skips intent pre-classification and sends
  // every message straight to the brain (website__create / walkthrough__generate /
  // dashboard__control become brain-invoked tools instead of being pre-routed to a
  // separate endpoint). Off by default; sticky per-browser via localStorage.
  const [goMode, setGoMode] = useState(false)
  useEffect(() => {
    if (typeof window === 'undefined') return
    try {
      setGoMode(window.localStorage.getItem('jarvis_go_mode') === '1')
    } catch {}
  }, [])
  const handleGoModeChange = (next) => {
    setGoMode(next)
    if (typeof window === 'undefined') return
    try { window.localStorage.setItem('jarvis_go_mode', next ? '1' : '0') } catch {}
  }
  const msgIdRef = useRef(1)
  const scrollRef = useRef(null)
  const inputRef = useRef(null)
  // Track current conversation ID in a ref so the send handler always has the latest value
  const activeConvRef = useRef(activeConversationId)
  // Holds the conversation ID currently mid-stream (or null). When the conv-change
  // effect fires for THIS conversation while a stream is in flight, the assistant's
  // reply hasn't been persisted yet — skip the DB reload so it doesn't wipe the
  // in-flight streaming bubble.
  const streamingConvRef = useRef(null)
  // Scroll-to-bottom anchor and initial-load flag
  const messagesEndRef = useRef(null)
  const didInitialScroll = useRef(false)
  const deployPollersRef = useRef({})

  const isActivelyStreaming = messages.some(m => m.streaming === true)

  // Keep ref in sync with prop
  useEffect(() => {
    activeConvRef.current = activeConversationId
  }, [activeConversationId])

  useEffect(() => {
    return () => {
      Object.values(deployPollersRef.current).forEach(clearInterval)
      deployPollersRef.current = {}
    }
  }, [])

  useEffect(() => {
    if (!userId || typeof window === 'undefined') return
    try {
      const saved = JSON.parse(localStorage.getItem(pendingDeployStorageKey(userId)) || '[]')
      if (!Array.isArray(saved) || saved.length === 0) return
      setMessages(prev => {
        const existing = new Set(prev.map(m => m.deploymentId).filter(Boolean))
        const restored = saved
          .filter(m => m.deploymentId && !existing.has(m.deploymentId))
          .map(m => ({ ...m, id: `deploy-${m.deploymentId}`, role: 'creation' }))
        return restored.length ? [...prev, ...restored] : prev
      })
      for (const msg of saved) {
        if (msg.deploymentId) startDeployPolling(`deploy-${msg.deploymentId}`, msg)
      }
    } catch {}
  }, [userId])

  // Check sessionStorage for prefill from workflow canvas "Open in Chat"
  useEffect(() => {
    const prefill = sessionStorage.getItem('jarvis_prefill')
    if (prefill) {
      setInput(prefill)
      sessionStorage.removeItem('jarvis_prefill')
    }
  }, [])

  // Check sessionStorage for a node-context handoff from The Mind ("Talk to Jarvis about this ->")
  useEffect(() => {
    let raw
    try {
      raw = sessionStorage.getItem('jarvis_node_context')
    } catch {
      raw = null
    }
    if (!raw) return
    try {
      sessionStorage.removeItem('jarvis_node_context')
    } catch {}
    try {
      const ctx = JSON.parse(raw)
      setNodeContext(ctx)
      if (ctx.mode === 'gap' && ctx.prompt) {
        setInput(ctx.prompt)
      }
    } catch {}
  }, [])

  // "Act on this ->" from the Morning Queue — drop the action prompt into the input.
  // Batch 67: Home block actions set autoSend so one tap actually runs it (the write
  // path still hits the existing hold-to-confirm before anything external happens).
  useEffect(() => {
    if (!injectPrompt?.text) return
    if (injectPrompt.autoSend) {
      sendMessage(injectPrompt.text)
    } else {
      setInput(injectPrompt.text)
      inputRef.current?.focus()
    }
  }, [injectPrompt])  // eslint-disable-line react-hooks/exhaustive-deps

  // Load messages when conversation changes
  useEffect(() => {
    if (activeConversationId === null || activeConversationId === undefined) {
      setMessages([])
      setMessagesLoading(false)
      return
    }
    if (!supabase) return
    // A reply is actively streaming for THIS conversation — its assistant message
    // isn't in the DB yet. Skip the reload entirely; reloading now would wipe the
    // in-flight streaming bubble and the reply would appear to "never arrive."
    if (streamingConvRef.current && String(streamingConvRef.current) === String(activeConversationId)) {
      return
    }
    setMessagesLoading(true)
    const load = async () => {
      const { data: msgs } = await supabase
        .from('business_messages')
        .select('id, role, content, created_at, attachments')
        .eq('conversation_id', activeConversationId)
        .order('created_at', { ascending: true })
      // Normalize DB messages to match in-memory format. Assistant messages carrying a
      // creation marker (⟦jarvis-creation:UUID⟧) are rehydrated into a Creation canvas that
      // self-fetches its saved preview/live URL — so a refresh never loses the work.
      const CREATION_MARKER = /⟦jarvis-creation:([0-9a-fA-F-]{36})⟧/
      const dbMessages = (msgs || []).map(m => {
        const base = { ...m, attachments: m.attachments || [], streaming: false, chunks: [] }
        if (m.role === 'assistant' && typeof m.content === 'string') {
          const hit = m.content.match(CREATION_MARKER)
          if (hit) {
            return {
              ...base,
              role: 'creation',
              creationId: hit[1],
              rehydrate: true,
              complete: true,
              note: m.content.replace(CREATION_MARKER, '').trim(),
            }
          }
        }
        return base
      })
      setMessages(prev => {
        // Preserve in-flight creations AND any still-streaming assistant bubble —
        // neither is persisted to the DB until it completes.
        const preserved = prev.filter(m => isActiveCreationMessage(m) || m.streaming === true)
        if (preserved.length === 0) return dbMessages
        const dbIds = new Set(dbMessages.map(m => String(m.id)))
        const filteredPreserved = preserved.filter(m => !dbIds.has(String(m.id)))
        return [...dbMessages, ...filteredPreserved]
      })
      setMessagesLoading(false)
    }
    load().catch(e => { console.error(e); setMessagesLoading(false) })
  }, [activeConversationId])

  useEffect(() => {
    if (messages.length === 0) {
      didInitialScroll.current = false
      return
    }
    const behavior = didInitialScroll.current ? 'smooth' : 'auto'
    didInitialScroll.current = true
    requestAnimationFrame(() => {
      messagesEndRef.current?.scrollIntoView({ behavior })
    })
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

  const savePendingDeploy = (deployMsg) => {
    if (!userId || typeof window === 'undefined' || !deployMsg?.deploymentId) return
    try {
      const key = pendingDeployStorageKey(userId)
      const saved = JSON.parse(localStorage.getItem(key) || '[]')
      const rest = Array.isArray(saved)
        ? saved.filter(m => m.deploymentId !== deployMsg.deploymentId)
        : []
      localStorage.setItem(key, JSON.stringify([...rest, deployMsg]))
    } catch {}
  }

  const removePendingDeploy = (deploymentId) => {
    if (!userId || typeof window === 'undefined' || !deploymentId) return
    try {
      const key = pendingDeployStorageKey(userId)
      const saved = JSON.parse(localStorage.getItem(key) || '[]')
      localStorage.setItem(
        key,
        JSON.stringify((Array.isArray(saved) ? saved : []).filter(m => m.deploymentId !== deploymentId))
      )
    } catch {}
  }

  const startDeployPolling = (messageId, deployMsg) => {
    const deploymentId = deployMsg?.deploymentId || deployMsg?.deployment_id
    if (!deploymentId || deployPollersRef.current[messageId]) return

    const startedAt = Date.now()
    const poll = async () => {
      try {
        const res = await fetch(`${BACKEND}/api/business/deploy-status?user_id=${encodeURIComponent(userId || '')}&deployment_id=${encodeURIComponent(deploymentId)}`)
        const data = await res.json()
        const state = data.state || 'BUILDING'

        if (state === 'READY' && data.url) {
          clearInterval(deployPollersRef.current[messageId])
          delete deployPollersRef.current[messageId]
          removePendingDeploy(deploymentId)
          setMessages(prev => prev.map(m => m.id === messageId ? {
            ...m,
            deploying: false,
            deploymentStatus: null,
            liveUrl: data.url,
            deploymentError: null,
            deploymentMessage: `Live at ${data.url}`,
          } : m))
          onConversationsUpdated?.()
          return
        }

        if (['ERROR', 'FAILED', 'CANCELED'].includes(state)) {
          clearInterval(deployPollersRef.current[messageId])
          delete deployPollersRef.current[messageId]
          removePendingDeploy(deploymentId)
          setMessages(prev => prev.map(m => m.id === messageId ? {
            ...m,
            deploying: false,
            deploymentStatus: null,
            deploymentError: data.logs || data.error || `Build ended with state ${state}`,
          } : m))
          return
        }

        const status = state === 'UNKNOWN'
          ? `Vercel status is temporarily unavailable — retrying safely…`
          : `Vercel is building and validating the site…`
        setMessages(prev => prev.map(m => {
          if (m.id !== messageId) return m
          const updated = {
            ...m,
            deploying: true,
            deploymentStatus: status,
            deploymentStages: appendUniqueStage(m.deploymentStages, status),
          }
          savePendingDeploy(updated)
          return updated
        }))

        if (Date.now() - startedAt > DEPLOY_POLL_MAX_MS) {
          clearInterval(deployPollersRef.current[messageId])
          delete deployPollersRef.current[messageId]
          setMessages(prev => prev.map(m => m.id === messageId ? {
            ...m,
            deploying: false,
            deploymentStatus: null,
            deploymentError: 'Still building after 6 minutes. The repo and expected URL are saved below.',
          } : m))
        }
      } catch {
        setMessages(prev => prev.map(m => m.id === messageId ? {
          ...m,
          deploying: true,
          deploymentStatus: 'Still building — reconnecting to Vercel status…',
        } : m))
      }
    }

    poll()
    deployPollersRef.current[messageId] = setInterval(poll, DEPLOY_POLL_MS)
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
      const toolResult = result.tool_result || {}
      // Confirmed Jarvis CRM write (e.g. delete) — refresh the embedded CRM.
      if (result.crm_changed) onCrmChanged?.()
      // Confirmed leads action — refresh the Leads cockpit panel.
      if (result.leads_changed) onLeadsChanged?.()
      msgIdRef.current += 1
      setMessages(prev => [...prev, {
        id: msgIdRef.current,
        role: 'assistant',
        content: result.response || 'Done.',
        streaming: false,
        chunks: [],
        ...(toolResult.agent_id ? { agent_id: toolResult.agent_id } : {}),
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
          size: file.size,
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

    // Convert File objects to base64 attachments, in parallel with uploading
    // each file to Supabase Storage (chat-attachments) for persistent display.
    const attachments = files.length > 0
      ? await Promise.all(files.map(async (file) => {
          const [att, storagePath] = await Promise.all([
            fileToAttachment(file),
            uploadChatAttachment(file, userId, activeConvRef.current),
          ])
          return { ...att, storage_path: storagePath }
        }))
      : []

    // When files are attached, always use the regular chat path — it has full
    // image/PDF/text handling. The show-me-how and creation detectors only apply
    // to text-only messages; attachments mean "look at this and respond".
    const hasAttachments = attachments.length > 0

    // "Active build context": if Jarvis just created/edited an ElevenLabs agent,
    // pass its id to the intent classifier so "adjust the greeting" routes to
    // chat (update_agent) rather than a walkthrough or a brand-new creation.
    const activeAgentId = !hasAttachments ? findActiveAgentId(messages) : null

    msgIdRef.current += 1
    const userMsgId = msgIdRef.current
    setMessages(prev => [...prev, { id: userMsgId, role: 'user', content: text, attachments }])
    setLoading(true)
    // Show the working indicator within <1s — before the intent-classification
    // round-trip — so there's never dead air while we decide how to route.
    setIsThinking(true)

    // Single backend classification call decides chat vs show-me-how vs
    // create — replaces the old independent regex-detector cascade
    // (agentEditDetector / showMeHowDetector / creationDetector / isDeployConfirmation).
    // Deploy commands are explicit authorization and must never fall into conversational chat.
    // The create endpoint owns the safe "latest saved artifact → Vercel" execution path.
    //
    // Jarvis GO (Batch 70): skip the classify-intent pre-routing call entirely — every
    // message (other than an explicit deploy command, which stays on the existing tested
    // deploy pipeline) goes straight to the brain via /business/chat/stream, which can now
    // call website__create / walkthrough__generate / dashboard__control as tools instead of
    // needing to be pre-routed to a separate endpoint.
    let intent = !hasAttachments && DIRECT_DEPLOY_RE.test(text) ? 'create' : 'chat'
    if (!hasAttachments && intent === 'chat' && !goMode) {
      try {
        const lastAssistant = [...messages].reverse().find(m => m.role === 'assistant' && typeof m.content === 'string' && m.content)
        const res = await fetch(`${BACKEND}/api/business/classify-intent`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message: text,
            active_agent_id: activeAgentId,
            recent_assistant_texts: lastAssistant ? [lastAssistant.content] : [],
            has_attachments: false,
          }),
        })
        if (res.ok) {
          const data = await res.json()
          if (data?.intent) intent = data.intent
        }
      } catch (err) {
        console.error('Intent classification failed, defaulting to chat:', err)
      }
    }

    if (intent === 'show_me_how') {
      msgIdRef.current += 1
      const wId = msgIdRef.current
      setMessages(prev => [...prev, {
        id: wId, role: 'walkthrough',
        title: '', intro: '', steps: [], loading: true, complete: false,
        walkthroughData: null, sources: [],
      }])
      setIsThinking(true)

      try {
        const res = await fetch(`${BACKEND}/api/business/show-me-how`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query: text, user_id: userId || '' }),
        })
        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buf = ''
        let smhFirstContent = false

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
              // Dismiss thinking indicator on first real content
              if (!smhFirstContent && ev.type !== 'status') {
                smhFirstContent = true
                setIsThinking(false)
              }
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
      setIsThinking(false)
      setLoading(false)
      return
    }

    if (intent === 'create') {
      msgIdRef.current += 1
      const cId = msgIdRef.current
      setMessages(prev => [...prev, {
        id: cId, role: 'creation',
        title: '', intro: '', agents: [], statuses: {},
        artifact: '', error: '', complete: false,
        deploying: false, deploymentStages: [], deploymentStatus: null, liveUrl: null, repoUrl: null, dbUrl: null, deploymentMessage: null, deploymentError: null,
        deploymentId: null, expectedUrl: null,
      }])
      setIsThinking(true)
      let createdConversationId = null
      let creationMode = null
      let editedCreationId = null

      try {
        const res = await fetch(`${BACKEND}/api/business/create`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: text, user_id: userId || '', conversation_id: activeConvRef.current || null }),
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
              // Link this creation session to the conversation (new or existing)
              if (ev.type === 'conv_id' && ev.value && !activeConvRef.current) {
                activeConvRef.current = ev.value
                createdConversationId = ev.value
              }
              // Dismiss thinking indicator once the plan (real content) arrives
              if (ev.type === 'plan') {
                creationMode = ev.mode || null
                setIsThinking(false)
              }
              if (ev.type === 'html_artifact' && creationMode === 'standalone_edit') {
                editedCreationId = ev.creation_id || null
                setMessages(prev => prev.map(existing => {
                  if (
                    existing.id === cId ||
                    existing.role !== 'creation' ||
                    existing.creationId !== editedCreationId
                  ) return existing
                  return {
                    ...existing,
                    previewHtml: ev.html,
                    title: ev.title || existing.title,
                    projectName: ev.project_name || existing.projectName,
                    summary: ev.summary || existing.summary,
                    deploymentStatus: ev.deployment_status || existing.deploymentStatus,
                    liveUrl: ev.live_url || existing.liveUrl,
                    complete: true,
                  }
                }))
              }
              if (ev.type === 'deployment_pending') {
                const pendingMsg = {
                  id: cId,
                  role: 'creation',
                  creationId: ev.creation_id,
                  complete: true,
                  deploying: true,
                  deploymentId: ev.deployment_id,
                  repoUrl: ev.repo_url || null,
                  expectedUrl: ev.expected_url || null,
                  dbUrl: ev.db_url || null,
                  deploymentStatus: ev.message || 'Building on Vercel…',
                  deploymentStages: ['Build triggered on Vercel…'],
                  deploymentError: null,
                }
                savePendingDeploy(pendingMsg)
                startDeployPolling(cId, pendingMsg)
              }
              setMessages(prev => prev.map(m => {
                if (m.id !== cId) return m
                if (ev.type === 'plan') {
                  const initialStatuses = {}
                  for (const a of ev.agents) initialStatuses[a.id] = 'pending'
                  return { ...m, title: ev.title, intro: ev.intro, agents: ev.agents, statuses: initialStatuses }
                }
                if (ev.type === 'agent_status') return { ...m, statuses: { ...m.statuses, [ev.id]: ev.status } }
                if (ev.type === 'creation_id') return { ...m, creationId: ev.id }
                if (ev.type === 'creation_stage') return { ...m, stage: ev.stage, stageMessage: ev.message }
                if (ev.type === 'creation_progress') return { ...m, stageMessage: ev.message }
                if (ev.type === 'html_artifact') return {
                  ...m,
                  kind: 'standalone',
                  creationId: ev.creation_id || m.creationId,
                  title: ev.title || m.title,
                  previewHtml: ev.html,
                  projectName: ev.project_name,
                  summary: ev.summary,
                  isFallback: ev.is_fallback,
                  deploymentStatus: ev.deployment_status || m.deploymentStatus,
                  liveUrl: ev.live_url || m.liveUrl,
                }
                if (ev.type === 'artifact') return { ...m, artifact: ev.content }
                if (ev.type === 'complete') return { ...m, complete: true }
                if (ev.type === 'error') return { ...m, error: ev.value, complete: true }
                if (ev.type === 'deployment_started') return { ...m, deploying: true, deploymentStages: ['Starting the deploy pipeline…'], deploymentStatus: 'Starting the deploy pipeline…' }
                if (ev.type === 'deployment_progress') return { ...m, deploying: true, deploymentStatus: ev.message }
                if (ev.type === 'deployment_status') return { ...m, deploying: true, deploymentStatus: ev.message, deploymentStages: appendUniqueStage(m.deploymentStages, ev.message) }
                if (ev.type === 'deployment_pending') return { ...m, complete: true, deploying: true, deploymentStatus: ev.message || 'Vercel is building the site…', deploymentStages: appendUniqueStage(m.deploymentStages, 'Build triggered on Vercel…'), deploymentId: ev.deployment_id, repoUrl: ev.repo_url || m.repoUrl, expectedUrl: ev.expected_url || m.expectedUrl, dbUrl: ev.db_url || m.dbUrl || null, deploymentError: null }
                if (ev.type === 'deployment_complete') return { ...m, deploying: false, deploymentStatus: null, liveUrl: ev.url, repoUrl: ev.repo_url, dbUrl: ev.db_url || null, deploymentMessage: ev.message }
                if (ev.type === 'deployment_error') return { ...m, deploying: false, deploymentStatus: null, deploymentError: ev.value }
                return m
              }))
            } catch {}
          }
        }
        if (creationMode === 'standalone_edit' && editedCreationId) {
          setMessages(prev => {
            const hasExistingCard = prev.some(
              m => m.id !== cId && m.role === 'creation' && m.creationId === editedCreationId
            )
            return hasExistingCard ? prev.filter(m => m.id !== cId) : prev
          })
        }
      } catch (err) {
        console.error('Creation failed:', err)
        setMessages(prev => prev.map(m =>
          m.id === cId
            ? deployPollersRef.current[cId]
              ? { ...m, deploying: true, deploymentStatus: 'Build is still running — polling Vercel status…' }
              : { ...m, error: 'Creation failed. Please try again.', complete: true }
            : m
        ))
      }
      setIsThinking(false)
      if (createdConversationId) {
        onConversationCreated?.(createdConversationId)
      } else {
        onConversationsUpdated?.()
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
    setIsThinking(true)
    streamingConvRef.current = activeConvRef.current || 'pending'

    let result = await runChatStream(aId, text, history, attachments)
    if (!result.gotChunk) {
      // Render free-tier cold start can drop the very first request of a session
      // silently. Retry once, transparently — the thinking indicator stays up
      // throughout since the bubble is still marked `streaming: true`.
      result = await runChatStream(aId, text, history, attachments, true)
    }

    streamingConvRef.current = null
    setToolStatus(null)
    setToolProgress(null)

    if (!result.gotChunk) {
      setIsThinking(false)
      setMessages(prev => prev.map(m =>
        m.id === aId ? { ...m, content: 'Something went wrong. Please try again.', streaming: false } : m
      ))
    } else {
      setIsThinking(false)
      // Notify parent to refresh sidebar (new title may have been generated)
      onConversationsUpdated?.()
    }
    setLoading(false)
    // An action/turn may have changed readiness (memory stored, tool connected).
    // Nudge the bar to refresh — it's throttled to once/60s internally.
    setReadinessRefresh(n => n + 1)
  }

  // Runs one attempt of the chat stream for assistant message `aId`. Returns
  // { gotChunk: boolean } — false means the stream produced nothing (network
  // error, Render cold-start timeout, or zero content within 25s) so the
  // caller can retry once before showing an error bubble.
  async function runChatStream(aId, text, history, attachments, isRetry = false) {
    const controller = new AbortController()
    let gotChunk = false
    let firstChunkTimer = setTimeout(() => controller.abort(), 25000)

    try {
      const res = await fetch(`${BACKEND}/api/business/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text,
          user_id: userId || '',
          conversation_history: history,
          conversation_id: activeConvRef.current || null,
          attachments: attachments.map(a => ({ type: a.type, media_type: a.media_type, data: a.data, name: a.name, storage_path: a.storage_path, size: a.size })),
          node_context: nodeContext,
          surface: surface || undefined,
        }),
        signal: controller.signal,
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
                  streamingConvRef.current = chunk.value
                  onConversationCreated?.(chunk.value)
                }
              } else if (chunk.type === 'tool_call') {
                if (chunk.status === 'executing') {
                  setToolStatus(chunk.name)
                  setToolProgress(null)
                } else if (chunk.status === 'complete') {
                  setToolStatus(null)
                  setToolProgress(null)
                }
              } else if (chunk.type === 'tool_progress') {
                setToolProgress(chunk.value)
              } else if (chunk.type === 'crm_changed') {
                // A Jarvis CRM write landed — tell the cockpit to refresh the embed.
                onCrmChanged?.()
              } else if (chunk.type === 'leads_changed') {
                // A find/push landed — tell the Leads cockpit to refresh its panel.
                onLeadsChanged?.()
              } else if (chunk.type === 'home_changed') {
                // A Home layout command applied — tell the Home cockpit to refresh.
                onHomeChanged?.()
              } else if (chunk.type === 'creation_artifact') {
                // Jarvis GO (Batch 70): website__create / walkthrough__generate ran as a
                // brain-invoked tool inside this same stream — build the exact same
                // role:'creation' / role:'walkthrough' card the classic /business/create
                // and /business/show-me-how endpoints would have produced.
                if (!gotChunk) {
                  gotChunk = true
                  clearTimeout(firstChunkTimer)
                  firstChunkTimer = null
                }
                setIsThinking(false)
                const data = chunk.data || {}
                msgIdRef.current += 1
                const newId = msgIdRef.current
                if (chunk.render_as === 'creation') {
                  setMessages(prev => [...prev, {
                    id: newId, role: 'creation',
                    title: data.title || '', intro: '', agents: [], statuses: {},
                    kind: 'standalone', creationId: data.creation_id || null,
                    previewHtml: data.html || '', projectName: data.title || '', summary: data.summary || '',
                    artifact: '', error: data.error || '', complete: true,
                    deploying: false, deploymentStages: [], deploymentStatus: null, liveUrl: null,
                    repoUrl: null, dbUrl: null, deploymentMessage: null, deploymentError: null,
                    deploymentId: null, expectedUrl: null,
                  }])
                } else if (chunk.render_as === 'walkthrough') {
                  setMessages(prev => [...prev, {
                    id: newId, role: 'walkthrough',
                    title: data.title || '', intro: data.intro || '', steps: data.steps || [],
                    loading: false, complete: true, walkthroughData: data, sources: data.sources || [],
                  }])
                }
              } else if (chunk.type === 'pending_action') {
                if (!gotChunk) {
                  gotChunk = true
                  clearTimeout(firstChunkTimer)
                  firstChunkTimer = null
                }
                setMessages(prev => prev.map(m =>
                  m.id === aId ? { ...m, pending_action: chunk.action, action_resolved: false } : m
                ))
              } else if (chunk.type === 'usage') {
                setUsage(chunk.data)
              }
              continue
            }

            // Regular text chunk
            if (!gotChunk) {
              gotChunk = true
              clearTimeout(firstChunkTimer)
              firstChunkTimer = null
            }
            setIsThinking(false)
            setToolProgress(null)
            acc += chunk
            pendingBatch += chunk
            if (!batchTimer) {
              batchTimer = setTimeout(flushBatch, 30)
            }
          } catch {}
        }
      }

      // Flush remaining buffered text
      if (batchTimer) clearTimeout(batchTimer)
      if (pendingBatch) {
        allChunks.push({ text: pendingBatch, key: Date.now() + Math.random() })
      }
      if (gotChunk) {
        setMessages(prev => prev.map(m =>
          m.id === aId ? { ...m, content: acc, chunks: [...allChunks], streaming: false } : m
        ))
      }
      return { gotChunk }
    } catch (err) {
      console.error(`Chat stream failed${isRetry ? ' (retry)' : ''}:`, err)
      return { gotChunk }
    } finally {
      if (firstChunkTimer) clearTimeout(firstChunkTimer)
    }
  }

  const handleSuggestion = (text) => sendMessage(text)

  const hasMessages = messages.length > 0 || messagesLoading

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 1.02 }}
      transition={{ duration: 0.4, ease: 'easeOut' }}
      style={{ display: 'flex', flexDirection: 'column', height: '100%' }}
    >
      {/* Top center — "Jarvis Knows About Me..." progress */}
      <ReadinessBar
        userId={userId}
        apiUrl={BACKEND}
        refreshSignal={readinessRefresh}
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
                <div style={{ position: 'absolute', top: 0, left: 0, right: 0, padding: `20px ${hPad}px 0`, zIndex: 2 }}>
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
              className="os1-scroll"
              style={{
                position: 'absolute', inset: 0,
                overflowY: 'auto',
                padding: `76px ${hPad}px 12px`,
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
                      userId={userId}
                      onDeploy={() => sendMessage('deploy it')}
                      onArtifactUpdate={(update) => {
                        setMessages(prev => prev.map(x => {
                          if (x.id !== m.id) return x
                          if (typeof update === 'string') return { ...x, artifact: update }
                          if (update?.html) {
                            return {
                              ...x,
                              previewHtml: update.html,
                              summary: update.summary || x.summary,
                              deploymentStatus: update.deploymentStatus || x.deploymentStatus,
                              liveUrl: update.liveUrl || x.liveUrl,
                            }
                          }
                          return x
                        }))
                      }}
                    />
                  )
                  return (
                    <div key={m.id ?? i}>
                      {m.is_proactive && (
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                          <span style={{
                            width: 7, height: 7, background: 'var(--os1-blue)', display: 'inline-block',
                          }} />
                          <span className="font-pixel" style={{
                            fontSize: 10,
                            letterSpacing: '0.06em',
                            textTransform: 'uppercase',
                            color: 'var(--os1-text-faint)',
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
                        toolProgress={m.streaming ? toolProgress : null}
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
                {isThinking && !isActivelyStreaming && <ThinkingIndicator />}
                <div ref={messagesEndRef} />
              </div>
            </div>
          )}
        </AnimatePresence>

        {/* Mini Jarvis globe — persistent during conversation */}
        {hasMessages && (
          <div style={{
            position: 'absolute', top: 10, left: 0, right: 0, zIndex: 3,
            display: 'flex', justifyContent: 'center',
            pointerEvents: 'none',
          }}>
            <motion.div
              animate={{ opacity: isActivelyStreaming ? 1 : 0.5 }}
              transition={{ duration: 0.4, ease: 'easeInOut' }}
            >
              <JarvisAvatar size={40} isStreaming={isActivelyStreaming || loading} />
            </motion.div>
          </div>
        )}

        {/* Gradient fade above input */}
        {hasMessages && (
          <div style={{
            position: 'absolute', bottom: 0, left: 0, right: 0, height: 56,
            background: 'linear-gradient(to bottom, transparent, #131313)',
            pointerEvents: 'none', zIndex: 1,
          }} />
        )}
      </div>

      {/* Input area */}
      <div style={{ padding: `8px ${hPad}px 26px`, flexShrink: 0 }}>
        <div style={{ maxWidth: 740, margin: '0 auto', position: 'relative' }}>
          {/* Mind node-context chip — set via "Talk to Jarvis about this ->" */}
          {nodeContext && (
            <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 8 }}>
              <div style={{
                display: 'flex', alignItems: 'center', gap: 8,
                maxWidth: '100%', padding: '6px 8px 6px 14px',
                background: 'rgba(45,127,249,0.08)',
                border: '1px solid rgba(45,127,249,0.3)',
                borderRadius: 999,
                fontSize: 12, color: '#e8e8e8',
              }}>
                <span style={{
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  maxWidth: 480,
                }}>
                  {nodeContextSummary(nodeContext)}
                </span>
                <button
                  onClick={() => setNodeContext(null)}
                  aria-label="Dismiss context"
                  style={{
                    flexShrink: 0, width: 18, height: 18, borderRadius: '50%',
                    border: 'none', background: 'rgba(232,232,232,0.1)',
                    color: '#9a9a9a', cursor: 'pointer', fontSize: 12,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    lineHeight: 1, padding: 0,
                  }}
                >
                  ×
                </button>
              </div>
            </div>
          )}
          {/* Usage counter — top-right of input area */}
          {usage && (
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 4 }}>
              <UsageCounter usage={usage} />
            </div>
          )}
          <PromptInputBox
            onSend={(message, files) => sendMessage(message, files)}
            isLoading={loading}
            placeholder="Ask Jarvis..."
            enableVoice={false}
            enableUpload={true}
            showViewToggle={true}
            showGoToggle={!compact}
            goMode={goMode}
            onGoModeChange={handleGoModeChange}
          />
          {/* Autonomous Jarvis lever — floats to the right of the input. Hidden when
              docked (compact): it sits outside the panel and would be clipped. */}
          {!compact && (
            <div className="os1-autonomous-dock" style={{ position: 'absolute', left: 'calc(100% + 30px)', bottom: 14 }}>
              <style>{`@media (max-width: 1180px) { .os1-autonomous-dock { display: none !important; } }`}</style>
              <AutonomousToggle
                userId={userId}
                apiUrl={BACKEND}
                isReady={readiness?.is_ready === true}
                onToggle={setAutonomousEnabled}
              />
            </div>
          )}
        </div>
      </div>
    </motion.div>
  )
}
