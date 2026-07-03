'use client'
// Batch 56 — minimal admin authoring form for "What's New" announcements.
//
// Gated server-side by ADMIN_USER_IDS (the backend returns 403 for non-admins).
// Publishing fires the one-time branded email blast to all users. Mohamed can
// use this form OR insert a row in Supabase and flip is_published=true — both
// paths trigger the email exactly once (guarded by announcement_email_log).

import { useEffect, useState } from 'react'
import { supabase } from '../../../lib/supabase'

import { BACKEND } from '@/lib/backend'

const TAGS = ['New Feature', 'Improvement', 'Fix']

export default function AdminAnnouncementsPage() {
  const [adminUserId, setAdminUserId] = useState(null)
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const [tag, setTag] = useState('New Feature')
  const [mediaUrl, setMediaUrl] = useState('')
  const [ctaLabel, setCtaLabel] = useState('')
  const [ctaUrl, setCtaUrl] = useState('')
  const [publish, setPublish] = useState(true)
  const [status, setStatus] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!supabase) return
    supabase.auth.getUser().then(({ data }) => setAdminUserId(data?.user?.id || null))
  }, [])

  const submit = async () => {
    if (!adminUserId) { setStatus({ ok: false, msg: 'Not signed in.' }); return }
    if (!title.trim() || !body.trim()) { setStatus({ ok: false, msg: 'Title and body are required.' }); return }
    setBusy(true)
    setStatus(null)
    try {
      const res = await fetch(`${BACKEND}/api/admin/announcements`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          admin_user_id: adminUserId,
          title: title.trim(),
          body,
          tag,
          media_url: mediaUrl.trim() || null,
          cta_label: ctaLabel.trim() || null,
          cta_url: ctaUrl.trim() || null,
          is_published: publish,
        }),
      })
      if (res.status === 403) { setStatus({ ok: false, msg: 'Forbidden — this account is not an admin.' }); return }
      if (!res.ok) { setStatus({ ok: false, msg: `Failed (${res.status}).` }); return }
      setStatus({
        ok: true,
        msg: publish
          ? 'Published! Users will see the in-app card and the email blast is sending.'
          : 'Saved as draft (not published, no email sent).',
      })
      setTitle(''); setBody(''); setMediaUrl(''); setCtaLabel(''); setCtaUrl('')
    } catch {
      setStatus({ ok: false, msg: 'Network error.' })
    } finally {
      setBusy(false)
    }
  }

  const inputStyle = {
    width: '100%', background: '#141414', color: '#ededed',
    border: '1px solid rgba(255,255,255,0.12)', borderRadius: 8,
    padding: '11px 13px', fontSize: 14, fontFamily: 'inherit', marginBottom: 16,
    boxSizing: 'border-box',
  }
  const labelStyle = { display: 'block', fontSize: 11, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'rgba(237,237,237,0.5)', marginBottom: 7 }

  return (
    <div style={{ minHeight: '100vh', background: '#0a0a0a', color: '#ededed', padding: '48px 20px', fontFamily: '-apple-system, "Segoe UI", Roboto, sans-serif' }}>
      <div style={{ maxWidth: 560, margin: '0 auto' }}>
        <h1 style={{ fontSize: 24, margin: '0 0 6px' }}>✨ New Announcement</h1>
        <p style={{ color: 'rgba(237,237,237,0.5)', fontSize: 13, margin: '0 0 28px', lineHeight: 1.6 }}>
          Publishes a "What's New" card to every user (Personal + OS1) and sends one branded email.
          Admin only. <strong>Body supports markdown.</strong>
        </p>

        <label style={labelStyle}>Title</label>
        <input style={inputStyle} value={title} onChange={e => setTitle(e.target.value)} placeholder="e.g. Concurrent web research is here" />

        <label style={labelStyle}>Body (markdown)</label>
        <textarea
          style={{ ...inputStyle, minHeight: 130, resize: 'vertical' }}
          value={body}
          onChange={e => setBody(e.target.value)}
          placeholder={'What changed and why it matters.\n\n- Bullet one\n- Bullet two'}
        />

        <label style={labelStyle}>Tag</label>
        <select style={inputStyle} value={tag} onChange={e => setTag(e.target.value)}>
          {TAGS.map(t => <option key={t} value={t}>{t}</option>)}
        </select>

        <label style={labelStyle}>Media URL (optional — image / gif)</label>
        <input style={inputStyle} value={mediaUrl} onChange={e => setMediaUrl(e.target.value)} placeholder="https://..." />

        <div style={{ display: 'flex', gap: 14 }}>
          <div style={{ flex: 1 }}>
            <label style={labelStyle}>CTA label (optional)</label>
            <input style={inputStyle} value={ctaLabel} onChange={e => setCtaLabel(e.target.value)} placeholder="See what's new" />
          </div>
          <div style={{ flex: 1 }}>
            <label style={labelStyle}>CTA URL (optional)</label>
            <input style={inputStyle} value={ctaUrl} onChange={e => setCtaUrl(e.target.value)} placeholder="https://..." />
          </div>
        </div>

        <label style={{ display: 'flex', alignItems: 'center', gap: 10, margin: '6px 0 22px', cursor: 'pointer', fontSize: 14 }}>
          <input type="checkbox" checked={publish} onChange={e => setPublish(e.target.checked)} />
          Publish now (sends the email blast). Uncheck to save as a draft.
        </label>

        <button
          onClick={submit}
          disabled={busy}
          style={{
            width: '100%', padding: '14px', borderRadius: 9, border: 'none',
            background: busy ? '#444' : '#ff9072', color: '#140b07',
            fontSize: 13, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase',
            cursor: busy ? 'default' : 'pointer',
          }}
        >
          {busy ? 'Working…' : publish ? 'Publish + Email Everyone' : 'Save Draft'}
        </button>

        {status && (
          <div style={{
            marginTop: 18, padding: '13px 15px', borderRadius: 8, fontSize: 13, lineHeight: 1.55,
            background: status.ok ? 'rgba(108,208,138,0.1)' : 'rgba(255,90,90,0.1)',
            border: `1px solid ${status.ok ? 'rgba(108,208,138,0.4)' : 'rgba(255,90,90,0.4)'}`,
            color: status.ok ? '#9be8b3' : '#ff9a9a',
          }}>
            {status.msg}
          </div>
        )}

        <p style={{ color: 'rgba(237,237,237,0.35)', fontSize: 11, marginTop: 26, lineHeight: 1.6 }}>
          Signed in as: {adminUserId || '—'}
        </p>
      </div>
    </div>
  )
}
