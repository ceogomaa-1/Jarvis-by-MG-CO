'use client'
import { useEffect, useState, useCallback } from 'react'
import { Loader2, Send, Unplug, Copy, Check } from 'lucide-react'

const BACKEND = 'https://jarvis-backend-4oz6.onrender.com'

// Jarvis on Telegram / WhatsApp — link an external chat identity to this OS1 account so the
// user can DM the same OS1 brain. OS1-only (Personal is untouched). Gated to subscribers.
export default function ChannelsPanel({ userId, email }) {
  const [loading, setLoading] = useState(true)
  const [state, setState] = useState(null)        // { has_access, telegram_enabled, whatsapp_enabled, bot_username, links }
  const [code, setCode] = useState(null)          // { code, deep_link, expires_at }
  const [busy, setBusy] = useState(false)
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    if (!userId) return
    setLoading(true)
    try {
      const res = await fetch(`${BACKEND}/api/channels/links?user_id=${encodeURIComponent(userId)}&email=${encodeURIComponent(email || '')}`)
      setState(await res.json())
    } catch (e) {
      setError('Could not load channel status.')
    }
    setLoading(false)
  }, [userId, email])

  useEffect(() => { load() }, [load])

  const telegramLink = (state?.links || []).find(l => l.channel === 'telegram')

  const generate = async () => {
    setBusy(true); setError(null); setCode(null)
    try {
      const res = await fetch(`${BACKEND}/api/channels/link/create`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, email: email || '', channel: 'telegram' }),
      })
      const data = await res.json()
      if (data.ok) setCode(data)
      else setError(data.error || 'Could not generate a code.')
    } catch (e) {
      setError(e.message)
    }
    setBusy(false)
  }

  const unlink = async () => {
    if (!confirm('Unlink Telegram? You will need a new code to reconnect.')) return
    setBusy(true)
    try {
      await fetch(`${BACKEND}/api/channels/unlink`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, channel: 'telegram' }),
      })
      setCode(null)
      await load()
    } catch (e) { setError(e.message) }
    setBusy(false)
  }

  const copyCode = () => {
    if (!code?.code) return
    navigator.clipboard?.writeText(code.code)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <div style={{
      borderRadius: 14, marginBottom: 14,
      border: '1px solid rgba(207,138,91,0.18)',
      background: 'rgba(207,138,91,0.03)',
      overflow: 'hidden',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '14px 16px' }}>
        <div style={{
          width: 40, height: 40, borderRadius: 10, background: '#229ED9',
          display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, color: '#fff',
        }}>
          <Send size={20} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            fontFamily: 'var(--pixel)', fontSize: 11, letterSpacing: '0.1em',
            color: '#ece6d9', textTransform: 'uppercase', marginBottom: 2,
          }}>
            Jarvis on Telegram
          </div>
          <p style={{ fontSize: 11, color: 'rgba(236,230,217,0.4)', margin: 0, lineHeight: 1.4 }}>
            Chat the same OS1 Jarvis from Telegram — text & files. Actions that change your data
            stay in the web app.
          </p>
        </div>
        {telegramLink && (
          <span style={{
            display: 'inline-flex', alignItems: 'center', gap: 4, padding: '2px 7px', borderRadius: 99,
            background: 'rgba(127,176,105,0.1)', border: '1px solid rgba(127,176,105,0.18)', flexShrink: 0,
          }}>
            <div style={{ width: 5, height: 5, borderRadius: '50%', background: '#7fb069' }} />
            <span style={{ fontFamily: 'var(--pixel)', fontSize: 8, letterSpacing: '0.08em', color: '#7fb069' }}>
              Linked
            </span>
          </span>
        )}
      </div>

      <div style={{ padding: '0 16px 14px', borderTop: '1px solid rgba(236,230,217,0.04)' }}>
        {loading ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '12px 0', color: 'rgba(236,230,217,0.4)', fontSize: 11 }}>
            <Loader2 size={12} style={{ animation: 'spin 1s linear infinite' }} /> Loading…
          </div>
        ) : !state?.telegram_enabled ? (
          <Note>Telegram isn't configured on the server yet. Check back soon.</Note>
        ) : !state?.has_access ? (
          <Note>Chatting Jarvis on Telegram is for OS1 subscribers. Subscribe to enable it.</Note>
        ) : telegramLink ? (
          <div style={{ paddingTop: 12 }}>
            <p style={{ fontSize: 11, color: 'rgba(236,230,217,0.6)', margin: '0 0 10px' }}>
              Connected{telegramLink.channel_username ? ` as @${telegramLink.channel_username}` : ''}. Just message the bot normally.
            </p>
            <button onClick={unlink} disabled={busy} style={btn('danger')}>
              <Unplug size={11} /> Unlink Telegram
            </button>
          </div>
        ) : (
          <div style={{ paddingTop: 12 }}>
            {!code ? (
              <button onClick={generate} disabled={busy} style={btn('primary')}>
                {busy && <Loader2 size={11} style={{ animation: 'spin 1s linear infinite' }} />}
                Generate link code
              </button>
            ) : (
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                  <code style={{
                    fontFamily: 'ui-monospace, monospace', fontSize: 18, letterSpacing: '0.18em',
                    color: '#cf8a5b', background: 'rgba(207,138,91,0.08)', padding: '6px 12px', borderRadius: 8,
                  }}>{code.code}</code>
                  <button onClick={copyCode} style={btn('ghost')}>
                    {copied ? <Check size={11} /> : <Copy size={11} />} {copied ? 'Copied' : 'Copy'}
                  </button>
                </div>
                <ol style={{ fontSize: 11, color: 'rgba(236,230,217,0.55)', lineHeight: 1.7, margin: '0 0 12px', paddingLeft: 16 }}>
                  <li>Open the Telegram bot{state?.bot_username ? ` (@${state.bot_username})` : ''}.</li>
                  <li>Send it this code (or tap the button below).</li>
                  <li>You're linked — start chatting Jarvis right there.</li>
                </ol>
                {code.deep_link && (
                  <a href={code.deep_link} target="_blank" rel="noreferrer" style={{ ...btn('primary'), textDecoration: 'none' }}>
                    <Send size={11} /> Open in Telegram &amp; link
                  </a>
                )}
                <p style={{ fontSize: 10, color: 'rgba(236,230,217,0.3)', marginTop: 10 }}>
                  Code expires in 15 minutes. Generate a new one any time.
                </p>
              </div>
            )}
          </div>
        )}
        {error && <Note danger>{error}</Note>}
      </div>
      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
    </div>
  )
}

function Note({ children, danger }) {
  return (
    <div style={{
      marginTop: 10, padding: '8px 11px', borderRadius: 8,
      background: danger ? 'rgba(239,68,68,0.07)' : 'rgba(236,230,217,0.03)',
      border: `1px solid ${danger ? 'rgba(239,68,68,0.18)' : 'rgba(236,230,217,0.08)'}`,
      fontSize: 11, color: danger ? 'rgba(239,68,68,0.85)' : 'rgba(236,230,217,0.5)', lineHeight: 1.5,
    }}>
      {children}
    </div>
  )
}

function btn(kind) {
  const base = {
    display: 'inline-flex', alignItems: 'center', gap: 6, borderRadius: 8,
    padding: '7px 14px', fontSize: 11, fontWeight: 500, fontFamily: 'system-ui, sans-serif',
    cursor: 'pointer', border: 'none', transition: 'all 200ms',
  }
  if (kind === 'primary') return { ...base, background: '#cf8a5b', color: '#fff' }
  if (kind === 'danger') return { ...base, background: 'transparent', color: 'rgba(239,68,68,0.8)', border: '1px solid rgba(239,68,68,0.22)' }
  return { ...base, background: 'transparent', color: 'rgba(236,230,217,0.6)', border: '1px solid rgba(236,230,217,0.12)' }
}
