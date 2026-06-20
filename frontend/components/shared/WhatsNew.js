'use client'
// Batch 56 — "What's New" feature announcements (shared by Personal + OS1).
//
// Drop <WhatsNewBell userId={userId} variant="personal" /> into a header. It is
// fully self-contained: it renders the bell + unread badge, auto-pops an
// animated modal for any unread announcements on load, and opens a history
// panel on click. Mark-as-seen is persisted, so dismissed cards never re-pop.

import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  fetchAnnouncements,
  markAnnouncementSeen,
  markAllAnnouncementsSeen,
} from '../../lib/announcements'

const THEMES = {
  personal: {
    accent: '#ff9072',
    card: '#0f0e0d',
    border: 'rgba(243,234,217,0.10)',
    ink: '#f3ead9',
    inkDim: 'rgba(243,234,217,0.55)',
    inkFaint: 'rgba(243,234,217,0.38)',
    titleClass: '',
    titleStyle: { fontFamily: "Georgia, 'Times New Roman', serif", fontWeight: 400 },
  },
  business: {
    accent: '#2d7ff9',
    card: '#141414',
    border: 'rgba(255,255,255,0.09)',
    ink: '#ededed',
    inkDim: 'rgba(237,237,237,0.55)',
    inkFaint: 'rgba(237,237,237,0.38)',
    titleClass: 'font-pixel',
    titleStyle: {},
  },
}

const TAG_COLORS = {
  'New Feature': '#ff9072',
  Improvement: '#5fb0ff',
  Fix: '#6cd08a',
}

function tagColor(tag, fallback) {
  return TAG_COLORS[tag] || fallback
}

function fmtDate(iso) {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
  } catch {
    return ''
  }
}

function BellIcon({ size = 20, color }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
      <path d="M13.73 21a2 2 0 0 1-3.46 0" />
    </svg>
  )
}

// A handful of CSS-keyframe sparkles — the "confetti accent", zero new deps.
function Sparkles({ accent }) {
  const dots = [
    { left: '8%', top: '14%', delay: '0s', size: 6 },
    { left: '88%', top: '10%', delay: '0.25s', size: 5 },
    { left: '20%', top: '78%', delay: '0.5s', size: 4 },
    { left: '78%', top: '70%', delay: '0.15s', size: 6 },
    { left: '50%', top: '6%', delay: '0.4s', size: 4 },
    { left: '94%', top: '46%', delay: '0.6s', size: 5 },
  ]
  return (
    <>
      {dots.map((d, i) => (
        <span
          key={i}
          aria-hidden
          style={{
            position: 'absolute', left: d.left, top: d.top,
            width: d.size, height: d.size, borderRadius: '50%',
            background: accent, pointerEvents: 'none',
            boxShadow: `0 0 8px ${accent}`,
            animation: `wn-sparkle 1.8s ease-in-out ${d.delay} infinite`,
          }}
        />
      ))}
    </>
  )
}

function AnnouncementCard({ item, theme, total, index, onNext, isLast }) {
  const accent = tagColor(item.tag, theme.accent)
  return (
    <div style={{ position: 'relative', padding: '34px 30px 28px' }}>
      <Sparkles accent={accent} />

      {/* tag pill */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 18 }}>
        <span style={{
          display: 'inline-flex', alignItems: 'center', gap: 6,
          fontFamily: '-apple-system, "Segoe UI", Roboto, sans-serif',
          fontSize: 10, letterSpacing: '0.18em', textTransform: 'uppercase',
          color: accent, border: `1px solid ${accent}`, borderRadius: 999,
          padding: '5px 12px', background: `${accent}14`,
        }}>
          ✦ {item.tag || 'Update'}
        </span>
        {total > 1 && (
          <span style={{ fontSize: 10, letterSpacing: '0.12em', color: theme.inkFaint, fontFamily: 'monospace' }}>
            {index + 1} / {total}
          </span>
        )}
      </div>

      <h2 className={theme.titleClass} style={{
        margin: '0 0 14px', fontSize: 23, lineHeight: 1.25, color: theme.ink, ...theme.titleStyle,
      }}>
        {item.title}
      </h2>

      {item.media_url && (
        <img
          src={item.media_url}
          alt=""
          style={{
            width: '100%', borderRadius: 12, marginBottom: 16,
            border: `1px solid ${theme.border}`, display: 'block',
          }}
        />
      )}

      <div className="wn-md" style={{ color: theme.inkDim, fontSize: 14.5, lineHeight: 1.65 }}>
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{item.body || ''}</ReactMarkdown>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 26 }}>
        {item.cta_url && (
          <a
            href={item.cta_url}
            target="_blank"
            rel="noreferrer"
            style={{
              flex: 1, textAlign: 'center', textDecoration: 'none',
              fontFamily: '-apple-system, "Segoe UI", Roboto, sans-serif',
              fontSize: 11, fontWeight: 600, letterSpacing: '0.14em', textTransform: 'uppercase',
              color: theme.ink, border: `1px solid ${theme.border}`, borderRadius: 9,
              padding: '13px 18px',
            }}
          >
            {item.cta_label || 'Learn more'}
          </a>
        )}
        <button
          onClick={onNext}
          style={{
            flex: item.cta_url ? 1 : 'unset', minWidth: 130,
            cursor: 'pointer', border: 'none', borderRadius: 9,
            fontFamily: '-apple-system, "Segoe UI", Roboto, sans-serif',
            fontSize: 11, fontWeight: 600, letterSpacing: '0.14em', textTransform: 'uppercase',
            color: '#140b07', background: accent, padding: '14px 22px',
            boxShadow: `0 8px 24px ${accent}40`,
          }}
        >
          {isLast ? 'Got it' : 'Next'}
        </button>
      </div>
    </div>
  )
}

export default function WhatsNewBell({ userId, variant = 'personal', style }) {
  const theme = THEMES[variant] || THEMES.personal
  const [items, setItems] = useState([])
  const [unread, setUnread] = useState(0)

  const [popOpen, setPopOpen] = useState(false)
  const [popQueue, setPopQueue] = useState([])
  const [popIndex, setPopIndex] = useState(0)

  const [historyOpen, setHistoryOpen] = useState(false)

  const load = useCallback(async () => {
    const data = await fetchAnnouncements(userId)
    setItems(data.announcements || [])
    setUnread(data.unread_count || 0)
    return data
  }, [userId])

  // Initial load — auto-pop any unread announcements.
  useEffect(() => {
    if (!userId) return
    let cancelled = false
    ;(async () => {
      const data = await fetchAnnouncements(userId)
      if (cancelled) return
      setItems(data.announcements || [])
      setUnread(data.unread_count || 0)
      const unreadItems = (data.announcements || []).filter(a => !a.seen)
      if (unreadItems.length > 0) {
        setPopQueue(unreadItems)
        setPopIndex(0)
        setPopOpen(true)
      }
    })()
    return () => { cancelled = true }
  }, [userId])

  const closePop = useCallback(async () => {
    setPopOpen(false)
    // Safety net: mark everything in the queue seen so nothing re-pops on refresh.
    await markAllAnnouncementsSeen(userId)
    setItems(prev => prev.map(a => ({ ...a, seen: true })))
    setUnread(0)
  }, [userId])

  const handleNext = useCallback(async () => {
    const current = popQueue[popIndex]
    if (current) {
      markAnnouncementSeen(userId, current.id) // fire-and-forget; persisted seen
      setItems(prev => prev.map(a => (a.id === current.id ? { ...a, seen: true } : a)))
      setUnread(u => Math.max(0, u - 1))
    }
    if (popIndex < popQueue.length - 1) {
      setPopIndex(i => i + 1)
    } else {
      await closePop()
    }
  }, [popQueue, popIndex, userId, closePop])

  if (!userId) return null

  const current = popQueue[popIndex]

  return (
    <>
      {/* Keyframes + markdown styling (injected once per mount; cheap & idempotent) */}
      <style>{`
        @keyframes wn-sparkle {
          0%, 100% { opacity: 0; transform: scale(0.4); }
          50% { opacity: 0.9; transform: scale(1); }
        }
        .wn-md p { margin: 0 0 10px; }
        .wn-md ul { margin: 0 0 10px; padding-left: 20px; }
        .wn-md li { margin: 0 0 5px; }
        .wn-md strong { color: ${theme.ink}; }
        .wn-md a { color: ${theme.accent}; text-decoration: underline; }
        .wn-md code {
          background: rgba(255,255,255,0.07); padding: 1px 5px;
          border-radius: 4px; font-size: 0.88em;
        }
      `}</style>

      {/* Bell + unread badge */}
      <button
        onClick={() => setHistoryOpen(true)}
        title="What's New"
        aria-label="What's New"
        style={{
          position: 'relative', background: 'none', border: `1px solid ${theme.border}`,
          borderRadius: 8, padding: '6px 8px', cursor: 'pointer',
          color: theme.inkDim, display: 'inline-flex', alignItems: 'center',
          transition: 'color 0.2s, border-color 0.2s', lineHeight: 0,
          ...style,
        }}
        onMouseEnter={e => { e.currentTarget.style.color = theme.ink; e.currentTarget.style.borderColor = theme.accent }}
        onMouseLeave={e => { e.currentTarget.style.color = theme.inkDim; e.currentTarget.style.borderColor = theme.border }}
      >
        <BellIcon size={18} color="currentColor" />
        {unread > 0 && (
          <span style={{
            position: 'absolute', top: -6, right: -6, minWidth: 16, height: 16,
            padding: '0 4px', borderRadius: 999, background: theme.accent,
            color: '#140b07', fontSize: 10, fontWeight: 700, lineHeight: '16px',
            textAlign: 'center', boxShadow: `0 0 0 2px ${theme.card}`,
          }}>
            {unread > 9 ? '9+' : unread}
          </span>
        )}
      </button>

      {/* Auto-pop "What's New" modal (animated, carousel for multiple unread) */}
      <AnimatePresence>
        {popOpen && current && (
          <motion.div
            key="wn-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={closePop}
            style={{
              position: 'fixed', inset: 0, zIndex: 9000,
              background: 'rgba(0,0,0,0.74)', backdropFilter: 'blur(6px)',
              display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 18,
            }}
          >
            <motion.div
              key={`wn-card-${current.id}`}
              initial={{ opacity: 0, scale: 0.9, y: 26 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.94, y: 14 }}
              transition={{ type: 'spring', stiffness: 320, damping: 26 }}
              onClick={e => e.stopPropagation()}
              style={{
                position: 'relative', width: '100%', maxWidth: 440,
                maxHeight: '88vh', overflowY: 'auto',
                background: theme.card, border: `1px solid ${theme.border}`,
                borderRadius: 18, boxShadow: '0 24px 80px rgba(0,0,0,0.6)',
              }}
            >
              <button
                onClick={closePop}
                aria-label="Close"
                style={{
                  position: 'absolute', top: 12, right: 12, zIndex: 2,
                  background: 'none', border: 'none', cursor: 'pointer',
                  color: theme.inkFaint, fontSize: 20, lineHeight: 1, padding: 4,
                }}
              >
                ×
              </button>
              <AnnouncementCard
                item={current}
                theme={theme}
                total={popQueue.length}
                index={popIndex}
                onNext={handleNext}
                isLast={popIndex >= popQueue.length - 1}
              />
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* History panel */}
      <AnimatePresence>
        {historyOpen && (
          <motion.div
            key="wn-hist-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setHistoryOpen(false)}
            style={{
              position: 'fixed', inset: 0, zIndex: 9000,
              background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)',
              display: 'flex', justifyContent: 'flex-end',
            }}
          >
            <motion.div
              key="wn-hist-panel"
              initial={{ x: 420, opacity: 0.5 }}
              animate={{ x: 0, opacity: 1 }}
              exit={{ x: 420, opacity: 0 }}
              transition={{ type: 'spring', stiffness: 300, damping: 30 }}
              onClick={e => e.stopPropagation()}
              style={{
                width: '100%', maxWidth: 400, height: '100%',
                background: theme.card, borderLeft: `1px solid ${theme.border}`,
                display: 'flex', flexDirection: 'column',
                boxShadow: '-12px 0 48px rgba(0,0,0,0.5)',
              }}
            >
              <div style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: '22px 24px 16px', borderBottom: `1px solid ${theme.border}`,
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <BellIcon size={18} color={theme.accent} />
                  <span className={theme.titleClass} style={{ fontSize: 16, color: theme.ink, ...theme.titleStyle }}>
                    What's New
                  </span>
                </div>
                <button
                  onClick={() => setHistoryOpen(false)}
                  aria-label="Close"
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: theme.inkFaint, fontSize: 22, lineHeight: 1 }}
                >
                  ×
                </button>
              </div>

              <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '12px 18px 24px' }}>
                {items.length === 0 ? (
                  <div style={{ color: theme.inkFaint, fontSize: 13, textAlign: 'center', padding: '48px 16px', lineHeight: 1.6 }}>
                    Nothing here yet.<br />New features will show up here.
                  </div>
                ) : (
                  items.map(item => {
                    const ac = tagColor(item.tag, theme.accent)
                    return (
                      <div
                        key={item.id}
                        style={{
                          padding: '16px 16px', marginBottom: 12,
                          background: item.seen ? 'transparent' : `${ac}0d`,
                          border: `1px solid ${item.seen ? theme.border : ac + '44'}`,
                          borderRadius: 12,
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 9 }}>
                          <span style={{
                            fontSize: 9.5, letterSpacing: '0.16em', textTransform: 'uppercase',
                            color: ac, fontFamily: '-apple-system, "Segoe UI", Roboto, sans-serif',
                          }}>
                            ✦ {item.tag || 'Update'}
                          </span>
                          <span style={{ fontSize: 10, color: theme.inkFaint, fontFamily: 'monospace' }}>
                            {fmtDate(item.published_at || item.created_at)}
                          </span>
                        </div>
                        <div className={theme.titleClass} style={{ fontSize: 15, color: theme.ink, marginBottom: 7, lineHeight: 1.3, ...theme.titleStyle }}>
                          {item.title}
                        </div>
                        <div className="wn-md" style={{ color: theme.inkDim, fontSize: 13, lineHeight: 1.55 }}>
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>{item.body || ''}</ReactMarkdown>
                        </div>
                        {item.cta_url && (
                          <a
                            href={item.cta_url}
                            target="_blank"
                            rel="noreferrer"
                            style={{ display: 'inline-block', marginTop: 10, fontSize: 12, color: ac, textDecoration: 'none', fontWeight: 600 }}
                          >
                            {item.cta_label || 'Learn more'} →
                          </a>
                        )}
                      </div>
                    )
                  })
                )}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  )
}
