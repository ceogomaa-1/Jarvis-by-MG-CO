'use client'
import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

const SEVERITY_STYLES = {
  red: {
    accent: '#ef4444',
    bg: 'rgba(239,68,68,0.06)',
    border: 'rgba(239,68,68,0.3)',
    label: '🔴 RED FLAG',
  },
  yellow: {
    accent: '#f59e0b',
    bg: 'rgba(245,158,11,0.06)',
    border: 'rgba(245,158,11,0.3)',
    label: '🟡 HEADS UP',
  },
  green: {
    accent: '#22c55e',
    bg: 'rgba(34,197,94,0.05)',
    border: 'rgba(34,197,94,0.25)',
    label: '🟢 ALL CLEAR',
  },
  stale: {
    accent: '#9ca3af',
    bg: 'rgba(156,163,175,0.05)',
    border: 'rgba(156,163,175,0.25)',
    label: '📊 NEEDS NUMBERS',
  },
  none: {
    accent: '#9ca3af',
    bg: 'rgba(156,163,175,0.05)',
    border: 'rgba(156,163,175,0.25)',
    label: '📋 BRIEFING',
  },
}

export default function ProactiveBanner({ briefing, onDispatchAction, onDismiss }) {
  const [dismissing, setDismissing] = useState(false)

  if (!briefing) return null

  const sev = briefing.flag_severity || 'none'
  const s = SEVERITY_STYLES[sev] || SEVERITY_STYLES.none
  const hasAction = !!(briefing.suggested_action && briefing.suggested_action.trim())

  const handleDispatch = () => {
    if (!hasAction) return
    onDispatchAction && onDispatchAction(briefing.suggested_action, briefing.id)
  }

  const handleDismiss = () => {
    setDismissing(true)
    onDismiss && onDismiss(briefing.id)
  }

  return (
    <div style={{
      background: s.bg,
      border: `1px solid ${s.border}`,
      borderRadius: 14,
      padding: '18px 22px',
      margin: '0 0 22px',
      fontFamily: 'system-ui, sans-serif',
      opacity: dismissing ? 0.3 : 1,
      transition: 'opacity 300ms ease',
    }}>
      {/* Header row */}
      <div style={{
        display: 'flex', alignItems: 'center',
        justifyContent: 'space-between', marginBottom: 10,
      }}>
        <div style={{
          fontSize: 10, fontWeight: 600, letterSpacing: '0.14em',
          color: s.accent, textTransform: 'uppercase',
        }}>
          {s.label} · MORNING BRIEFING
        </div>
        <button
          onClick={handleDismiss}
          style={{
            background: 'transparent', border: 'none', cursor: 'pointer',
            color: 'rgba(244,244,242,0.4)', fontSize: 18, padding: '2px 6px',
            lineHeight: 1,
          }}
          aria-label="Dismiss briefing"
        >
          ×
        </button>
      </div>

      {/* Briefing body */}
      <div
        className="biz-markdown"
        style={{
          fontSize: 14, color: '#f4f4f2', lineHeight: 1.65,
          marginBottom: hasAction ? 14 : 0,
        }}
      >
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{briefing.briefing_text || ''}</ReactMarkdown>
      </div>

      {/* Action button */}
      {hasAction && (
        <button
          onClick={handleDispatch}
          onMouseEnter={e => (e.currentTarget.style.background = s.accent)}
          onMouseLeave={e => (e.currentTarget.style.background = `${s.accent}cc`)}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 8,
            background: `${s.accent}cc`,
            border: 'none', borderRadius: 8, padding: '10px 18px',
            color: '#0a0a0a', fontSize: 13, fontWeight: 600,
            fontFamily: 'system-ui, sans-serif', cursor: 'pointer',
            transition: 'background 180ms ease',
          }}
        >
          <span>⚡</span>
          <span>Spawn sub-agents to fix this</span>
          <span style={{ marginLeft: 2 }}>→</span>
        </button>
      )}
    </div>
  )
}
