'use client'
import { useState } from 'react'

const BACKEND = 'https://jarvis-backend-4oz6.onrender.com'

export default function RefineModal({ creationId, onClose, onRefined }) {
  const [instruction, setInstruction] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleRefine() {
    if (!instruction.trim() || loading) return
    setLoading(true)
    setError('')

    try {
      const res = await fetch(`${BACKEND}/api/business/create/${creationId}/refine`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ instruction: instruction.trim() }),
      })
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buf = ''
      let refined = null

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
            if (ev.type === 'artifact') refined = ev.content
            if (ev.type === 'error') setError(ev.value)
          } catch {}
        }
      }

      if (refined) {
        onRefined(refined)
        onClose()
      }
    } catch {
      setError('Refinement failed. Please try again.')
    }

    setLoading(false)
  }

  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 1000,
        background: 'rgba(0,0,0,0.72)', backdropFilter: 'blur(4px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 20,
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: 'rgba(15, 15, 18, 0.55)',
          backdropFilter: 'blur(28px) saturate(180%)',
          WebkitBackdropFilter: 'blur(28px) saturate(180%)',
          border: '1px solid rgba(232,232,232,0.15)',
          borderRadius: 20, padding: '28px 32px',
          maxWidth: 520, width: '100%',
          boxShadow: '0 24px 60px rgba(0,0,0,0.55), inset 0 1px 0 rgba(232,232,232,0.06)',
        }}
        onClick={e => e.stopPropagation()}
      >
        <div style={{
          fontSize: 11, fontWeight: 600, letterSpacing: '0.1em',
          color: '#2d7ff9', marginBottom: 8, textTransform: 'uppercase',
        }}>
          Refine Artifact
        </div>
        <div style={{ fontSize: 18, fontWeight: 600, color: '#e8e8e8', marginBottom: 18 }}>
          What should I improve?
        </div>

        <textarea
          value={instruction}
          onChange={e => setInstruction(e.target.value)}
          placeholder='"Make the email shorter and more punchy" or "Add a discount angle to the campaign"'
          disabled={loading}
          rows={4}
          style={{
            width: '100%', boxSizing: 'border-box',
            background: 'rgba(232,232,232,0.04)',
            border: '1px solid rgba(232,232,232,0.12)',
            borderRadius: 8, padding: '12px 14px',
            color: '#e8e8e8', fontFamily: 'system-ui, sans-serif',
            fontSize: 14, outline: 'none', resize: 'vertical',
            marginBottom: error ? 10 : 20,
            transition: 'border-color 200ms',
          }}
          onFocus={e => (e.target.style.borderColor = 'rgba(45,127,249,0.4)')}
          onBlur={e => (e.target.style.borderColor = 'rgba(232,232,232,0.12)')}
        />

        {error && (
          <div style={{ color: '#ef4444', fontSize: 13, marginBottom: 16 }}>{error}</div>
        )}

        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
          <button
            onClick={onClose}
            disabled={loading}
            style={{
              background: 'transparent',
              border: '1px solid rgba(232,232,232,0.12)',
              borderRadius: 8, padding: '10px 20px',
              color: 'rgba(232,232,232,0.6)',
              cursor: 'pointer', fontFamily: 'system-ui, sans-serif',
              fontSize: 13, fontWeight: 500,
            }}
          >
            Cancel
          </button>
          <button
            onClick={handleRefine}
            disabled={!instruction.trim() || loading}
            style={{
              background: instruction.trim() && !loading ? '#2d7ff9' : 'rgba(45,127,249,0.12)',
              border: 'none', borderRadius: 8, padding: '10px 24px',
              color: instruction.trim() && !loading ? 'white' : 'rgba(45,127,249,0.4)',
              cursor: instruction.trim() && !loading ? 'pointer' : 'default',
              fontFamily: 'system-ui, sans-serif', fontSize: 13, fontWeight: 500,
              transition: 'all 200ms ease',
            }}
          >
            {loading ? 'Refining...' : 'Refine'}
          </button>
        </div>
      </div>
    </div>
  )
}
