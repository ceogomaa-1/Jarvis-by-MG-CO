'use client'
import { useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

const BACKEND = 'https://jarvis-backend-4oz6.onrender.com'

const ACTION_TYPE_LABELS = {
  email_draft: '📧 Email Draft',
  sms_draft: '💬 SMS Draft',
  landing_page: '🌐 Landing Page',
  campaign_bundle: '📦 Campaign Bundle',
  report: '📊 Report',
  analysis: '🔍 Analysis',
  research_brief: '📰 Research Brief',
  strategy_doc: '🗺️ Strategy Doc',
}

const CONNECTOR_LABELS = {
  smtp: 'Send via Email',
  twilio: 'Send via SMS',
  '': 'Manual',
}

function ActionCard({ action, onShip, onDiscard, onExpand, expanded }) {
  const isExternal = action.internal_or_external === 'external'
  const typeLabel = ACTION_TYPE_LABELS[action.action_type] || action.action_type
  const connLabel = CONNECTOR_LABELS[action.connector_type || ''] || action.connector_type

  return (
    <div style={{
      border: '1px solid rgba(243,234,217,0.08)',
      borderRadius: 10, marginBottom: 10, overflow: 'hidden',
    }}>
      {/* Card header */}
      <div
        onClick={onExpand}
        style={{
          display: 'flex', alignItems: 'flex-start', gap: 12,
          padding: '12px 14px', cursor: 'pointer',
          background: expanded ? 'rgba(243,234,217,0.03)' : 'transparent',
        }}
      >
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 4 }}>
            <span style={{
              fontSize: 10, fontWeight: 600, letterSpacing: '0.06em',
              color: 'rgba(243,234,217,0.5)', textTransform: 'uppercase',
            }}>
              {typeLabel}
            </span>
            {isExternal && (
              <span style={{
                fontSize: 10, fontWeight: 600, letterSpacing: '0.05em',
                background: 'rgba(200,75,49,0.12)', color: '#c84b31',
                padding: '2px 6px', borderRadius: 4, textTransform: 'uppercase',
              }}>
                External · {connLabel}
              </span>
            )}
          </div>
          <div style={{ fontSize: 14, color: '#f3ead9', fontWeight: 500, lineHeight: 1.4 }}>
            {action.title}
          </div>
          {action.description && (
            <div style={{ fontSize: 11, color: 'rgba(243,234,217,0.5)', marginTop: 3 }}>
              {action.description}
            </div>
          )}
        </div>
        <span style={{ fontSize: 11, color: 'rgba(243,234,217,0.35)', flexShrink: 0, marginTop: 2 }}>
          {expanded ? '▲' : '▼'}
        </span>
      </div>

      {/* Expanded artifact */}
      {expanded && (
        <div style={{
          borderTop: '1px solid rgba(243,234,217,0.06)',
          padding: '14px 16px',
        }}>
          <div
            className="biz-markdown"
            style={{ fontSize: 13, color: 'rgba(243,234,217,0.85)', lineHeight: 1.7 }}
          >
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {action.artifact_markdown || '*(no artifact)*'}
            </ReactMarkdown>
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 16 }}>
            <button
              onClick={() => onDiscard(action.id)}
              style={{
                background: 'transparent',
                border: '1px solid rgba(239,68,68,0.3)',
                borderRadius: 6, padding: '6px 14px',
                color: '#ef4444', fontSize: 11, cursor: 'pointer',
              }}
            >
              Discard
            </button>
            <button
              onClick={() => onShip(action.id)}
              style={{
                background: '#c84b31', border: 'none',
                borderRadius: 6, padding: '6px 16px',
                color: 'white', fontSize: 11, fontWeight: 600, cursor: 'pointer',
              }}
            >
              {isExternal ? `🚀 Ship via ${connLabel}` : '✅ Mark Done'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

export default function PendingActionsStack({ open, onClose, userId }) {
  const [actions, setActions] = useState([])
  const [loading, setLoading] = useState(true)
  const [expandedId, setExpandedId] = useState(null)

  const loadActions = async () => {
    setLoading(true)
    try {
      const res = await fetch(
        `${BACKEND}/api/business/operator/pending?user_id=${encodeURIComponent(userId || '')}`
      )
      const data = await res.json()
      setActions(data.actions || [])
    } catch (e) {
      console.error('PendingActionsStack load failed', e)
    }
    setLoading(false)
  }

  useEffect(() => {
    if (open && userId) loadActions()
  }, [open, userId])

  const updateAction = async (id, status) => {
    try {
      await fetch(`${BACKEND}/api/business/operator/actions/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status }),
      })
      setActions(prev => prev.filter(a => a.id !== id))
    } catch (e) {
      console.error('Update action failed', e)
    }
  }

  if (!open) return null

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0,
        background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(4px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: 1000,
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          width: '100%', maxWidth: 680, margin: '0 20px',
          background: '#0a0a0a',
          border: '1px solid rgba(243,234,217,0.1)',
          borderRadius: 16, padding: 28,
          fontFamily: 'system-ui, sans-serif',
          maxHeight: '88vh', display: 'flex', flexDirection: 'column',
        }}
      >
        <div style={{
          fontSize: 11, fontWeight: 600, letterSpacing: '0.12em',
          color: '#c84b31', marginBottom: 6, textTransform: 'uppercase',
        }}>
          📋 MORNING QUEUE
        </div>
        <div style={{ fontSize: 18, color: '#f3ead9', marginBottom: 4, fontWeight: 600 }}>
          Operator prepared these overnight
        </div>
        <div style={{ fontSize: 12, color: 'rgba(243,234,217,0.5)', marginBottom: 18, lineHeight: 1.5 }}>
          Review each card. External actions fire through your connected services when you click Ship.
        </div>

        <div style={{ overflowY: 'auto', flex: 1, paddingRight: 4 }}>
          {loading ? (
            <div style={{ color: 'rgba(243,234,217,0.5)', fontSize: 13, padding: 8 }}>
              Loading…
            </div>
          ) : actions.length === 0 ? (
            <div style={{
              textAlign: 'center', padding: '32px 0',
              color: 'rgba(243,234,217,0.35)', fontSize: 13,
            }}>
              No pending actions. The Operator runs nightly at 2:00 AM — enable it in Brand Settings.
            </div>
          ) : (
            actions.map(action => (
              <ActionCard
                key={action.id}
                action={action}
                expanded={expandedId === action.id}
                onExpand={() => setExpandedId(expandedId === action.id ? null : action.id)}
                onShip={id => updateAction(id, 'shipped')}
                onDiscard={id => updateAction(id, 'discarded')}
              />
            ))
          )}
        </div>

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 16 }}>
          <span style={{ fontSize: 11, color: 'rgba(243,234,217,0.4)' }}>
            {actions.length} pending
          </span>
          <button
            onClick={onClose}
            style={{
              background: 'transparent',
              border: '1px solid rgba(243,234,217,0.15)',
              borderRadius: 8, padding: '8px 20px',
              color: 'rgba(243,234,217,0.7)', fontSize: 13,
              fontFamily: 'system-ui, sans-serif', cursor: 'pointer',
            }}
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
