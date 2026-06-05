'use client'
import { useEffect, useRef, useState } from 'react'

const BACKEND = 'https://jarvis-backend-4oz6.onrender.com'

const PLACEHOLDER = `Paste your current numbers however you track them. Examples:

AR over 90 days: $84,000
Cash on hand: $42,000
Trust account reconciled today, zero variance
Conversion rate this week: 19%
Foot traffic down 8% vs same week last year
Sell-through on Q2 buy: 47% at week 8
Top SKU stock: 3 units (concerning)`

export default function MetricsModal({ open, onClose, userId }) {
  const [text, setText] = useState('')
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [savedAt, setSavedAt] = useState(null)
  const inputRef = useRef(null)

  useEffect(() => {
    if (!open || !userId) return
    setLoading(true)
    fetch(`${BACKEND}/api/business/metrics?user_id=${encodeURIComponent(userId)}`)
      .then(r => r.json())
      .then(d => {
        setText(d.metrics_text || '')
        setSavedAt(d.updated_at || null)
      })
      .catch(() => {})
      .finally(() => {
        setLoading(false)
        setTimeout(() => inputRef.current?.focus(), 80)
      })
  }, [open, userId])

  if (!open) return null

  const handleSave = async () => {
    if (!userId) return
    setSaving(true)
    try {
      const res = await fetch(`${BACKEND}/api/business/metrics`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, metrics_text: text }),
      })
      if (res.ok) {
        setSavedAt(new Date().toISOString())
        setTimeout(onClose, 600)
      }
    } catch (e) {
      console.error('Save metrics failed', e)
    }
    setSaving(false)
  }

  const formatTimestamp = (iso) => {
    if (!iso) return null
    try {
      return new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
    } catch {
      return null
    }
  }

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0,
        background: 'rgba(0,0,0,0.65)', backdropFilter: 'blur(8px)',
        WebkitBackdropFilter: 'blur(8px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: 1000,
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          width: '100%', maxWidth: 640, margin: '0 20px',
          background: 'rgba(15, 15, 18, 0.55)',
          backdropFilter: 'blur(28px) saturate(180%)',
          WebkitBackdropFilter: 'blur(28px) saturate(180%)',
          border: '1px solid rgba(243,234,217,0.15)',
          borderRadius: 20, padding: 28,
          fontFamily: 'system-ui, sans-serif',
          boxShadow: '0 24px 60px rgba(0,0,0,0.55), inset 0 1px 0 rgba(243,234,217,0.06)',
          display: 'flex', flexDirection: 'column',
          maxHeight: '88vh',
        }}
      >
        <div style={{
          fontFamily: 'var(--font-arcade), monospace',
          fontSize: 10, letterSpacing: '0.12em',
          color: '#c84b31', marginBottom: 8, textTransform: 'uppercase',
        }}>
          YOUR NUMBERS
        </div>
        <div style={{
          fontFamily: 'var(--font-arcade), monospace',
          fontSize: 13, color: '#f3ead9', marginBottom: 6, lineHeight: 1.5,
        }}>
          Update your current metrics
        </div>
        <div style={{ fontSize: 12, color: 'rgba(243,234,217,0.5)', marginBottom: 16, lineHeight: 1.5 }}>
          Paste your current numbers in whatever way you track them. Jarvis evaluates these against your industry risk flags every morning at 6 AM.
          {savedAt && (
            <span style={{ display: 'block', marginTop: 6, color: 'rgba(243,234,217,0.4)' }}>
              Last updated: {formatTimestamp(savedAt)}
            </span>
          )}
        </div>

        <textarea
          ref={inputRef}
          value={text}
          onChange={e => setText(e.target.value)}
          disabled={loading}
          placeholder={loading ? 'Loading...' : PLACEHOLDER}
          rows={14}
          style={{
            width: '100%', boxSizing: 'border-box',
            background: 'rgba(243,234,217,0.04)',
            border: '1px solid rgba(243,234,217,0.12)',
            borderRadius: 10, padding: '14px 16px',
            color: '#f3ead9',
            fontFamily: 'ui-monospace, "SF Mono", Menlo, monospace',
            fontSize: 13, lineHeight: 1.6, outline: 'none', resize: 'vertical',
            flex: 1, minHeight: 240,
          }}
        />

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 16 }}>
          <button
            onClick={onClose}
            disabled={saving}
            style={{
              background: 'transparent',
              border: '1px solid rgba(243,234,217,0.1)',
              borderRadius: 12, padding: '10px 24px',
              color: 'rgba(243,234,217,0.7)', fontSize: 13,
              fontFamily: 'system-ui, sans-serif', cursor: saving ? 'default' : 'pointer',
              transition: 'all 200ms ease',
            }}
          >
            Close
          </button>
          <button
            onClick={handleSave}
            disabled={saving || loading}
            style={{
              background: saving ? 'rgba(200,75,49,0.4)' : '#c84b31',
              border: 'none', borderRadius: 12, padding: '10px 24px',
              color: '#0a0a0a', fontSize: 13, fontWeight: 500,
              fontFamily: 'system-ui, sans-serif',
              cursor: saving ? 'default' : 'pointer',
              transition: 'background 200ms ease',
            }}
          >
            {saving ? 'Saving...' : 'Save numbers'}
          </button>
        </div>
      </div>
    </div>
  )
}
