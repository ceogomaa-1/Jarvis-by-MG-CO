'use client'
import { GripVertical, X, ArrowRight, Sparkles, Plug } from 'lucide-react'

// One living Home block: it EXPLAINS what changed (ai_summary + evidence) and offers a
// real one-tap action. Most actions inject a precise instruction into the docked chat,
// which runs the full confirm-gated tool pipeline — so Jarvis acts, it doesn't hand homework.
// The header doubles as the react-grid-layout drag handle (.home-drag-handle).

const STATUS_TINT = {
  ok: 'rgba(255,46,81,0.0)',
  needs_connection: 'rgba(245,179,90,0.05)',
  empty: 'rgba(255,255,255,0.0)',
}

function ActionButton({ action, primary, onClick }) {
  if (!action) return null
  const isConnect = action.kind === 'connect' || action.kind === 'navigate'
  const Icon = action.kind === 'chat' ? Sparkles : isConnect ? (action.kind === 'connect' ? Plug : ArrowRight) : ArrowRight
  return (
    <button
      onClick={(e) => { e.stopPropagation(); onClick(action, primary) }}
      onMouseDown={(e) => e.stopPropagation()}
      className="font-pixel"
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 7,
        padding: primary ? '9px 14px' : '6px 10px',
        borderRadius: 10,
        border: primary ? '1px solid var(--home-accent-border, rgba(255,46,81,0.35))' : '1px solid var(--os1-border-soft, rgba(255,255,255,0.08))',
        background: primary ? 'var(--home-accent-soft, rgba(255,46,81,0.12))' : 'transparent',
        color: primary ? 'var(--home-accent, #5b9bff)' : 'var(--os1-text-dim, #A8A8A6)',
        fontSize: primary ? 11 : 10, letterSpacing: '0.02em',
        cursor: 'pointer', whiteSpace: 'nowrap',
        transition: 'background 150ms ease, color 150ms ease, border-color 150ms ease',
      }}
      onMouseEnter={(e) => { if (!primary) e.currentTarget.style.color = 'var(--os1-text, #F5F5F4)' }}
      onMouseLeave={(e) => { if (!primary) e.currentTarget.style.color = 'var(--os1-text-dim, #A8A8A6)' }}
    >
      <Icon size={primary ? 13 : 11} />
      {action.label}
    </button>
  )
}

export default function HomeBlock({ block, onAction, onRemove }) {
  if (!block) return null
  const evidence = Array.isArray(block.evidence) ? block.evidence : []
  const secondary = Array.isArray(block.secondary_actions) ? block.secondary_actions : []

  return (
    <div
      className="os1-card"
      style={{
        height: '100%', display: 'flex', flexDirection: 'column',
        padding: 0, overflow: 'hidden',
        background: `linear-gradient(${STATUS_TINT[block.status] || 'transparent'}, transparent), #15151a`,
        border: '1px solid var(--os1-border-soft, rgba(255,255,255,0.08))',
        borderRadius: 14,
      }}
    >
      {/* Header — also the drag handle */}
      <div
        className="home-drag-handle"
        style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '10px 12px 8px', cursor: 'grab', flexShrink: 0,
          borderBottom: '1px solid var(--os1-border-soft, rgba(255,255,255,0.06))',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 7, minWidth: 0 }}>
          <GripVertical size={13} style={{ color: 'var(--os1-text-faint, #6E6E6C)', flexShrink: 0 }} />
          <span className="font-pixel" style={{
            fontSize: 11.5, color: 'var(--os1-text, #F5F5F4)', letterSpacing: '0.02em',
            whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
          }}>
            {block.title}
          </span>
          {block.status === 'needs_connection' && (
            <span className="os1-serif-micro" style={{ fontSize: 8, color: '#f5b35a', flexShrink: 0 }}>connect</span>
          )}
        </div>
        <button
          onClick={(e) => { e.stopPropagation(); onRemove?.(block.block_key) }}
          onMouseDown={(e) => e.stopPropagation()}
          className="os1-iconbtn" title="Hide this block"
          style={{ padding: 2, color: 'var(--os1-text-faint, #6E6E6C)', flexShrink: 0 }}
        >
          <X size={13} />
        </button>
      </div>

      {/* Body */}
      <div className="os1-scroll" style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '10px 12px 12px' }}>
        <p style={{
          margin: 0, fontSize: 12.5, lineHeight: 1.5,
          color: 'var(--os1-text-dim, #C8C8C6)',
        }}>
          {block.ai_summary}
        </p>

        {evidence.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 10 }}>
            {evidence.slice(0, 4).map((ev, i) => (
              <span key={i} style={{
                display: 'inline-flex', alignItems: 'baseline', gap: 5,
                padding: '3px 8px', borderRadius: 7,
                background: 'rgba(255,255,255,0.03)',
                border: '1px solid var(--os1-border-soft, rgba(255,255,255,0.06))',
              }}>
                <span className="os1-serif-micro" style={{ fontSize: 8, color: 'var(--os1-text-faint, #6E6E6C)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                  {ev.label}
                </span>
                <span className="font-pixel" style={{ fontSize: 10, color: 'var(--os1-text, #E8E8E6)' }}>
                  {String(ev.value)}
                </span>
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Actions */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap',
        padding: '0 12px 12px', flexShrink: 0,
      }}>
        <ActionButton action={block.primary_action} primary onClick={(a, p) => onAction(block, a, p)} />
        {secondary.slice(0, 2).map((a, i) => (
          <ActionButton key={i} action={a} onClick={(act, p) => onAction(block, act, p)} />
        ))}
      </div>
    </div>
  )
}
