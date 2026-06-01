'use client'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

const ROLE_LABELS = {
  strategist: 'STRATEGIST',
  copywriter: 'COPYWRITER',
  designer: 'DESIGNER',
  researcher: 'RESEARCHER',
  analyst: 'ANALYST',
  reporter: 'REPORTER',
}

const ROLE_ICONS = {
  strategist: '🎯',
  copywriter: '✍️',
  designer: '🎨',
  researcher: '🔍',
  analyst: '📊',
  reporter: '📦',
}

function StatusPill({ agent, status }) {
  const palette = {
    pending: { bg: 'rgba(243,234,217,0.04)', border: 'rgba(243,234,217,0.1)', text: 'rgba(243,234,217,0.5)', dot: 'rgba(243,234,217,0.3)' },
    started: { bg: 'rgba(200,75,49,0.08)', border: 'rgba(200,75,49,0.3)', text: '#f3ead9', dot: '#c84b31' },
    complete: { bg: 'rgba(34,197,94,0.08)', border: 'rgba(34,197,94,0.3)', text: '#f3ead9', dot: '#22c55e' },
    failed: { bg: 'rgba(239,68,68,0.08)', border: 'rgba(239,68,68,0.3)', text: '#f3ead9', dot: '#ef4444' },
  }
  const c = palette[status] || palette.pending

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 10,
      padding: '10px 14px',
      background: c.bg,
      border: `1px solid ${c.border}`,
      borderRadius: 10,
      transition: 'all 300ms ease',
    }}>
      <div style={{
        width: 8, height: 8, borderRadius: '50%',
        background: c.dot,
        animation: status === 'started' ? 'pulseDot 1.2s ease-in-out infinite' : 'none',
        flexShrink: 0,
      }} />
      <div style={{ fontSize: 14, flexShrink: 0 }}>{ROLE_ICONS[agent.role] || '⚙️'}</div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontSize: 10, fontWeight: 600, letterSpacing: '0.08em',
          color: c.text, opacity: 0.7, marginBottom: 2,
        }}>
          {ROLE_LABELS[agent.role] || agent.role.toUpperCase()}
        </div>
        <div style={{
          fontSize: 12, color: c.text,
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
          {agent.task}
        </div>
      </div>
    </div>
  )
}

export default function CreationCanvas({ msg }) {
  const { title, intro, agents = [], statuses = {}, artifact, error, complete } = msg

  return (
    <div style={{ marginBottom: 24, maxWidth: '94%' }}>
      <style>{`
        @keyframes pulseDot {
          0%, 100% { transform: scale(1); opacity: 1; }
          50%      { transform: scale(1.4); opacity: 0.5; }
        }
      `}</style>

      {/* Header */}
      {title && (
        <div style={{
          fontSize: 11, fontWeight: 600, letterSpacing: '0.12em',
          color: '#c84b31', marginBottom: 6, textTransform: 'uppercase',
        }}>
          CREATION 1.0 · Spinning up sub-agents
        </div>
      )}
      {title && (
        <div style={{
          fontSize: 20, fontWeight: 600, color: '#f3ead9',
          marginBottom: 8, fontFamily: 'system-ui, sans-serif',
        }}>
          {title}
        </div>
      )}
      {intro && (
        <div style={{
          fontSize: 14, color: 'rgba(243,234,217,0.7)', marginBottom: 16,
          fontFamily: 'system-ui, sans-serif', lineHeight: 1.6,
        }}>
          {intro}
        </div>
      )}

      {/* Sub-agent pills */}
      {agents.length > 0 && (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
          gap: 10, marginBottom: 18,
        }}>
          {agents.map(a => (
            <StatusPill key={a.id} agent={a} status={statuses[a.id] || 'pending'} />
          ))}
        </div>
      )}

      {/* Final artifact */}
      {artifact && (
        <div style={{
          background: 'rgba(243,234,217,0.03)',
          border: '1px solid rgba(243,234,217,0.1)',
          borderRadius: 14,
          padding: '22px 26px',
          marginTop: 12,
        }}>
          <div style={{
            fontSize: 10, fontWeight: 600, letterSpacing: '0.12em',
            color: '#22c55e', marginBottom: 14, textTransform: 'uppercase',
          }}>
            SHIPPED
          </div>
          <div
            className="biz-markdown"
            style={{
              fontSize: 14, color: '#f3ead9', lineHeight: 1.7,
              fontFamily: 'system-ui, sans-serif',
            }}
          >
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{artifact}</ReactMarkdown>
          </div>
        </div>
      )}

      {/* Error state */}
      {error && (
        <div style={{
          background: 'rgba(239,68,68,0.08)',
          border: '1px solid rgba(239,68,68,0.3)',
          borderRadius: 10,
          padding: '14px 18px',
          color: '#f3ead9', fontSize: 13,
          marginTop: 12,
        }}>
          {error}
        </div>
      )}
    </div>
  )
}
