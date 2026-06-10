'use client'
import { useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

const BACKEND = 'https://jarvis-backend-4oz6.onrender.com'

const GLASS_OVERLAY = {
  position: 'fixed', inset: 0,
  background: 'rgba(0,0,0,0.55)',
  backdropFilter: 'blur(6px)',
  WebkitBackdropFilter: 'blur(6px)',
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  zIndex: 1000,
}

const GLASS_PANEL = {
  width: '100%', maxWidth: 720, margin: '0 20px',
  background: 'rgba(15, 15, 18, 0.55)',
  backdropFilter: 'blur(28px) saturate(180%)',
  WebkitBackdropFilter: 'blur(28px) saturate(180%)',
  border: '1px solid rgba(232,232,232,0.15)',
  borderRadius: 20,
  padding: 28,
  fontFamily: 'system-ui, sans-serif',
  boxShadow: '0 24px 60px rgba(0,0,0,0.55), inset 0 1px 0 rgba(232,232,232,0.06)',
  maxHeight: '88vh', display: 'flex', flexDirection: 'column',
}

function ActionCard({ action, onUpdate, busy }) {
  const [expanded, setExpanded] = useState(false)
  const isExternal = action.internal_or_external === 'external'

  return (
    <div style={{
      background: 'rgba(232,232,232,0.03)',
      border: `1px solid ${isExternal ? 'rgba(45,127,249,0.25)' : 'rgba(232,232,232,0.1)'}`,
      borderRadius: 12, padding: '14px 18px', marginBottom: 10,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
        <span style={{
          fontSize: 9, fontWeight: 700, letterSpacing: '0.1em',
          color: isExternal ? '#2d7ff9' : 'rgba(232,232,232,0.6)',
          textTransform: 'uppercase',
          background: isExternal ? 'rgba(45,127,249,0.1)' : 'rgba(232,232,232,0.06)',
          padding: '2px 6px', borderRadius: 4,
        }}>
          {isExternal ? '⚡ EXTERNAL' : '🧠 INTERNAL'}
        </span>
        <span style={{ fontSize: 10, color: 'rgba(232,232,232,0.4)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
          {action.action_type?.replace(/_/g, ' ')}
        </span>
      </div>
      <div style={{ fontSize: 14, color: '#e8e8e8', fontWeight: 600, marginBottom: 4 }}>
        {action.title}
      </div>
      {action.description && (
        <div style={{ fontSize: 12, color: 'rgba(232,232,232,0.6)', marginBottom: 8 }}>
          {action.description}
        </div>
      )}

      {expanded && action.artifact_markdown && (
        <div style={{
          background: 'rgba(0,0,0,0.35)',
          border: '1px solid rgba(232,232,232,0.06)',
          borderRadius: 8, padding: '14px 16px', marginTop: 10,
          maxHeight: 360, overflowY: 'auto',
        }}>
          <div className="biz-markdown" style={{ fontSize: 13, color: '#e8e8e8', lineHeight: 1.65 }}>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{action.artifact_markdown}</ReactMarkdown>
          </div>
        </div>
      )}

      <div style={{ display: 'flex', gap: 6, marginTop: 10, flexWrap: 'wrap' }}>
        <button
          onClick={() => setExpanded(e => !e)}
          style={{
            background: 'rgba(232,232,232,0.04)', border: '1px solid rgba(232,232,232,0.12)',
            borderRadius: 6, padding: '6px 12px', color: '#e8e8e8', fontSize: 11,
            cursor: 'pointer', fontFamily: 'system-ui, sans-serif',
          }}
        >
          {expanded ? 'Hide preview' : 'Preview'}
        </button>
        <button
          onClick={() => onUpdate('shipped')}
          disabled={busy}
          style={{
            background: 'rgba(34,197,94,0.15)',
            border: '1px solid rgba(34,197,94,0.4)',
            borderRadius: 6, padding: '6px 14px', color: '#22c55e',
            fontSize: 11, fontWeight: 600, cursor: busy ? 'default' : 'pointer',
            fontFamily: 'system-ui, sans-serif',
          }}
        >
          ✓ {isExternal ? 'Ship' : 'Mark Done'}
        </button>
        <button
          onClick={() => onUpdate('discarded')}
          disabled={busy}
          style={{
            background: 'transparent', border: '1px solid rgba(239,68,68,0.3)',
            borderRadius: 6, padding: '6px 12px', color: '#ef4444',
            fontSize: 11, cursor: busy ? 'default' : 'pointer',
            fontFamily: 'system-ui, sans-serif',
          }}
        >
          Discard
        </button>
      </div>
    </div>
  )
}

export default function MorningQueueModal({ open, onClose, userId }) {
  const [actions, setActions] = useState([])
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState(null)

  const reload = async () => {
    if (!userId) return
    setLoading(true)
    try {
      const r = await fetch(`${BACKEND}/api/business/operator/pending?user_id=${encodeURIComponent(userId)}`)
      const d = await r.json()
      setActions(d.actions || [])
    } catch (e) { console.error(e) }
    setLoading(false)
  }

  useEffect(() => {
    if (open) reload()
  }, [open, userId])

  const updateAction = async (actionId, status) => {
    setBusyId(actionId)
    try {
      await fetch(`${BACKEND}/api/business/operator/actions/${actionId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, status }),
      })
      setActions(prev => prev.filter(a => a.id !== actionId))
    } catch (e) { console.error(e) }
    setBusyId(null)
  }

  if (!open) return null

  return (
    <div onClick={onClose} style={GLASS_OVERLAY}>
      <div onClick={e => e.stopPropagation()} style={GLASS_PANEL}>
        <div style={{
          fontFamily: 'var(--font-pixel), monospace',
          fontSize: 10, letterSpacing: '0.12em',
          color: '#2d7ff9', marginBottom: 8, textTransform: 'uppercase',
        }}>
          📋 MORNING QUEUE
        </div>
        <div style={{
          fontFamily: 'var(--font-pixel), monospace',
          fontSize: 13, color: '#e8e8e8', marginBottom: 6, lineHeight: 1.5,
        }}>
          {loading ? 'Loading…' : actions.length === 0 ? 'Inbox zero' : `${actions.length} pending action${actions.length === 1 ? '' : 's'}`}
        </div>
        <div style={{ fontSize: 12, color: 'rgba(232,232,232,0.55)', marginBottom: 18 }}>
          {actions.length === 0 && !loading
            ? 'Nothing queued right now. Jarvis will surface new work each morning at 2 AM.'
            : 'Review what Jarvis prepared for you. Ship to deploy, Discard to dismiss.'}
        </div>

        <div style={{ overflowY: 'auto', flex: 1, paddingRight: 4 }}>
          {actions.map(a => (
            <ActionCard
              key={a.id}
              action={a}
              busy={busyId === a.id}
              onUpdate={(status) => updateAction(a.id, status)}
            />
          ))}
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 16 }}>
          <button
            onClick={onClose}
            style={{
              background: 'transparent',
              border: '1px solid rgba(232,232,232,0.1)',
              borderRadius: 12, padding: '10px 24px',
              color: 'rgba(232,232,232,0.7)', fontSize: 13,
              fontFamily: 'system-ui, sans-serif', cursor: 'pointer',
              transition: 'all 200ms ease',
            }}
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
