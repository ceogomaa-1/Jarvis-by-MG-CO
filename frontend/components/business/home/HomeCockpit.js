'use client'
import { useCallback, useEffect, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { X, MessageSquare, RefreshCw, Home as HomeIcon, Sparkles, Undo2 } from 'lucide-react'
import ChatCanvas from '../ChatCanvas'
import HomeGrid from './HomeGrid'
import GoalCommandCenter from './GoalCommandCenter'

import { BACKEND } from '@/lib/backend'

// Batch 68 — theme. Rue sets settings.theme via dashboard__control(set_theme); we turn it
// into CSS variables the blocks read (so "make the accent emerald" / "use a serif font" is live).
const ACCENT_NAMES = {
  blue: '#2d7ff9', emerald: '#34d399', green: '#22c55e', teal: '#14b8a6', purple: '#a855f7',
  violet: '#8b5cf6', pink: '#ec4899', red: '#ef4444', orange: '#f59e0b', amber: '#f59e0b',
  gold: '#eab308', cyan: '#06b6d4', indigo: '#6366f1', rose: '#f43f5e', lime: '#84cc16',
}
const FONTS = {
  serif: "Georgia, 'Times New Roman', serif",
  mono: "var(--pixel), 'SFMono-Regular', Menlo, monospace",
  sans: "inherit",
}

function resolveTheme(theme) {
  const t = theme || {}
  const raw = (t.accent || '').toString().trim().toLowerCase()
  const accent = raw.startsWith('#') ? raw : (ACCENT_NAMES[raw] || '#2d7ff9')
  const style = {
    '--home-accent': accent,
    '--home-accent-border': accent + '59',  // ~35% alpha
    '--home-accent-soft': accent + '1f',    // ~12% alpha fill
  }
  if (t.font && FONTS[t.font]) style.fontFamily = FONTS[t.font]
  if (t.background) style.background = t.background
  return style
}

// Batch 67 — Rue Home: the adaptive command center. A full-screen cockpit (mirrors
// CrmCockpit / LeadsCockpit) that renders INSTANTLY from the precomputed block cache and
// docks the same ChatCanvas so you can chat with Rue while you work the dashboard.
// Blocks act through that docked chat (one tap → Rue runs it, behind hold-to-confirm).
export default function HomeCockpit({ open, onClose, userId, onNavigate }) {
  const [blocks, setBlocks] = useState([])
  const [layout, setLayout] = useState(null)
  const [settings, setSettings] = useState({ default_landing: true })
  const [suggestion, setSuggestion] = useState(null)
  const [composed, setComposed] = useState(true)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [chatOpen, setChatOpen] = useState(true)
  const [conversationId, setConversationId] = useState(null)
  const [injectPrompt, setInjectPrompt] = useState(null)
  const [undoLayout, setUndoLayout] = useState(null)

  const openedAt = useRef(0)
  const firstActionFired = useRef(false)
  const refreshPoll = useRef(null)

  // ── data ────────────────────────────────────────────────────────────────
  const fetchHome = useCallback(async () => {
    if (!userId) return
    try {
      const res = await fetch(`${BACKEND}/api/business/home?user_id=${encodeURIComponent(userId)}`)
      const data = await res.json()
      setBlocks(data.blocks || [])
      setLayout(data.layout || null)
      setSettings(data.settings || { default_landing: true })
      setSuggestion(data.suggestion || null)
      setComposed(!!data.composed)
    } catch (e) {
      console.error('fetchHome failed', e)
    } finally {
      setLoading(false)
    }
  }, [userId])

  const logUsage = useCallback(async (events) => {
    if (!userId || !events?.length) return
    try {
      await fetch(`${BACKEND}/api/business/home/usage`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, events }),
      })
    } catch { /* telemetry is best-effort */ }
  }, [userId])

  // Open: load, start dwell clock, log block views.
  useEffect(() => {
    if (!open || !userId) return
    openedAt.current = Date.now()
    firstActionFired.current = false
    setLoading(true)
    fetchHome()
  }, [open, userId, fetchHome])

  // Once blocks + layout are known, log a view event per visible block (telemetry from day 1).
  const viewsLogged = useRef(false)
  useEffect(() => {
    if (!open || viewsLogged.current || !layout || blocks.length === 0) return
    viewsLogged.current = true
    const hidden = new Set(layout.hidden || [])
    const order = (layout.order || []).filter(k => !hidden.has(k))
    logUsage(order.map((k, i) => ({ block_key: k, event_type: 'view', position: i })))
  }, [open, layout, blocks, logUsage])

  useEffect(() => { if (!open) viewsLogged.current = false }, [open])

  // Close: log dwell time, then bubble up.
  const handleClose = useCallback(() => {
    if (openedAt.current) {
      logUsage([{ event_type: 'dwell', dwell_ms: Date.now() - openedAt.current }])
    }
    if (refreshPoll.current) { clearInterval(refreshPoll.current); refreshPoll.current = null }
    onClose?.()
  }, [logUsage, onClose])

  // Refresh: recompute blocks in the background, then poll the cache a few times.
  const handleRefresh = useCallback(async () => {
    if (!userId || refreshing) return
    setRefreshing(true)
    try {
      await fetch(`${BACKEND}/api/business/home/refresh`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId }),
      })
    } catch { /* ignore */ }
    let n = 0
    refreshPoll.current = setInterval(async () => {
      n += 1
      await fetchHome()
      if (n >= 4) { clearInterval(refreshPoll.current); refreshPoll.current = null; setRefreshing(false) }
    }, 2200)
  }, [userId, refreshing, fetchHome])

  useEffect(() => () => { if (refreshPoll.current) clearInterval(refreshPoll.current) }, [])

  // ── block actions ───────────────────────────────────────────────────────
  const handleAction = useCallback((block, action, isPrimary) => {
    const order = (layout?.order || []).filter(k => !(new Set(layout?.hidden || [])).has(k))
    const position = order.indexOf(block.block_key)
    const events = [{ block_key: block.block_key, event_type: 'click_through', position,
                      metadata: { label: action.label, kind: action.kind, primary: !!isPrimary } }]
    if (!firstActionFired.current) {
      firstActionFired.current = true
      events.push({ block_key: block.block_key, event_type: 'first_action', position })
    }
    logUsage(events)

    if (action.kind === 'navigate') {
      onNavigate?.(action.target)
    } else if (action.kind === 'connect') {
      onNavigate?.('connections')
    } else {
      // 'chat' (and any fallback): one tap → Rue runs it in the docked chat.
      setChatOpen(true)
      setInjectPrompt({ text: action.prompt || action.label, autoSend: true, ts: Date.now() })
    }
  }, [layout, logUsage, onNavigate])

  const askRueFromGoal = useCallback((prompt) => {
    setChatOpen(true)
    setInjectPrompt({ text: prompt, autoSend: true, ts: Date.now() })
  }, [])

  // ── layout persistence ──────────────────────────────────────────────────
  const persistLayout = useCallback(async (newLayout) => {
    setLayout(newLayout)
    try {
      const res = await fetch(`${BACKEND}/api/business/home/layout`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, layout: newLayout }),
      })
      const data = await res.json()
      if (data.layout) setLayout(data.layout)
    } catch (e) { console.error('persistLayout failed', e) }
  }, [userId])

  const handleLayoutChange = useCallback((allLayouts) => {
    if (!layout) return
    persistLayout({ ...layout, layouts: allLayouts })
  }, [layout, persistLayout])

  // Hide / restore route through the tested NL command parser (apply_command rebuilds the
  // grid correctly). Sending the canonical block_key resolves deterministically.
  const sendCommand = useCallback(async (command) => {
    try {
      const res = await fetch(`${BACKEND}/api/business/home/command`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, command }),
      })
      const data = await res.json()
      if (data.layout) setLayout(data.layout)
    } catch (e) { console.error('sendCommand failed', e) }
  }, [userId])

  // Precomputed blocks hide (recoverable via the Hidden tray); custom blocks soft-delete (undo).
  const handleHideBlock = useCallback((key) => { sendCommand(`hide ${key}`) }, [sendCommand])

  const [deletedToast, setDeletedToast] = useState(false)
  const handleCustomDelete = useCallback(async (blockId) => {
    try {
      await fetch(`${BACKEND}/api/business/home/custom/delete`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, block_id: blockId }),
      })
      setDeletedToast(true)
      fetchHome()
    } catch (e) { console.error('custom delete failed', e) }
  }, [userId, fetchHome])

  const restoreDeleted = useCallback(async () => {
    try {
      await fetch(`${BACKEND}/api/business/home/custom/restore`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId }),
      })
      setDeletedToast(false)
      fetchHome()
    } catch (e) { console.error('restore failed', e) }
  }, [userId, fetchHome])

  // ── settings ────────────────────────────────────────────────────────────
  const toggleDefaultLanding = useCallback(async () => {
    const next = { ...settings, default_landing: !settings.default_landing }
    setSettings(next)
    try {
      await fetch(`${BACKEND}/api/business/home/settings`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, settings: next }),
      })
    } catch { /* ignore */ }
  }, [settings, userId])

  // ── Phase 3 suggestion ──────────────────────────────────────────────────
  const resolveSuggestion = useCallback(async (decision) => {
    if (!suggestion) return
    const prev = layout
    try {
      const res = await fetch(`${BACKEND}/api/business/home/suggestion/${suggestion.id}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, decision }),
      })
      const data = await res.json()
      if (decision === 'accept' && data.layout) {
        setLayout(data.layout)
        setUndoLayout(prev)   // one-click Undo
      }
    } catch (e) { console.error('resolveSuggestion failed', e) }
    setSuggestion(null)
  }, [suggestion, layout, userId])

  const undoSuggestion = useCallback(() => {
    if (undoLayout) { persistLayout(undoLayout); setUndoLayout(null) }
  }, [undoLayout, persistLayout])

  if (!open) return null

  return (
    <AnimatePresence>
      <motion.div
        key="home-cockpit"
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        transition={{ duration: 0.2 }}
        style={{ position: 'fixed', inset: 0, zIndex: 58, background: '#0B0B0C', display: 'flex', flexDirection: 'column',
                 ...resolveTheme(settings.theme) }}
      >
        {/* Top bar */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '10px 16px', flexShrink: 0,
          borderBottom: '1px solid var(--os1-border-soft, rgba(255,255,255,0.08))', background: '#131316',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <HomeIcon size={16} style={{ color: 'var(--os1-text-dim, #A8A8A6)' }} />
            <span className="font-pixel" style={{ fontSize: 14, color: 'var(--os1-text, #F5F5F4)' }}>Home</span>
            <span className="os1-serif-micro" style={{ fontSize: 9, color: 'var(--os1-text-faint, #6E6E6C)' }}>
              Rue thinks about your business so you don&apos;t have to
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            {/* Default-landing toggle */}
            <button
              onClick={toggleDefaultLanding}
              className="os1-serif-micro"
              title="Open Home first when you sign in"
              style={{
                display: 'flex', alignItems: 'center', gap: 6, padding: '4px 9px', borderRadius: 8,
                border: '1px solid var(--os1-border-soft, rgba(255,255,255,0.08))', background: 'transparent',
                color: settings.default_landing ? '#5b9bff' : 'var(--os1-text-faint, #6E6E6C)',
                cursor: 'pointer', fontSize: 9,
              }}
            >
              <span style={{
                width: 7, height: 7, borderRadius: 999,
                background: settings.default_landing ? '#2d7ff9' : 'var(--os1-text-faint, #6E6E6C)',
              }} />
              Default landing
            </button>
            <button onClick={handleRefresh} className="os1-iconbtn" title="Recompute Home" disabled={refreshing}>
              <RefreshCw size={16} style={{ animation: refreshing ? 'spin 1s linear infinite' : 'none' }} />
            </button>
            <button onClick={() => setChatOpen(o => !o)} className="os1-iconbtn" title={chatOpen ? 'Hide chat' : 'Show chat'}>
              <MessageSquare size={16} />
            </button>
            <button onClick={handleClose} className="os1-iconbtn" title="Close Home"><X size={18} /></button>
          </div>
        </div>
        <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>

        {/* Phase 3 — adaptive suggestion banner (suggestion-only) */}
        {suggestion && (
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12,
            padding: '9px 16px', background: 'rgba(45,127,249,0.08)',
            borderBottom: '1px solid rgba(45,127,249,0.18)', flexShrink: 0,
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
              <Sparkles size={14} style={{ color: '#5b9bff', flexShrink: 0 }} />
              <span style={{ fontSize: 12, color: 'var(--os1-text, #E8E8E6)', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {suggestion.message}
              </span>
            </div>
            <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
              <button onClick={() => resolveSuggestion('accept')} className="font-pixel"
                style={{ padding: '5px 11px', borderRadius: 8, fontSize: 10, border: '1px solid rgba(45,127,249,0.4)',
                         background: 'rgba(45,127,249,0.14)', color: '#5b9bff', cursor: 'pointer' }}>
                Apply
              </button>
              <button onClick={() => resolveSuggestion('reject')} className="font-pixel"
                style={{ padding: '5px 11px', borderRadius: 8, fontSize: 10, border: '1px solid var(--os1-border-soft, rgba(255,255,255,0.08))',
                         background: 'transparent', color: 'var(--os1-text-faint, #6E6E6C)', cursor: 'pointer' }}>
                Dismiss
              </button>
            </div>
          </div>
        )}
        {undoLayout && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 16px',
                        background: 'rgba(255,255,255,0.03)', borderBottom: '1px solid var(--os1-border-soft, rgba(255,255,255,0.06))', flexShrink: 0 }}>
            <span className="os1-serif-micro" style={{ fontSize: 9, color: 'var(--os1-text-faint, #6E6E6C)' }}>Reorganized your Home.</span>
            <button onClick={undoSuggestion} className="font-pixel"
              style={{ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '3px 9px', borderRadius: 7, fontSize: 9,
                       border: '1px solid var(--os1-border-soft, rgba(255,255,255,0.08))', background: 'transparent', color: 'var(--os1-text-dim, #A8A8A6)', cursor: 'pointer' }}>
              <Undo2 size={11} /> Undo
            </button>
          </div>
        )}
        {deletedToast && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 16px',
                        background: 'rgba(255,255,255,0.03)', borderBottom: '1px solid var(--os1-border-soft, rgba(255,255,255,0.06))', flexShrink: 0 }}>
            <span className="os1-serif-micro" style={{ fontSize: 9, color: 'var(--os1-text-faint, #6E6E6C)' }}>Block deleted.</span>
            <button onClick={restoreDeleted} className="font-pixel"
              style={{ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '3px 9px', borderRadius: 7, fontSize: 9,
                       border: '1px solid var(--os1-border-soft, rgba(255,255,255,0.08))', background: 'transparent', color: 'var(--os1-text-dim, #A8A8A6)', cursor: 'pointer' }}>
              <Undo2 size={11} /> Undo
            </button>
            <button onClick={() => setDeletedToast(false)} className="os1-iconbtn" title="Dismiss" style={{ padding: 2, color: 'var(--os1-text-faint,#6E6E6C)' }}><X size={12} /></button>
          </div>
        )}

        {/* Body: grid + docked chat */}
        <div style={{ flex: 1, minHeight: 0, display: 'flex' }}>
          <div className="os1-scroll" style={{ flex: 1, minWidth: 0, overflowY: 'auto', padding: '16px 16px 40px' }}>
            {!loading && <GoalCommandCenter userId={userId} onAskRue={askRueFromGoal} />}
            {loading ? (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '60%', color: 'var(--os1-text-faint, #6E6E6C)' }}>
                <span className="font-pixel" style={{ fontSize: 12 }}>Loading your Home…</span>
              </div>
            ) : (!composed && blocks.length === 0) ? (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '60%', gap: 14, textAlign: 'center' }}>
                <HomeIcon size={28} style={{ color: 'var(--os1-text-faint, #6E6E6C)' }} />
                <div className="font-pixel" style={{ fontSize: 14, color: 'var(--os1-text, #F5F5F4)' }}>Your Home isn&apos;t composed yet</div>
                <div className="os1-serif-micro" style={{ fontSize: 11, maxWidth: 360, color: 'var(--os1-text-faint, #6E6E6C)' }}>
                  Rue composes Home from your overnight Operator run. Compose it now and it&apos;ll be ready every morning.
                </div>
                <button onClick={handleRefresh} disabled={refreshing} className="font-pixel"
                  style={{ padding: '9px 16px', borderRadius: 10, fontSize: 11, border: '1px solid rgba(45,127,249,0.35)',
                           background: 'rgba(45,127,249,0.12)', color: '#5b9bff', cursor: 'pointer' }}>
                  {refreshing ? 'Composing…' : 'Compose my Home'}
                </button>
              </div>
            ) : layout && (
              <>
                <HomeGrid
                  layout={layout}
                  blocks={blocks}
                  onAction={handleAction}
                  onHideBlock={handleHideBlock}
                  onLayoutChange={handleLayoutChange}
                  userId={userId}
                  onCustomChanged={fetchHome}
                  onCustomDelete={handleCustomDelete}
                />
                {(layout.hidden || []).length > 0 && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginTop: 18 }}>
                    <span className="os1-serif-micro" style={{ fontSize: 9, color: 'var(--os1-text-faint, #6E6E6C)' }}>Hidden:</span>
                    {(layout.hidden || []).map((k) => (
                      <button key={k} onClick={() => sendCommand(`show ${k}`)} className="font-pixel"
                        style={{ padding: '3px 9px', borderRadius: 7, fontSize: 9, border: '1px solid var(--os1-border-soft, rgba(255,255,255,0.08))',
                                 background: 'transparent', color: 'var(--os1-text-dim, #A8A8A6)', cursor: 'pointer' }}>
                        + {k.replace(/_/g, ' ')}
                      </button>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>

          {/* Docked chat — the same ChatCanvas, scoped to Home (surface="home") */}
          <AnimatePresence>
            {chatOpen && (
              <motion.div
                key="home-chat-dock"
                initial={{ width: 0, opacity: 0 }}
                animate={{ width: 'min(420px, 36vw)', opacity: 1 }}
                exit={{ width: 0, opacity: 0 }}
                transition={{ duration: 0.2, ease: 'easeOut' }}
                style={{
                  borderLeft: '1px solid var(--os1-border-soft, rgba(255,255,255,0.08))',
                  background: '#131313', display: 'flex', flexDirection: 'column',
                  minWidth: 300, flexShrink: 0, overflow: 'hidden',
                }}
              >
                <div style={{ flex: 1, minHeight: 0, minWidth: 0, position: 'relative' }}>
                  <ChatCanvas
                    userId={userId}
                    activeConversationId={conversationId}
                    onConversationCreated={setConversationId}
                    onConversationsUpdated={() => {}}
                    onMemoryCountUpdate={() => {}}
                    onHomeChanged={fetchHome}
                    surface="home"
                    injectPrompt={injectPrompt}
                    compact
                  />
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </motion.div>
    </AnimatePresence>
  )
}
