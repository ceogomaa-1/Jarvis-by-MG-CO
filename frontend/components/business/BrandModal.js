'use client'
import { useEffect, useState } from 'react'

const BACKEND = 'https://jarvis-backend-4oz6.onrender.com'

function Field({ label, children }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <label style={{
        display: 'block', fontSize: 11, fontWeight: 500,
        color: 'rgba(243,234,217,0.7)', marginBottom: 5,
        textTransform: 'uppercase', letterSpacing: '0.06em',
      }}>
        {label}
      </label>
      {children}
    </div>
  )
}

const inputStyle = {
  width: '100%', boxSizing: 'border-box',
  background: 'rgba(243,234,217,0.04)',
  border: '1px solid rgba(243,234,217,0.12)',
  borderRadius: 7, padding: '9px 12px',
  color: '#f3ead9', fontSize: 13,
  fontFamily: 'system-ui, sans-serif', outline: 'none',
}

export default function BrandModal({ open, onClose, userId }) {
  const [form, setForm] = useState({
    display_name: '',
    accent_color: '#c84b31',
    logo_url: '',
    banner_url: '',
    north_star_target_usd: 1000000,
    north_star_target_label: '$1M ARR',
    operator_enabled: false,
    operator_daily_budget_usd: 5.00,
  })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  const set = (key, val) => setForm(f => ({ ...f, [key]: val }))

  useEffect(() => {
    if (!open || !userId) return
    setLoading(true)
    fetch(`${BACKEND}/api/business/brand?user_id=${encodeURIComponent(userId)}`)
      .then(r => r.json())
      .then(d => {
        const b = d.brand || {}
        setForm({
          display_name: b.display_name || '',
          accent_color: b.accent_color || '#c84b31',
          logo_url: b.logo_url || '',
          banner_url: b.banner_url || '',
          north_star_target_usd: b.north_star_target_usd ?? 1000000,
          north_star_target_label: b.north_star_target_label || '$1M ARR',
          operator_enabled: b.operator_enabled ?? false,
          operator_daily_budget_usd: b.operator_daily_budget_usd ?? 5.00,
        })
      })
      .catch(e => console.error('BrandModal load failed', e))
      .finally(() => setLoading(false))
  }, [open, userId])

  const handleSave = async () => {
    setSaving(true)
    setSaved(false)
    try {
      const res = await fetch(`${BACKEND}/api/business/brand`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, ...form }),
      })
      const data = await res.json()
      if (data.brand) setSaved(true)
    } catch (e) {
      console.error('BrandModal save failed', e)
    }
    setSaving(false)
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
          width: '100%', maxWidth: 560, margin: '0 20px',
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
          ⚙️ BRAND & NORTH STAR
        </div>
        <div style={{ fontSize: 18, color: '#f3ead9', marginBottom: 4, fontWeight: 600 }}>
          Customize Jarvis for your business
        </div>
        <div style={{ fontSize: 12, color: 'rgba(243,234,217,0.5)', marginBottom: 20, lineHeight: 1.5 }}>
          The North Star target gets injected into every Jarvis response — it primes every answer toward closing the gap.
        </div>

        <div style={{ overflowY: 'auto', flex: 1, paddingRight: 4 }}>
          {loading ? (
            <div style={{ color: 'rgba(243,234,217,0.5)', fontSize: 13 }}>Loading…</div>
          ) : (
            <>
              {/* Identity */}
              <div style={{
                fontSize: 10, fontWeight: 700, letterSpacing: '0.1em',
                color: 'rgba(243,234,217,0.35)', textTransform: 'uppercase',
                marginBottom: 10,
              }}>
                Identity
              </div>

              <Field label="Business Display Name">
                <input
                  style={inputStyle}
                  value={form.display_name}
                  onChange={e => set('display_name', e.target.value)}
                  placeholder="e.g. Apex Dental"
                />
              </Field>

              <Field label="Accent Color">
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <input
                    type="color"
                    value={form.accent_color}
                    onChange={e => set('accent_color', e.target.value)}
                    style={{
                      width: 40, height: 36, borderRadius: 6, border: 'none',
                      background: 'none', cursor: 'pointer', padding: 2,
                    }}
                  />
                  <input
                    style={{ ...inputStyle, flex: 1 }}
                    value={form.accent_color}
                    onChange={e => set('accent_color', e.target.value)}
                    placeholder="#c84b31"
                  />
                </div>
              </Field>

              <Field label="Logo URL (optional)">
                <input
                  style={inputStyle}
                  value={form.logo_url}
                  onChange={e => set('logo_url', e.target.value)}
                  placeholder="https://..."
                />
              </Field>

              <Field label="Banner URL (optional)">
                <input
                  style={inputStyle}
                  value={form.banner_url}
                  onChange={e => set('banner_url', e.target.value)}
                  placeholder="https://..."
                />
              </Field>

              {/* North Star */}
              <div style={{
                fontSize: 10, fontWeight: 700, letterSpacing: '0.1em',
                color: 'rgba(243,234,217,0.35)', textTransform: 'uppercase',
                marginTop: 20, marginBottom: 10,
              }}>
                🎯 North Star
              </div>

              <Field label="Target Revenue Label">
                <input
                  style={inputStyle}
                  value={form.north_star_target_label}
                  onChange={e => set('north_star_target_label', e.target.value)}
                  placeholder="$1M ARR"
                />
              </Field>

              <Field label="Target Revenue (USD/year)">
                <input
                  type="number"
                  style={inputStyle}
                  value={form.north_star_target_usd}
                  onChange={e => set('north_star_target_usd', parseFloat(e.target.value) || 0)}
                  placeholder="1000000"
                  min={0}
                />
              </Field>

              <div style={{
                background: 'rgba(200,75,49,0.06)',
                border: '1px solid rgba(200,75,49,0.15)',
                borderRadius: 8, padding: '10px 14px', marginBottom: 16, fontSize: 11,
                color: 'rgba(243,234,217,0.65)', lineHeight: 1.5,
              }}>
                Every Jarvis response — chat, sub-agents, and the Operator Agent — is primed with this target. Jarvis filters everything through "does this close the gap to {form.north_star_target_label || '$1M'}?"
              </div>

              {/* Operator Agent */}
              <div style={{
                fontSize: 10, fontWeight: 700, letterSpacing: '0.1em',
                color: 'rgba(243,234,217,0.35)', textTransform: 'uppercase',
                marginTop: 20, marginBottom: 10,
              }}>
                🤖 Operator Agent
              </div>

              <div style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                marginBottom: 12,
              }}>
                <div>
                  <div style={{ fontSize: 13, color: '#f3ead9', fontWeight: 500 }}>
                    Enable nightly runs
                  </div>
                  <div style={{ fontSize: 11, color: 'rgba(243,234,217,0.5)', marginTop: 2 }}>
                    Jarvis works overnight — strategy, research, drafts. You approve in the morning.
                  </div>
                </div>
                <button
                  onClick={() => set('operator_enabled', !form.operator_enabled)}
                  style={{
                    width: 48, height: 26, borderRadius: 13, border: 'none',
                    background: form.operator_enabled ? '#22c55e' : 'rgba(243,234,217,0.12)',
                    cursor: 'pointer', position: 'relative', transition: 'background 200ms',
                    flexShrink: 0,
                  }}
                >
                  <span style={{
                    position: 'absolute', top: 3,
                    left: form.operator_enabled ? 26 : 4,
                    width: 20, height: 20, borderRadius: '50%',
                    background: 'white', transition: 'left 200ms',
                  }} />
                </button>
              </div>

              {form.operator_enabled && (
                <Field label="Daily budget cap (USD)">
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <input
                      type="number"
                      style={{ ...inputStyle, width: 120 }}
                      value={form.operator_daily_budget_usd}
                      onChange={e => set('operator_daily_budget_usd', parseFloat(e.target.value) || 0)}
                      min={0.5} max={50} step={0.5}
                    />
                    <span style={{ fontSize: 11, color: 'rgba(243,234,217,0.5)' }}>
                      per night · hard cap · default $5
                    </span>
                  </div>
                </Field>
              )}
            </>
          )}
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 20 }}>
          {saved && (
            <span style={{ fontSize: 12, color: '#22c55e', alignSelf: 'center', marginRight: 8 }}>
              ✅ Saved
            </span>
          )}
          <button
            onClick={onClose}
            style={{
              background: 'transparent',
              border: '1px solid rgba(243,234,217,0.15)',
              borderRadius: 8, padding: '8px 18px',
              color: 'rgba(243,234,217,0.7)', fontSize: 13,
              fontFamily: 'system-ui, sans-serif', cursor: 'pointer',
            }}
          >
            Close
          </button>
          <button
            onClick={handleSave}
            disabled={saving || loading}
            style={{
              background: saving ? 'rgba(200,75,49,0.5)' : '#c84b31',
              border: 'none', borderRadius: 8, padding: '8px 20px',
              color: 'white', fontSize: 13, fontWeight: 500,
              fontFamily: 'system-ui, sans-serif',
              cursor: saving ? 'default' : 'pointer',
            }}
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  )
}
