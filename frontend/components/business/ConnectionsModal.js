'use client'
import { useEffect, useState } from 'react'

const BACKEND = 'https://jarvis-backend-4oz6.onrender.com'

function StatusBadge({ status, lastResult }) {
  const styles = {
    active: { bg: 'rgba(34,197,94,0.12)', color: '#22c55e', label: '● Active' },
    invalid: { bg: 'rgba(239,68,68,0.12)', color: '#ef4444', label: '● Invalid' },
    disabled: { bg: 'rgba(156,163,175,0.12)', color: '#9ca3af', label: '● Disabled' },
    none: { bg: 'rgba(243,234,217,0.04)', color: 'rgba(243,234,217,0.5)', label: '○ Not connected' },
  }
  const s = styles[status] || styles.none
  return (
    <span
      title={lastResult || ''}
      style={{
        background: s.bg, color: s.color,
        fontSize: 10, fontWeight: 600, letterSpacing: '0.06em',
        padding: '3px 8px', borderRadius: 6, textTransform: 'uppercase',
      }}
    >
      {s.label}
    </span>
  )
}

function ConnectForm({ manifest, onSave, onCancel, saving }) {
  const [values, setValues] = useState(() => {
    const v = {}
    for (const f of manifest.fields) v[f.name] = ''
    return v
  })

  return (
    <div style={{
      background: 'rgba(243,234,217,0.03)',
      border: '1px solid rgba(243,234,217,0.1)',
      borderRadius: 10, padding: '16px 18px', marginTop: 8,
    }}>
      <div style={{ fontSize: 12, color: 'rgba(243,234,217,0.6)', marginBottom: 12 }}>
        {manifest.description}{' '}
        {manifest.docs_url && (
          <a
            href={manifest.docs_url} target="_blank" rel="noreferrer"
            style={{ color: '#c84b31', textDecoration: 'underline' }}
          >
            Where do I get this?
          </a>
        )}
      </div>

      {manifest.fields.map(field => (
        <div key={field.name} style={{ marginBottom: 10 }}>
          <label style={{
            display: 'block', fontSize: 11, fontWeight: 500,
            color: 'rgba(243,234,217,0.7)', marginBottom: 4,
          }}>
            {field.label}{field.required !== false ? ' *' : ''}
          </label>
          <input
            type={field.type === 'password' ? 'password' : field.type === 'number' ? 'number' : 'text'}
            value={values[field.name]}
            onChange={e => setValues(v => ({ ...v, [field.name]: e.target.value }))}
            placeholder={field.placeholder || ''}
            style={{
              width: '100%', boxSizing: 'border-box',
              background: 'rgba(243,234,217,0.04)',
              border: '1px solid rgba(243,234,217,0.12)',
              borderRadius: 7, padding: '9px 12px',
              color: '#f3ead9', fontSize: 13,
              fontFamily: field.type === 'password' ? 'ui-monospace, monospace' : 'system-ui, sans-serif',
              outline: 'none',
            }}
          />
        </div>
      ))}

      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 12 }}>
        <button
          onClick={onCancel}
          disabled={saving}
          style={{
            background: 'transparent',
            border: '1px solid rgba(243,234,217,0.15)',
            borderRadius: 7, padding: '7px 14px',
            color: 'rgba(243,234,217,0.7)', fontSize: 12,
            fontFamily: 'system-ui, sans-serif', cursor: saving ? 'default' : 'pointer',
          }}
        >
          Cancel
        </button>
        <button
          onClick={() => onSave(values)}
          disabled={saving}
          style={{
            background: saving ? 'rgba(200,75,49,0.5)' : '#c84b31',
            border: 'none', borderRadius: 7, padding: '7px 16px',
            color: 'white', fontSize: 12, fontWeight: 500,
            fontFamily: 'system-ui, sans-serif',
            cursor: saving ? 'default' : 'pointer',
          }}
        >
          {saving ? 'Testing…' : 'Save & Test'}
        </button>
      </div>
    </div>
  )
}

export default function ConnectionsModal({ open, onClose, userId }) {
  const [manifests, setManifests] = useState([])
  const [userConnections, setUserConnections] = useState([])
  const [loading, setLoading] = useState(true)
  const [expandedType, setExpandedType] = useState(null)
  const [saving, setSaving] = useState(false)
  const [feedback, setFeedback] = useState(null)

  const loadAll = async () => {
    setLoading(true)
    try {
      const [mRes, cRes] = await Promise.all([
        fetch(`${BACKEND}/api/business/connections/manifests`),
        fetch(`${BACKEND}/api/business/connections?user_id=${encodeURIComponent(userId || '')}`),
      ])
      const m = await mRes.json()
      const c = await cRes.json()
      setManifests(m.connectors || [])
      setUserConnections(c.connections || [])
    } catch (e) {
      console.error('Load connections failed', e)
    }
    setLoading(false)
  }

  useEffect(() => {
    if (open && userId) loadAll()
  }, [open, userId])

  if (!open) return null

  const connByType = Object.fromEntries(userConnections.map(c => [c.connector_type, c]))

  const handleSave = async (manifest, values) => {
    setSaving(true)
    setFeedback(null)
    try {
      const res = await fetch(`${BACKEND}/api/business/connections`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: userId,
          connector_type: manifest.type,
          credentials: values,
          display_name: manifest.display_name,
        }),
      })
      const data = await res.json()
      if (data.ok) {
        setFeedback({ type: manifest.type, ok: true, message: 'Connected and verified.' })
        setExpandedType(null)
      } else {
        setFeedback({ type: manifest.type, ok: false, message: data.error || 'Test failed.' })
      }
      await loadAll()
    } catch (e) {
      setFeedback({ type: manifest.type, ok: false, message: e.message })
    }
    setSaving(false)
  }

  const handleDelete = async (connector_type) => {
    if (!confirm(`Disconnect ${connector_type}? Sub-agents will no longer be able to execute through this service.`)) return
    try {
      await fetch(`${BACKEND}/api/business/connections`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, connector_type }),
      })
      await loadAll()
    } catch (e) {
      console.error('Delete failed', e)
    }
  }

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
          width: '100%', maxWidth: 620, margin: '0 20px',
          background: 'rgba(15, 15, 18, 0.55)',
          backdropFilter: 'blur(28px) saturate(180%)',
          WebkitBackdropFilter: 'blur(28px) saturate(180%)',
          border: '1px solid rgba(243,234,217,0.15)',
          borderRadius: 20, padding: 28,
          fontFamily: 'system-ui, sans-serif',
          boxShadow: '0 24px 60px rgba(0,0,0,0.55), inset 0 1px 0 rgba(243,234,217,0.06)',
          maxHeight: '88vh', display: 'flex', flexDirection: 'column',
        }}
      >
        <div style={{
          fontSize: 11, fontWeight: 600, letterSpacing: '0.12em',
          color: '#c84b31', marginBottom: 6, textTransform: 'uppercase',
        }}>
          🔌 CONNECTIONS
        </div>
        <div style={{ fontSize: 18, color: '#f3ead9', marginBottom: 6, fontWeight: 600 }}>
          Wire Jarvis into your real systems
        </div>
        <div style={{ fontSize: 12, color: 'rgba(243,234,217,0.5)', marginBottom: 16, lineHeight: 1.5 }}>
          Each connection unlocks new capabilities — Jarvis can read your real data and execute actions on your behalf. All credentials are encrypted at rest. You can disconnect any time.
        </div>

        <div style={{ overflowY: 'auto', flex: 1, paddingRight: 4 }}>
          {loading ? (
            <div style={{ color: 'rgba(243,234,217,0.5)', fontSize: 13, padding: 12 }}>Loading…</div>
          ) : manifests.map(manifest => {
            const existing = connByType[manifest.type]
            const status = existing?.status || 'none'
            const expanded = expandedType === manifest.type
            const fb = feedback?.type === manifest.type ? feedback : null

            return (
              <div
                key={manifest.type}
                style={{
                  border: '1px solid rgba(243,234,217,0.08)',
                  borderRadius: 10, padding: '14px 16px',
                  marginBottom: 10,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <div style={{ fontSize: 14, color: '#f3ead9', fontWeight: 600 }}>
                        {manifest.display_name}
                      </div>
                      <StatusBadge status={status} lastResult={existing?.last_test_result} />
                    </div>
                    <div style={{ fontSize: 11, color: 'rgba(243,234,217,0.5)', marginTop: 3 }}>
                      {manifest.description}
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 6, flexShrink: 0, marginLeft: 12 }}>
                    {existing && (
                      <button
                        onClick={() => handleDelete(manifest.type)}
                        style={{
                          background: 'transparent',
                          border: '1px solid rgba(239,68,68,0.3)',
                          borderRadius: 6, padding: '5px 10px',
                          color: '#ef4444', fontSize: 11,
                          cursor: 'pointer',
                        }}
                      >
                        Disconnect
                      </button>
                    )}
                    <button
                      onClick={() => setExpandedType(expanded ? null : manifest.type)}
                      style={{
                        background: existing ? 'rgba(243,234,217,0.04)' : '#c84b31',
                        border: existing ? '1px solid rgba(243,234,217,0.12)' : 'none',
                        borderRadius: 6, padding: '5px 12px',
                        color: existing ? '#f3ead9' : 'white',
                        fontSize: 11, fontWeight: 500, cursor: 'pointer',
                      }}
                    >
                      {expanded ? 'Close' : existing ? 'Edit' : 'Connect'}
                    </button>
                  </div>
                </div>

                {fb && (
                  <div style={{
                    marginTop: 10, padding: '8px 12px',
                    background: fb.ok ? 'rgba(34,197,94,0.08)' : 'rgba(239,68,68,0.08)',
                    border: `1px solid ${fb.ok ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)'}`,
                    borderRadius: 7, color: '#f3ead9', fontSize: 12,
                  }}>
                    {fb.ok ? '✅' : '❌'} {fb.message}
                  </div>
                )}

                {expanded && (
                  <ConnectForm
                    manifest={manifest}
                    onSave={vals => handleSave(manifest, vals)}
                    onCancel={() => { setExpandedType(null); setFeedback(null) }}
                    saving={saving}
                  />
                )}
              </div>
            )
          })}
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 16 }}>
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
