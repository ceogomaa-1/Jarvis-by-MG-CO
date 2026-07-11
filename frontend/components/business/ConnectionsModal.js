'use client'
import { useEffect, useState, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { X, Search, ChevronDown, ChevronUp, Loader2, Unplug } from 'lucide-react'
import ChannelsPanel from './ChannelsPanel'

import { BACKEND } from '@/lib/backend'

// ── Connector brand icons (colored letter blocks) ─────────────────────────────
const ICON_CONFIG = {
  stripe:       { text: 'S',   bg: '#635BFF', color: '#fff' },
  twilio:       { text: 'T',   bg: '#F22F46', color: '#fff' },
  smtp:         { text: '✉',   bg: '#4A90D9', color: '#fff' },
  elevenlabs:   { text: 'XI',  bg: '#1a1a1a', color: '#fff', border: '1px solid rgba(255,255,255,0.12)' },
  notion:       { text: 'N',   bg: '#ffffff', color: '#000' },
  google:       { text: 'G',   bg: '#4285F4', color: '#fff' },
  canva:        { text: 'C',   bg: '#00C4CC', color: '#fff' },
  gohighlevel:     { text: 'GHL', bg: '#FF6B35', color: '#fff', small: true },
  github:          { text: 'G',   bg: '#24292e', color: '#fff' },
  vercel:          { text: 'V',   bg: '#000000', color: '#fff', border: '1px solid rgba(255,255,255,0.15)' },
  supabase_project: { text: 'S',  bg: '#3ECF8E', color: '#1a1a1a' },
}

function ConnectorIcon({ name, size = 40 }) {
  const cfg = ICON_CONFIG[name] || { text: '?', bg: '#555', color: '#fff' }
  return (
    <div style={{
      width: size, height: size, borderRadius: 10,
      background: cfg.bg,
      border: cfg.border || '1px solid rgba(232,232,232,0.08)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      flexShrink: 0,
      color: cfg.color,
      fontWeight: 700,
      fontSize: cfg.small ? 8 : (cfg.text.length > 1 ? 11 : 15),
      letterSpacing: cfg.small ? '0.04em' : 0,
      fontFamily: 'system-ui, sans-serif',
      userSelect: 'none',
    }}>
      {cfg.text}
    </div>
  )
}

// ── Credential form (API key connectors) ─────────────────────────────────────
function CredentialForm({ manifest, userId, onSave, saving, feedback }) {
  const [values, setValues] = useState(() => {
    const v = {}
    for (const f of (manifest.fields || [])) v[f.name] = ''
    return v
  })

  if (manifest.auth_type === 'oauth') {
    const authUrl = `${BACKEND}/api/business/connections/${manifest.type}/auth?user_id=${encodeURIComponent(userId || '')}`
    return (
      <div style={{ paddingTop: 14 }}>
        {manifest.docs_url && (
          <p style={{ fontSize: 11, color: 'rgba(232,232,232,0.45)', marginBottom: 12, lineHeight: 1.5 }}>
            {manifest.description}{' '}
            <a href={manifest.docs_url} target="_blank" rel="noreferrer" style={{ color: '#2d7ff9' }}>
              Learn more
            </a>
          </p>
        )}
        {feedback && (
          <FeedbackBar ok={feedback.ok} message={feedback.message} />
        )}
        <a
          href={authUrl}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            background: '#2d7ff9', borderRadius: 8, padding: '8px 16px',
            color: '#fff', fontSize: 11, fontWeight: 500,
            textDecoration: 'none', fontFamily: 'system-ui, sans-serif',
            transition: 'opacity 200ms ease',
          }}
        >
          Connect with {manifest.display_name} →
        </a>
      </div>
    )
  }

  return (
    <div style={{ paddingTop: 12 }}>
      {manifest.docs_url && (
        <p style={{ fontSize: 11, color: 'rgba(232,232,232,0.45)', marginBottom: 10, lineHeight: 1.5 }}>
          <a href={manifest.docs_url} target="_blank" rel="noreferrer" style={{ color: '#2d7ff9' }}>
            Where do I get this?
          </a>
        </p>
      )}
      {manifest.status_note && (
        <div style={{
          marginBottom: 10, padding: '6px 10px',
          background: 'rgba(232,232,232,0.03)',
          border: '1px solid rgba(232,232,232,0.08)',
          borderRadius: 7, fontSize: 10, color: 'rgba(232,232,232,0.5)', lineHeight: 1.5,
        }}>
          ℹ️ {manifest.status_note}
        </div>
      )}
      {(manifest.fields || []).map(field => (
        <div key={field.name} style={{ marginBottom: 8 }}>
          <label style={{
            display: 'block', fontSize: 10, fontWeight: 500,
            color: 'rgba(232,232,232,0.6)', marginBottom: 3,
            letterSpacing: '0.04em', textTransform: 'uppercase',
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
              background: 'rgba(232,232,232,0.04)',
              border: '1px solid rgba(232,232,232,0.1)',
              borderRadius: 8, padding: '8px 11px',
              color: '#e8e8e8', fontSize: 12,
              fontFamily: field.type === 'password' ? 'ui-monospace, monospace' : 'system-ui, sans-serif',
              outline: 'none',
            }}
          />
        </div>
      ))}
      {feedback && <FeedbackBar ok={feedback.ok} message={feedback.message} />}
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 10 }}>
        <button
          onClick={() => onSave(values)}
          disabled={saving}
          style={{
            display: 'flex', alignItems: 'center', gap: 6,
            background: saving ? 'rgba(45,127,249,0.5)' : '#2d7ff9',
            border: 'none', borderRadius: 8, padding: '7px 16px',
            color: '#fff', fontSize: 11, fontWeight: 500,
            fontFamily: 'system-ui, sans-serif',
            cursor: saving ? 'not-allowed' : 'pointer', transition: 'all 200ms',
          }}
        >
          {saving && <Loader2 size={11} style={{ animation: 'spin 1s linear infinite' }} />}
          {saving ? 'Testing…' : 'Save & Test'}
        </button>
      </div>
    </div>
  )
}

// ── Connected details panel ───────────────────────────────────────────────────
function ConnectedDetails({ connection, onDisconnect, onTest, testing }) {
  const tested = connection.last_tested_at
    ? new Date(connection.last_tested_at).toLocaleString()
    : null
  const isOk = connection.status === 'active'

  return (
    <div style={{ paddingTop: 12 }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 6,
        padding: '7px 10px', borderRadius: 8,
        background: isOk ? 'rgba(127,176,105,0.06)' : 'rgba(239,68,68,0.06)',
        border: `1px solid ${isOk ? 'rgba(127,176,105,0.15)' : 'rgba(239,68,68,0.15)'}`,
        marginBottom: 10,
      }}>
        <div style={{ width: 6, height: 6, borderRadius: '50%', background: isOk ? '#7fb069' : '#ef4444', flexShrink: 0 }} />
        <span style={{ fontSize: 10, color: isOk ? '#7fb069' : '#ef4444', fontFamily: 'system-ui' }}>
          {isOk ? 'Active' : 'Invalid — credentials need updating'}
        </span>
      </div>
      {tested && (
        <p style={{ fontSize: 10, color: 'rgba(232,232,232,0.35)', marginBottom: 10 }}>
          Last tested: {tested}
          {connection.last_test_result && (
            <span style={{ marginLeft: 6, color: isOk ? 'rgba(127,176,105,0.6)' : 'rgba(239,68,68,0.6)' }}>
              — {connection.last_test_result}
            </span>
          )}
        </p>
      )}
      <div style={{ display: 'flex', gap: 6 }}>
        <button
          onClick={onTest}
          disabled={testing}
          style={{
            display: 'flex', alignItems: 'center', gap: 5,
            background: 'transparent',
            border: '1px solid rgba(232,232,232,0.1)',
            borderRadius: 8, padding: '6px 12px',
            color: 'rgba(232,232,232,0.6)', fontSize: 10,
            fontFamily: 'system-ui', cursor: testing ? 'not-allowed' : 'pointer',
          }}
        >
          {testing ? <Loader2 size={10} style={{ animation: 'spin 1s linear infinite' }} /> : null}
          Test Connection
        </button>
        <button
          onClick={onDisconnect}
          style={{
            display: 'flex', alignItems: 'center', gap: 5,
            background: 'transparent',
            border: '1px solid rgba(239,68,68,0.2)',
            borderRadius: 8, padding: '6px 12px',
            color: 'rgba(239,68,68,0.7)', fontSize: 10,
            fontFamily: 'system-ui', cursor: 'pointer',
          }}
        >
          <Unplug size={10} />
          Disconnect
        </button>
      </div>
    </div>
  )
}

// ── GoHighLevel multi-account (up to 3 accounts per user) ─────────────────────
const GHL_ACCOUNT_SLOTS = [
  { label: 'default', name: 'Account 1' },
  { label: 'account_2', name: 'Account 2' },
  { label: 'account_3', name: 'Account 3' },
]

function GhlAccountSlot({ slot, manifest, userId, account, onChanged }) {
  const [values, setValues] = useState(() => {
    const v = { display_name: account?.display_name || '' }
    for (const f of (manifest.fields || [])) v[f.name] = ''
    return v
  })
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [feedback, setFeedback] = useState(null)

  const isConnected = !!account
  const isActive = account?.status === 'active'

  const handleSave = async () => {
    setSaving(true)
    setFeedback(null)
    try {
      const credentials = {}
      for (const f of (manifest.fields || [])) credentials[f.name] = values[f.name] || ''
      const res = await fetch(`${BACKEND}/api/business/connections`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: userId,
          connector_type: manifest.type,
          credentials,
          display_name: values.display_name || slot.name,
          account_label: slot.label,
        }),
      })
      const data = await res.json()
      if (!res.ok) {
        setFeedback({ ok: false, message: data.detail || 'Save failed.' })
      } else if (data.ok) {
        setFeedback({ ok: true, message: 'Connected and verified.' })
      } else {
        setFeedback({ ok: false, message: data.error || 'Test failed.' })
      }
      await onChanged()
    } catch (e) {
      setFeedback({ ok: false, message: e.message })
    }
    setSaving(false)
  }

  const handleTest = async () => {
    setTesting(true)
    setFeedback(null)
    try {
      const res = await fetch(`${BACKEND}/api/business/connections/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, connector_type: manifest.type, account_label: slot.label }),
      })
      const data = await res.json()
      setFeedback({ ok: data.ok, message: data.ok ? 'Connection verified.' : (data.error || 'Test failed.') })
      await onChanged()
    } catch (e) {
      setFeedback({ ok: false, message: e.message })
    }
    setTesting(false)
  }

  const handleDisconnect = async () => {
    if (!confirm(`Disconnect ${account?.display_name || slot.name}?`)) return
    try {
      await fetch(`${BACKEND}/api/business/connections`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, connector_type: manifest.type, account_label: slot.label }),
      })
      setValues(v => ({ ...v, display_name: '' }))
      setFeedback(null)
      await onChanged()
    } catch (e) {
      console.error('Disconnect failed', e)
    }
  }

  return (
    <div style={{
      marginBottom: 10, padding: '10px 12px', borderRadius: 10,
      background: 'rgba(232,232,232,0.02)',
      border: '1px solid rgba(232,232,232,0.06)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <span style={{
          fontFamily: 'var(--font-pixel), monospace',
          fontSize: 9, letterSpacing: '0.1em', textTransform: 'uppercase',
          color: 'rgba(232,232,232,0.5)',
        }}>
          {slot.name}
        </span>
        {isConnected && (
          <span style={{
            display: 'inline-flex', alignItems: 'center', gap: 4,
            padding: '2px 7px', borderRadius: 99,
            background: isActive ? 'rgba(127,176,105,0.1)' : 'rgba(239,68,68,0.08)',
            border: `1px solid ${isActive ? 'rgba(127,176,105,0.18)' : 'rgba(239,68,68,0.18)'}`,
          }}>
            <div style={{ width: 5, height: 5, borderRadius: '50%', background: isActive ? '#7fb069' : '#ef4444' }} />
            <span style={{
              fontFamily: 'var(--font-pixel), monospace',
              fontSize: 8, letterSpacing: '0.08em', color: isActive ? '#7fb069' : '#ef4444',
            }}>{isActive ? 'Connected' : 'Invalid'}</span>
          </span>
        )}
      </div>

      {isConnected ? (
        <>
          <p style={{ fontSize: 11, color: 'rgba(232,232,232,0.6)', margin: '0 0 8px' }}>
            {account.display_name || slot.name}
          </p>
          {account.last_tested_at && (
            <p style={{ fontSize: 10, color: 'rgba(232,232,232,0.35)', marginBottom: 8 }}>
              Last tested: {new Date(account.last_tested_at).toLocaleString()}
              {account.last_test_result && (
                <span style={{ marginLeft: 6, color: isActive ? 'rgba(127,176,105,0.6)' : 'rgba(239,68,68,0.6)' }}>
                  — {account.last_test_result}
                </span>
              )}
            </p>
          )}
          {feedback && <FeedbackBar ok={feedback.ok} message={feedback.message} />}
          <div style={{ display: 'flex', gap: 6 }}>
            <button
              onClick={handleTest}
              disabled={testing}
              style={{
                display: 'flex', alignItems: 'center', gap: 5,
                background: 'transparent',
                border: '1px solid rgba(232,232,232,0.1)',
                borderRadius: 8, padding: '6px 12px',
                color: 'rgba(232,232,232,0.6)', fontSize: 10,
                fontFamily: 'system-ui', cursor: testing ? 'not-allowed' : 'pointer',
              }}
            >
              {testing ? <Loader2 size={10} style={{ animation: 'spin 1s linear infinite' }} /> : null}
              Test Connection
            </button>
            <button
              onClick={handleDisconnect}
              style={{
                display: 'flex', alignItems: 'center', gap: 5,
                background: 'transparent',
                border: '1px solid rgba(239,68,68,0.2)',
                borderRadius: 8, padding: '6px 12px',
                color: 'rgba(239,68,68,0.7)', fontSize: 10,
                fontFamily: 'system-ui', cursor: 'pointer',
              }}
            >
              <Unplug size={10} />
              Disconnect
            </button>
          </div>
        </>
      ) : (
        <>
          <div style={{ marginBottom: 8 }}>
            <label style={{
              display: 'block', fontSize: 10, fontWeight: 500,
              color: 'rgba(232,232,232,0.6)', marginBottom: 3,
              letterSpacing: '0.04em', textTransform: 'uppercase',
            }}>
              Account Name
            </label>
            <input
              type="text"
              value={values.display_name}
              onChange={e => setValues(v => ({ ...v, display_name: e.target.value }))}
              placeholder={`e.g. "${slot.name} — Main Brokerage"`}
              style={{
                width: '100%', boxSizing: 'border-box',
                background: 'rgba(232,232,232,0.04)',
                border: '1px solid rgba(232,232,232,0.1)',
                borderRadius: 8, padding: '8px 11px',
                color: '#e8e8e8', fontSize: 12,
                fontFamily: 'system-ui, sans-serif', outline: 'none',
              }}
            />
          </div>
          {(manifest.fields || []).map(field => (
            <div key={field.name} style={{ marginBottom: 8 }}>
              <label style={{
                display: 'block', fontSize: 10, fontWeight: 500,
                color: 'rgba(232,232,232,0.6)', marginBottom: 3,
                letterSpacing: '0.04em', textTransform: 'uppercase',
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
                  background: 'rgba(232,232,232,0.04)',
                  border: '1px solid rgba(232,232,232,0.1)',
                  borderRadius: 8, padding: '8px 11px',
                  color: '#e8e8e8', fontSize: 12,
                  fontFamily: field.type === 'password' ? 'ui-monospace, monospace' : 'system-ui, sans-serif',
                  outline: 'none',
                }}
              />
            </div>
          ))}
          {feedback && <FeedbackBar ok={feedback.ok} message={feedback.message} />}
          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <button
              onClick={handleSave}
              disabled={saving}
              style={{
                display: 'flex', alignItems: 'center', gap: 6,
                background: saving ? 'rgba(45,127,249,0.5)' : '#2d7ff9',
                border: 'none', borderRadius: 8, padding: '7px 16px',
                color: '#fff', fontSize: 11, fontWeight: 500,
                fontFamily: 'system-ui, sans-serif',
                cursor: saving ? 'not-allowed' : 'pointer', transition: 'all 200ms',
              }}
            >
              {saving && <Loader2 size={11} style={{ animation: 'spin 1s linear infinite' }} />}
              {saving ? 'Testing…' : 'Save & Test'}
            </button>
          </div>
        </>
      )}
    </div>
  )
}

function GhlAccountsPanel({ manifest, userId, accounts, onChanged }) {
  const byLabel = Object.fromEntries((accounts || []).map(a => [a.account_label, a]))
  return (
    <div style={{ paddingTop: 12 }}>
      {manifest.docs_url && (
        <p style={{ fontSize: 11, color: 'rgba(232,232,232,0.45)', marginBottom: 10, lineHeight: 1.5 }}>
          <a href={manifest.docs_url} target="_blank" rel="noreferrer" style={{ color: '#2d7ff9' }}>
            Where do I get this?
          </a>
        </p>
      )}
      {manifest.status_note && (
        <div style={{
          marginBottom: 10, padding: '6px 10px',
          background: 'rgba(232,232,232,0.03)',
          border: '1px solid rgba(232,232,232,0.08)',
          borderRadius: 7, fontSize: 10, color: 'rgba(232,232,232,0.5)', lineHeight: 1.5,
        }}>
          ℹ️ {manifest.status_note}
        </div>
      )}
      <p style={{ fontSize: 10, color: 'rgba(232,232,232,0.35)', marginBottom: 10, lineHeight: 1.5 }}>
        Connect up to 3 GoHighLevel accounts — Rue will scan all of them for stale leads by default,
        or you can ask it to focus on one ("just check the Main Brokerage account").
      </p>
      {GHL_ACCOUNT_SLOTS.map(slot => (
        <GhlAccountSlot
          key={slot.label}
          slot={slot}
          manifest={manifest}
          userId={userId}
          account={byLabel[slot.label] || null}
          onChanged={onChanged}
        />
      ))}
    </div>
  )
}

function FeedbackBar({ ok, message }) {
  return (
    <div style={{
      marginBottom: 10, padding: '7px 10px', borderRadius: 8,
      background: ok ? 'rgba(127,176,105,0.08)' : 'rgba(239,68,68,0.08)',
      border: `1px solid ${ok ? 'rgba(127,176,105,0.2)' : 'rgba(239,68,68,0.2)'}`,
      color: '#e8e8e8', fontSize: 11, fontFamily: 'system-ui', lineHeight: 1.4,
    }}>
      {ok ? '✅' : '❌'} {message}
    </div>
  )
}

// ── Single connector card ────────────────────────────────────────────────────
function ConnectorCard({ manifest, connection, accounts, onAccountsChanged, userId, onSave, onDelete, onTest, saving, testing, feedback }) {
  const [expanded, setExpanded] = useState(false)
  const isMultiAccount = manifest.type === 'gohighlevel'
  const activeAccounts = isMultiAccount ? (accounts || []).filter(a => a.status === 'active') : []
  const isConnected = isMultiAccount ? (accounts || []).length > 0 : !!connection
  const isActive = isMultiAccount ? activeAccounts.length > 0 : connection?.status === 'active'
  const cardFeedback = feedback?.type === manifest.type ? feedback : null

  return (
    <div style={{
      borderRadius: 14,
      border: isConnected
        ? ' 1px solid rgba(45,127,249,0.18)'
        : '1px solid rgba(232,232,232,0.06)',
      background: isConnected
        ? 'rgba(45,127,249,0.03)'
        : 'rgba(232,232,232,0.015)',
      overflow: 'hidden',
      transition: 'border-color 200ms, background 200ms',
    }}>
      {/* Card header */}
      <div
        style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '14px 16px', cursor: 'pointer' }}
        onClick={() => setExpanded(e => !e)}
      >
        <ConnectorIcon name={manifest.type} size={40} />

        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 2 }}>
            <span style={{
              fontFamily: 'var(--font-pixel), monospace',
              fontSize: 11, letterSpacing: '0.1em',
              color: '#e8e8e8', textTransform: 'uppercase',
            }}>
              {manifest.display_name}
            </span>
            {isMultiAccount && isConnected && (
              <span style={{
                display: 'inline-flex', alignItems: 'center', gap: 4,
                padding: '2px 7px', borderRadius: 99,
                background: isActive ? 'rgba(127,176,105,0.1)' : 'rgba(239,68,68,0.08)',
                border: `1px solid ${isActive ? 'rgba(127,176,105,0.18)' : 'rgba(239,68,68,0.18)'}`,
              }}>
                <div style={{ width: 5, height: 5, borderRadius: '50%', background: isActive ? '#7fb069' : '#ef4444' }} />
                <span style={{
                  fontFamily: 'var(--font-pixel), monospace',
                  fontSize: 8, letterSpacing: '0.08em', color: isActive ? '#7fb069' : '#ef4444',
                }}>{activeAccounts.length}/3 connected</span>
              </span>
            )}
            {!isMultiAccount && isConnected && isActive && (
              <span style={{
                display: 'inline-flex', alignItems: 'center', gap: 4,
                padding: '2px 7px', borderRadius: 99,
                background: 'rgba(127,176,105,0.1)',
                border: '1px solid rgba(127,176,105,0.18)',
              }}>
                <div style={{ width: 5, height: 5, borderRadius: '50%', background: '#7fb069' }} />
                <span style={{
                  fontFamily: 'var(--font-pixel), monospace',
                  fontSize: 8, letterSpacing: '0.08em', color: '#7fb069',
                }}>Connected</span>
              </span>
            )}
            {!isMultiAccount && isConnected && !isActive && (
              <span style={{
                display: 'inline-flex', alignItems: 'center', gap: 4,
                padding: '2px 7px', borderRadius: 99,
                background: 'rgba(239,68,68,0.08)',
                border: '1px solid rgba(239,68,68,0.18)',
              }}>
                <div style={{ width: 5, height: 5, borderRadius: '50%', background: '#ef4444' }} />
                <span style={{
                  fontFamily: 'var(--font-pixel), monospace',
                  fontSize: 8, letterSpacing: '0.08em', color: '#ef4444',
                }}>Invalid</span>
              </span>
            )}
          </div>
          <p style={{ fontSize: 11, color: 'rgba(232,232,232,0.38)', margin: 0, lineHeight: 1.4, fontFamily: 'system-ui' }}>
            {manifest.description}
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
          {!isConnected && (
            <button
              onClick={(e) => { e.stopPropagation(); setExpanded(true) }}
              style={{
                background: '#2d7ff9', border: 'none', borderRadius: 8,
                padding: '6px 13px',
                fontFamily: 'var(--font-pixel), monospace',
                fontSize: 9, letterSpacing: '0.1em', textTransform: 'uppercase',
                color: '#0a0a0a', cursor: 'pointer', transition: 'opacity 200ms',
              }}
            >
              Connect
            </button>
          )}
          <div style={{ color: 'rgba(232,232,232,0.3)' }}>
            {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </div>
        </div>
      </div>

      {/* Expanded panel */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            key="panel"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: 'easeInOut' }}
            style={{ overflow: 'hidden' }}
          >
            <div style={{
              padding: '0 16px 14px',
              borderTop: '1px solid rgba(232,232,232,0.04)',
            }}>
              {isMultiAccount ? (
                <GhlAccountsPanel
                  manifest={manifest}
                  userId={userId}
                  accounts={accounts}
                  onChanged={onAccountsChanged}
                />
              ) : isConnected ? (
                <ConnectedDetails
                  connection={connection}
                  onDisconnect={() => onDelete(manifest.type)}
                  onTest={() => onTest(manifest.type)}
                  testing={testing === manifest.type}
                />
              ) : (
                <CredentialForm
                  manifest={manifest}
                  userId={userId}
                  onSave={(vals) => onSave(manifest, vals)}
                  saving={saving === manifest.type}
                  feedback={cardFeedback}
                />
              )}
              {cardFeedback && isConnected && !isMultiAccount && (
                <div style={{ marginTop: 10 }}>
                  <FeedbackBar ok={cardFeedback.ok} message={cardFeedback.message} />
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// ── Main modal ───────────────────────────────────────────────────────────────
export default function ConnectionsModal({ open, onClose, userId }) {
  const [manifests, setManifests] = useState([])
  const [userConnections, setUserConnections] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(null)    // connector_type or null
  const [testing, setTesting] = useState(null)  // connector_type or null
  const [feedback, setFeedback] = useState(null)
  const [searchQuery, setSearchQuery] = useState('')

  const loadAll = useCallback(async () => {
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
  }, [userId])

  useEffect(() => {
    if (open && userId) loadAll()
  }, [open, userId, loadAll])

  // Handle OAuth callback params
  useEffect(() => {
    if (!open) return
    const params = new URLSearchParams(window.location.search)
    const connected = params.get('connector_connected')
    const error = params.get('connector_error')
    if (connected) {
      setFeedback({ type: connected, ok: true, message: `${connected} connected successfully.` })
      const url = new URL(window.location.href)
      url.searchParams.delete('connector_connected')
      window.history.replaceState({}, '', url.toString())
      loadAll()
    } else if (error) {
      setFeedback({ type: 'google', ok: false, message: `OAuth error: ${error}` })
      const url = new URL(window.location.href)
      url.searchParams.delete('connector_error')
      window.history.replaceState({}, '', url.toString())
    }
  }, [open, loadAll])

  if (!open) return null

  const connByType = Object.fromEntries(userConnections.map(c => [c.connector_type, c]))

  const filteredManifests = searchQuery.trim()
    ? manifests.filter(m =>
        m.display_name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
        m.description?.toLowerCase().includes(searchQuery.toLowerCase()) ||
        m.type?.toLowerCase().includes(searchQuery.toLowerCase())
      )
    : manifests

  const handleSave = async (manifest, values) => {
    setSaving(manifest.type)
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
      } else {
        setFeedback({ type: manifest.type, ok: false, message: data.error || 'Test failed.' })
      }
      await loadAll()
    } catch (e) {
      setFeedback({ type: manifest.type, ok: false, message: e.message })
    }
    setSaving(null)
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

  const handleTest = async (connector_type) => {
    setTesting(connector_type)
    setFeedback(null)
    try {
      const res = await fetch(`${BACKEND}/api/business/connections/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, connector_type }),
      })
      const data = await res.json()
      setFeedback({
        type: connector_type,
        ok: data.ok,
        message: data.ok ? 'Connection verified.' : (data.error || 'Test failed.'),
      })
      await loadAll()
    } catch (e) {
      setFeedback({ type: connector_type, ok: false, message: e.message })
    }
    setTesting(null)
  }

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0,
        background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(10px)', WebkitBackdropFilter: 'blur(10px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: 1000, padding: '20px',
      }}
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.97, y: 12 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.97, y: 12 }}
        transition={{ duration: 0.25, ease: 'easeOut' }}
        onClick={e => e.stopPropagation()}
        style={{
          width: '100%', maxWidth: 760,
          maxHeight: '88vh',
          background: 'rgba(12,12,15,0.9)',
          backdropFilter: 'blur(28px) saturate(180%)',
          WebkitBackdropFilter: 'blur(28px) saturate(180%)',
          border: '1px solid rgba(232,232,232,0.1)',
          borderRadius: 20,
          boxShadow: '0 30px 70px rgba(0,0,0,0.6), inset 0 1px 0 rgba(232,232,232,0.05)',
          display: 'flex', flexDirection: 'column',
          overflow: 'hidden',
          fontFamily: 'system-ui, sans-serif',
        }}
      >
        {/* Header */}
        <div style={{
          padding: '20px 22px 16px',
          borderBottom: '1px solid rgba(232,232,232,0.06)',
          flexShrink: 0,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
            <div>
              <div style={{
                fontFamily: 'var(--font-pixel), monospace',
                fontSize: 10, letterSpacing: '0.14em',
                color: '#2d7ff9', textTransform: 'uppercase', marginBottom: 4,
              }}>
                Connections
              </div>
              <p style={{ fontSize: 11, color: 'rgba(232,232,232,0.4)', margin: 0, lineHeight: 1.4 }}>
                Wire Rue into your real systems. All credentials are encrypted at rest.
              </p>
            </div>
            <button
              onClick={onClose}
              style={{
                background: 'rgba(232,232,232,0.05)',
                border: '1px solid rgba(232,232,232,0.08)',
                borderRadius: 8, padding: 6, cursor: 'pointer',
                color: 'rgba(232,232,232,0.5)', display: 'flex', alignItems: 'center',
                transition: 'all 200ms',
              }}
            >
              <X size={16} />
            </button>
          </div>

          {/* Search */}
          <div style={{ position: 'relative' }}>
            <Search size={13} style={{
              position: 'absolute', left: 11, top: '50%', transform: 'translateY(-50%)',
              color: 'rgba(232,232,232,0.25)', pointerEvents: 'none',
            }} />
            <input
              type="text"
              placeholder="Search connectors…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{
                width: '100%', boxSizing: 'border-box',
                background: 'rgba(232,232,232,0.03)',
                border: '1px solid rgba(232,232,232,0.07)',
                borderRadius: 10, padding: '8px 12px 8px 32px',
                color: '#e8e8e8', fontSize: 12,
                fontFamily: 'system-ui', outline: 'none',
                transition: 'border-color 200ms',
              }}
              onFocus={e => { e.target.style.borderColor = 'rgba(232,232,232,0.15)' }}
              onBlur={e => { e.target.style.borderColor = 'rgba(232,232,232,0.07)' }}
            />
          </div>
        </div>

        {/* Card grid */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '16px 22px 20px' }}>
          {/* Messaging channels — chat the OS1 brain from Telegram (subscribers only) */}
          <ChannelsPanel userId={userId} />
          {loading ? (
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              padding: 48, color: 'rgba(232,232,232,0.3)', gap: 10,
            }}>
              <Loader2 size={16} style={{ animation: 'spin 1s linear infinite' }} />
              <span style={{ fontSize: 12 }}>Loading connectors…</span>
            </div>
          ) : filteredManifests.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 40, color: 'rgba(232,232,232,0.3)', fontSize: 12 }}>
              No connectors match "{searchQuery}"
            </div>
          ) : (
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
              gap: 10,
            }}>
              {filteredManifests.map(manifest => (
                <ConnectorCard
                  key={manifest.type}
                  manifest={manifest}
                  connection={connByType[manifest.type] || null}
                  accounts={manifest.type === 'gohighlevel' ? userConnections.filter(c => c.connector_type === 'gohighlevel') : undefined}
                  onAccountsChanged={loadAll}
                  userId={userId}
                  onSave={handleSave}
                  onDelete={handleDelete}
                  onTest={handleTest}
                  saving={saving}
                  testing={testing}
                  feedback={feedback}
                />
              ))}
            </div>
          )}
        </div>
      </motion.div>

      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
    </div>
  )
}
