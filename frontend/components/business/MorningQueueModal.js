'use client'
import { useEffect, useState } from 'react'

const BACKEND = 'https://jarvis-backend-4oz6.onrender.com'

const TYPE_META = {
  suggestion:  { label: 'SUGGESTION',  color: '#ff2e51' },
  draft:       { label: 'DRAFT',       color: '#f4f4f2' },
  warning:     { label: 'WARNING',     color: '#f5a623' },
  opportunity: { label: 'OPPORTUNITY', color: '#22c55e' },
}

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
  border: '1px solid rgba(244,244,242,0.15)',
  borderRadius: 20,
  padding: 28,
  fontFamily: 'system-ui, sans-serif',
  boxShadow: '0 24px 60px rgba(0,0,0,0.55), inset 0 1px 0 rgba(244,244,242,0.06)',
  maxHeight: '88vh', display: 'flex', flexDirection: 'column',
}

function QueueCard({ item, onAct, busy }) {
  const meta = TYPE_META[item.type] || TYPE_META.suggestion

  return (
    <div style={{
      background: 'rgba(244,244,242,0.03)',
      border: `1px solid ${item.read ? 'rgba(244,244,242,0.08)' : meta.color + '40'}`,
      borderRadius: 12, padding: '14px 18px', marginBottom: 10,
    }}>
      <div style={{ marginBottom: 6 }}>
        <span style={{
          fontFamily: 'var(--pixel)',
          fontSize: 9, fontWeight: 700, letterSpacing: '0.1em',
          color: meta.color,
          border: `1px solid ${meta.color}66`,
          borderRadius: 4, padding: '2px 6px',
          textTransform: 'uppercase',
        }}>
          {meta.label}
        </span>
      </div>
      <div style={{
        fontFamily: 'var(--pixel)',
        fontSize: 13, color: '#f4f4f2', marginBottom: 6, lineHeight: 1.4,
      }}>
        {item.title}
      </div>
      {item.body && (
        <div style={{ fontSize: 12, color: 'rgba(244,244,242,0.6)', marginBottom: 12, lineHeight: 1.6 }}>
          {item.body}
        </div>
      )}
      {item.action_prompt && (
        <button
          onClick={onAct}
          disabled={busy}
          style={{
            background: 'transparent',
            border: `1px solid ${meta.color}66`,
            borderRadius: 8, padding: '6px 14px',
            color: meta.color, fontSize: 11, fontWeight: 600,
            fontFamily: 'var(--pixel)',
            cursor: busy ? 'default' : 'pointer',
            transition: 'all 150ms ease',
          }}
        >
          {busy ? 'Sending…' : 'Act on this →'}
        </button>
      )}
    </div>
  )
}

export default function MorningQueueModal({ open, onClose, userId, onAct }) {
  const [items, setItems] = useState({ today: [], yesterday: [] })
  const [loading, setLoading] = useState(true)
  const [showYesterday, setShowYesterday] = useState(false)
  const [actingId, setActingId] = useState(null)

  useEffect(() => {
    if (!open || !userId) return
    reload()
    fetch(`${BACKEND}/api/business/morning-queue/read-all?user_id=${encodeURIComponent(userId)}`, { method: 'PATCH' }).catch(() => {})
  }, [open, userId])

  if (!open) return null

  async function reload() {
    setLoading(true)
    try {
      const res = await fetch(`${BACKEND}/api/business/morning-queue?user_id=${encodeURIComponent(userId)}`)
      const data = await res.json()
      setItems({ today: data.today || [], yesterday: data.yesterday || [] })
    } catch (e) {
      console.error('Load morning queue failed', e)
    }
    setLoading(false)
  }

  async function handleAct(item) {
    setActingId(item.id)
    try {
      const res = await fetch(`${BACKEND}/api/business/morning-queue/${item.id}/act?user_id=${encodeURIComponent(userId)}`, {
        method: 'POST',
      })
      const data = await res.json()
      if (data.ok && data.action_prompt) {
        onAct?.(data.action_prompt)
        onClose()
      }
    } catch (e) {
      console.error('Act on morning queue item failed', e)
    }
    setActingId(null)
  }

  const isEmpty = !loading && items.today.length === 0 && items.yesterday.length === 0

  return (
    <div onClick={onClose} style={GLASS_OVERLAY}>
      <div onClick={e => e.stopPropagation()} style={GLASS_PANEL}>
        <div style={{
          fontFamily: 'var(--pixel)',
          fontSize: 10, letterSpacing: '0.12em',
          color: '#ff2e51', marginBottom: 8, textTransform: 'uppercase',
        }}>
          MORNING QUEUE
        </div>
        <div style={{
          fontFamily: 'var(--pixel)',
          fontSize: 13, color: '#f4f4f2', marginBottom: 18, lineHeight: 1.5,
        }}>
          {loading
            ? 'Loading…'
            : isEmpty
              ? 'Inbox zero'
              : `${items.today.length} item${items.today.length === 1 ? '' : 's'} today`}
        </div>

        <div style={{ overflowY: 'auto', flex: 1, paddingRight: 4 }} className="os1-scroll">
          {isEmpty && (
            <div style={{ padding: '36px 0', textAlign: 'center' }}>
              <div className="os1-serif-micro" style={{ fontSize: 11, color: 'rgba(244,244,242,0.45)', lineHeight: 1.8 }}>
                Jarvis works while you sleep.<br />
                First queue lands tomorrow morning.
              </div>
            </div>
          )}

          {items.today.map(item => (
            <QueueCard key={item.id} item={item} busy={actingId === item.id} onAct={() => handleAct(item)} />
          ))}

          {items.yesterday.length > 0 && (
            <>
              <button
                onClick={() => setShowYesterday(s => !s)}
                style={{
                  background: 'transparent', border: 'none',
                  color: 'rgba(244,244,242,0.4)', fontSize: 11,
                  fontFamily: 'var(--pixel)',
                  letterSpacing: '0.06em', textTransform: 'uppercase',
                  cursor: 'pointer', padding: '8px 0', marginBottom: 4,
                }}
              >
                {showYesterday ? '▾' : '▸'} Yesterday ({items.yesterday.length})
              </button>
              {showYesterday && items.yesterday.map(item => (
                <QueueCard key={item.id} item={item} busy={actingId === item.id} onAct={() => handleAct(item)} />
              ))}
            </>
          )}
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 16 }}>
          <button
            onClick={onClose}
            style={{
              background: 'transparent',
              border: '1px solid rgba(244,244,242,0.1)',
              borderRadius: 12, padding: '10px 24px',
              color: 'rgba(244,244,242,0.7)', fontSize: 13,
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
