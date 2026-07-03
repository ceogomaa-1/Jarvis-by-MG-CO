'use client'
import { useState } from 'react'
import AIThinkingBlock from '@/components/ui/ai-thinking-block'

const BACKEND = 'https://jarvis-backend-4oz6.onrender.com'

export default function RefineModal({ creationId, userId, kind, onClose, onRefined }) {
  const [instruction, setInstruction] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [progress, setProgress] = useState('')
  const isWebsite = kind === 'standalone'

  async function handleRefine() {
    if (!instruction.trim() || loading) return
    setLoading(true)
    setError('')
    setProgress(isWebsite ? 'Mapping your instruction onto the saved HTML…' : 'Refining the saved artifact…')

    try {
      const res = await fetch(`${BACKEND}/api/business/create/${creationId}/refine`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ instruction: instruction.trim(), user_id: userId || '' }),
      })
      if (!res.ok || !res.body) {
        throw new Error((await res.text()) || 'Refinement failed')
      }
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
            if (ev.type === 'html_artifact') {
              refined = {
                html: ev.html,
                summary: ev.summary,
                deploymentStatus: ev.deployment_status,
                liveUrl: ev.live_url,
              }
            }
            if (ev.type === 'creation_progress') setProgress(ev.message)
            if (ev.type === 'error') setError(ev.value)
          } catch {}
        }
      }

      if (refined) {
        onRefined(refined)
        onClose()
      }
    } catch (err) {
      setError(err?.message || 'Refinement failed. Please try again.')
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
          border: '1px solid rgba(236,230,217,0.15)',
          borderRadius: 20, padding: '28px 32px',
          maxWidth: 520, width: '100%',
          boxShadow: '0 24px 60px rgba(0,0,0,0.55), inset 0 1px 0 rgba(236,230,217,0.06)',
        }}
        onClick={e => e.stopPropagation()}
      >
        <div style={{
          fontSize: 11, fontWeight: 600, letterSpacing: '0.1em',
          color: '#cf8a5b', marginBottom: 8, textTransform: 'uppercase',
        }}>
          {isWebsite ? 'Surgical Website Edit' : 'Refine Artifact'}
        </div>
        <div style={{ fontSize: 18, fontWeight: 600, color: '#ece6d9', marginBottom: 18 }}>
          {isWebsite ? 'What exactly should change?' : 'What should I improve?'}
        </div>

        <textarea
          value={instruction}
          onChange={e => setInstruction(e.target.value)}
          placeholder={isWebsite
            ? '"Replace the hero headline with…" or "Make only the Book a Table button blue"'
            : '"Make the email shorter and more punchy" or "Add a discount angle to the campaign"'}
          disabled={loading}
          rows={4}
          style={{
            width: '100%', boxSizing: 'border-box',
            background: 'rgba(236,230,217,0.04)',
            border: '1px solid rgba(236,230,217,0.12)',
            borderRadius: 8, padding: '12px 14px',
            color: '#ece6d9', fontFamily: 'system-ui, sans-serif',
            fontSize: 14, outline: 'none', resize: 'vertical',
            marginBottom: error ? 10 : 20,
            transition: 'border-color 200ms',
          }}
          onFocus={e => (e.target.style.borderColor = 'rgba(207,138,91,0.4)')}
          onBlur={e => (e.target.style.borderColor = 'rgba(236,230,217,0.12)')}
        />

        {error && (
          <div style={{ color: '#ef4444', fontSize: 13, marginBottom: 16 }}>{error}</div>
        )}

        {loading && (
          <AIThinkingBlock
            label={isWebsite ? 'Editing without touching the rest' : 'Refining the artifact'}
            status={progress}
            mode={isWebsite ? 'edit' : 'build'}
            className="mb-4"
          />
        )}

        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
          <button
            onClick={onClose}
            disabled={loading}
            style={{
              background: 'transparent',
              border: '1px solid rgba(236,230,217,0.12)',
              borderRadius: 8, padding: '10px 20px',
              color: 'rgba(236,230,217,0.6)',
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
              background: instruction.trim() && !loading ? '#cf8a5b' : 'rgba(207,138,91,0.12)',
              border: 'none', borderRadius: 8, padding: '10px 24px',
              color: instruction.trim() && !loading ? 'white' : 'rgba(207,138,91,0.4)',
              cursor: instruction.trim() && !loading ? 'pointer' : 'default',
              fontFamily: 'system-ui, sans-serif', fontSize: 13, fontWeight: 500,
              transition: 'all 200ms ease',
            }}
          >
            {loading ? (isWebsite ? 'Editing…' : 'Refining…') : (isWebsite ? 'Apply edit' : 'Refine')}
          </button>
        </div>
      </div>
    </div>
  )
}
