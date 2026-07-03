'use client'
import { useEffect, useRef, useState } from 'react'
import { BookOpen, Upload, X, Trash2, Eye, Pencil } from 'lucide-react'

const BACKEND = 'https://jarvis-backend-4oz6.onrender.com'
const ACCEPT = '.pdf,.png,.jpg,.jpeg,.txt,.md,.csv,.docx,.zip'

const SOURCE_LABELS = {
  text: 'TEXT', pasted: 'TEXT', url: 'URL', pdf: 'PDF',
  docx: 'DOCX', image: 'IMAGE', zip: 'ZIP',
}

const SKILL_TYPE_BADGE = {
  knowledge: { label: 'KNOWLEDGE', color: '#ff2e51' },
  behavior: { label: 'BEHAVIOR', color: '#c84b31' },
  both: { label: 'KNOWLEDGE + BEHAVIOR', color: '#9b6dff' },
}

function applyProgressEvent(prev, evt) {
  if (evt.status === 'analyzing') {
    return [...prev, { label: evt.label, status: 'analyzing' }]
  }
  for (let i = prev.length - 1; i >= 0; i--) {
    if (prev[i].status === 'analyzing') {
      const next = [...prev]
      next[i] = { ...next[i], ...evt, label: next[i].label || evt.label }
      return next
    }
  }
  return [...prev, evt]
}

function formatStatusSuffix(item) {
  if (item.status === 'analyzing') return ''
  if (item.status === 'learned') {
    const type = item.skill_type ? ` (${item.skill_type})` : ''
    const name = item.name ? ` '${item.name}'` : ''
    const change = item.what_changes ? ` — ${item.what_changes}` : ''
    return `[LEARNED ✓ — created skill${name}${type}]${change}`
  }
  if (item.status === 'skipped') return `[SKIPPED${item.error ? ` — ${item.error}` : ''}]`
  if (item.status === 'error') return `[ERROR — ${item.error || 'unknown'}]`
  return ''
}

function formatDate(iso) {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
  } catch {
    return ''
  }
}

export default function KnowledgeBaseModal({ open, onClose, userId, userEmail }) {
  const [tab, setTab] = useState('feed')
  const [text, setText] = useState('')
  const [files, setFiles] = useState([])
  const [dragOver, setDragOver] = useState(false)
  const [progress, setProgress] = useState([])
  const [feeding, setFeeding] = useState(false)
  const [sources, setSources] = useState([])
  const [sourcesLoading, setSourcesLoading] = useState(false)
  const [deletingId, setDeletingId] = useState(null)
  const [togglingId, setTogglingId] = useState(null)
  const [editingSkill, setEditingSkill] = useState(null)
  const [editMode, setEditMode] = useState(false)
  const [skillSaving, setSkillSaving] = useState(false)
  const [wishText, setWishText] = useState('')
  const [wishSubmitting, setWishSubmitting] = useState(false)
  const [wishSubmitted, setWishSubmitted] = useState(false)
  const [wishError, setWishError] = useState('')
  const lastWishSubmitRef = useRef(0)
  const fileInputRef = useRef(null)
  const progressEndRef = useRef(null)

  useEffect(() => {
    if (!open || !userId) return
    loadSources()
  }, [open, userId])

  useEffect(() => {
    progressEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [progress])

  if (!open) return null

  async function loadSources() {
    setSourcesLoading(true)
    try {
      const res = await fetch(`${BACKEND}/api/business/knowledge?user_id=${encodeURIComponent(userId)}`)
      const data = await res.json()
      setSources(data.sources || [])
    } catch (e) {
      console.error('Load knowledge sources failed', e)
    }
    setSourcesLoading(false)
  }

  function addFiles(list) {
    const incoming = Array.from(list || [])
    if (incoming.length) setFiles(prev => [...prev, ...incoming])
  }

  function removeFile(idx) {
    setFiles(prev => prev.filter((_, i) => i !== idx))
  }

  async function handleFeed() {
    if (!userId || feeding) return
    if (!text.trim() && files.length === 0) return

    setFeeding(true)
    setProgress([])

    try {
      const formData = new FormData()
      formData.append('user_id', userId)
      formData.append('text', text)
      files.forEach(f => formData.append('files', f))

      const res = await fetch(`${BACKEND}/api/business/knowledge/ingest`, {
        method: 'POST',
        body: formData,
      })
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buf = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const lines = buf.split('\n')
        buf = lines.pop() ?? ''
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const raw = line.slice(6)
          if (raw === '[DONE]') continue
          try {
            const evt = JSON.parse(raw)
            if (evt.type === 'progress') {
              setProgress(prev => applyProgressEvent(prev, evt))
            }
          } catch {}
        }
      }

      setText('')
      setFiles([])
      loadSources()
    } catch (e) {
      console.error('Knowledge ingest failed', e)
      setProgress(prev => [...prev, { label: 'connection', status: 'error', error: 'Could not reach Jarvis' }])
    }
    setFeeding(false)
  }

  async function handleDelete(id) {
    if (!userId) return
    setDeletingId(id)
    try {
      await fetch(`${BACKEND}/api/business/knowledge/${id}?user_id=${encodeURIComponent(userId)}`, { method: 'DELETE' })
      setSources(prev => prev.filter(s => s.id !== id))
    } catch (e) {
      console.error('Delete knowledge source failed', e)
    }
    setDeletingId(null)
  }

  async function toggleSkill(id, enabled) {
    if (!userId) return
    setTogglingId(id)
    setSources(prev => prev.map(s => (s.id === id ? { ...s, enabled } : s)))  // optimistic
    try {
      await fetch(`${BACKEND}/api/business/skills/${id}/toggle`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, enabled }),
      })
    } catch (e) {
      console.error('Toggle skill failed', e)
      setSources(prev => prev.map(s => (s.id === id ? { ...s, enabled: !enabled } : s)))  // revert
    }
    setTogglingId(null)
  }

  async function openSkill(id, mode) {
    if (!userId) return
    try {
      const res = await fetch(`${BACKEND}/api/business/skills/${id}?user_id=${encodeURIComponent(userId)}`)
      const data = await res.json()
      if (data.skill) {
        setEditingSkill(data.skill)
        setEditMode(mode === 'edit')
      }
    } catch (e) {
      console.error('Open skill failed', e)
    }
  }

  async function saveSkill() {
    if (!editingSkill || skillSaving) return
    setSkillSaving(true)
    try {
      const fields = {
        name: editingSkill.name,
        description: editingSkill.description,
        skill_type: editingSkill.skill_type,
        full_content: editingSkill.full_content,
        operating_instructions: editingSkill.operating_instructions,
      }
      const res = await fetch(`${BACKEND}/api/business/skills/${editingSkill.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, fields }),
      })
      if (res.ok) {
        setEditingSkill(null)
        setEditMode(false)
        loadSources()
      }
    } catch (e) {
      console.error('Save skill failed', e)
    }
    setSkillSaving(false)
  }

  async function handleWishSubmit() {
    if (!userId || wishSubmitting) return
    const wish = wishText.trim()
    if (!wish) return

    const now = Date.now()
    if (now - lastWishSubmitRef.current < 30000) {
      setWishError('Slow down a little — try again in a few seconds.')
      return
    }

    setWishSubmitting(true)
    setWishError('')
    try {
      await fetch(`${BACKEND}/api/business/feedback/wish`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, email: userEmail || null, wish_text: wish }),
      })
      lastWishSubmitRef.current = now
      setWishText('')
      setWishSubmitted(true)
    } catch (e) {
      console.error('Wish submit failed', e)
      setWishError('Could not reach Jarvis — try again in a moment.')
    }
    setWishSubmitting(false)
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
          width: '100%', maxWidth: 680, margin: '0 20px',
          background: 'rgba(15, 15, 18, 0.55)',
          backdropFilter: 'blur(28px) saturate(180%)',
          WebkitBackdropFilter: 'blur(28px) saturate(180%)',
          border: '1px solid rgba(244,244,242,0.15)',
          borderRadius: 20, padding: 28,
          fontFamily: 'system-ui, sans-serif',
          boxShadow: '0 24px 60px rgba(0,0,0,0.55), inset 0 1px 0 rgba(244,244,242,0.06)',
          display: 'flex', flexDirection: 'column',
          maxHeight: '88vh',
        }}
      >
        <div style={{
          fontFamily: 'var(--pixel)',
          fontSize: 10, letterSpacing: '0.12em',
          color: '#ff2e51', marginBottom: 8, textTransform: 'uppercase',
        }}>
          KNOWLEDGE BASE
        </div>
        <div style={{
          fontFamily: 'var(--pixel)',
          fontSize: 13, color: '#f4f4f2', marginBottom: 4, lineHeight: 1.5,
        }}>
          Feed Jarvis what it should know
        </div>
        <div className="os1-serif-micro" style={{ fontSize: 9, color: 'rgba(244,244,242,0.45)', marginBottom: 16 }}>
          stuff you're ready to paste and want me to know right away
        </div>

        {/* Tabs */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
          {[
            { key: 'feed', label: 'Feed Jarvis' },
            { key: 'knows', label: 'What Jarvis Knows' },
            { key: 'wish', label: 'Wish Box' },
          ].map(t => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              style={{
                background: tab === t.key ? 'rgba(255,46,81,0.15)' : 'transparent',
                border: `1px solid ${tab === t.key ? '#ff2e51' : 'rgba(244,244,242,0.12)'}`,
                borderRadius: 10, padding: '8px 16px',
                color: tab === t.key ? '#ff2e51' : 'rgba(244,244,242,0.6)',
                fontFamily: 'var(--pixel)',
                fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.06em',
                cursor: 'pointer', transition: 'all 150ms ease',
              }}
            >
              {t.label}
            </button>
          ))}
        </div>

        {tab === 'feed' && (
          <div style={{ display: 'flex', flexDirection: 'column', minHeight: 0, flex: 1 }}>
            <textarea
              value={text}
              onChange={e => setText(e.target.value)}
              disabled={feeding}
              placeholder="Paste anything — pricing, policies, a process doc, a URL to your menu... Jarvis will read it and remember what matters."
              rows={8}
              style={{
                width: '100%', boxSizing: 'border-box',
                background: 'rgba(244,244,242,0.04)',
                border: '1px solid rgba(244,244,242,0.12)',
                borderRadius: 10, padding: '14px 16px',
                color: '#f4f4f2',
                fontFamily: 'ui-monospace, "SF Mono", Menlo, monospace',
                fontSize: 13, lineHeight: 1.6, outline: 'none', resize: 'vertical',
                marginBottom: 12,
              }}
            />

            {/* Drop zone */}
            <div
              onDragOver={e => { e.preventDefault(); setDragOver(true) }}
              onDragLeave={() => setDragOver(false)}
              onDrop={e => { e.preventDefault(); setDragOver(false); addFiles(e.dataTransfer.files) }}
              onClick={() => fileInputRef.current?.click()}
              style={{
                border: `1px dashed ${dragOver ? '#ff2e51' : 'rgba(244,244,242,0.18)'}`,
                borderRadius: 10, padding: '16px',
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10,
                cursor: 'pointer', marginBottom: 12,
                background: dragOver ? 'rgba(255,46,81,0.08)' : 'transparent',
                transition: 'all 150ms ease',
              }}
            >
              <Upload size={16} color="rgba(244,244,242,0.5)" />
              <span className="os1-serif-micro" style={{ fontSize: 10, color: 'rgba(244,244,242,0.5)' }}>
                Drop files here or click to browse — pdf, image, txt, md, csv, docx, zip
              </span>
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept={ACCEPT}
                onChange={e => { addFiles(e.target.files); e.target.value = '' }}
                style={{ display: 'none' }}
              />
            </div>

            {files.length > 0 && (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 12 }}>
                {files.map((f, idx) => (
                  <div key={`${f.name}-${idx}`} style={{
                    display: 'flex', alignItems: 'center', gap: 6,
                    background: 'rgba(244,244,242,0.06)',
                    border: '1px solid rgba(244,244,242,0.12)',
                    borderRadius: 8, padding: '5px 8px 5px 10px',
                  }}>
                    <span className="os1-serif-micro" style={{ fontSize: 10, color: '#f4f4f2' }}>{f.name}</span>
                    <button
                      onClick={() => removeFile(idx)}
                      disabled={feeding}
                      style={{ background: 'none', border: 'none', cursor: 'pointer', display: 'flex', padding: 2 }}
                    >
                      <X size={12} color="rgba(244,244,242,0.5)" />
                    </button>
                  </div>
                ))}
              </div>
            )}

            {/* Progress lines */}
            {progress.length > 0 && (
              <div style={{
                background: 'rgba(0,0,0,0.35)',
                border: '1px solid rgba(244,244,242,0.1)',
                borderRadius: 10, padding: '12px 14px',
                marginBottom: 12, maxHeight: 160, overflowY: 'auto',
              }} className="os1-scroll">
                {progress.map((item, idx) => (
                  <div key={idx} className="os1-serif-micro" style={{
                    fontSize: 10, lineHeight: 1.8,
                    color: item.status === 'error' ? '#ff6b6b'
                      : item.status === 'learned' ? '#ff2e51'
                      : 'rgba(244,244,242,0.55)',
                    fontFamily: 'ui-monospace, "SF Mono", Menlo, monospace',
                    whiteSpace: 'pre-wrap', wordBreak: 'break-all',
                  }}>
                    {`▸ analyzing ${item.label}… ${formatStatusSuffix(item)}`}
                  </div>
                ))}
                <div ref={progressEndRef} />
              </div>
            )}

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 'auto' }}>
              <button
                onClick={onClose}
                disabled={feeding}
                style={{
                  background: 'transparent',
                  border: '1px solid rgba(244,244,242,0.1)',
                  borderRadius: 12, padding: '10px 24px',
                  color: 'rgba(244,244,242,0.7)', fontSize: 13,
                  fontFamily: 'system-ui, sans-serif', cursor: feeding ? 'default' : 'pointer',
                  transition: 'all 200ms ease',
                }}
              >
                Close
              </button>
              <button
                onClick={handleFeed}
                disabled={feeding || (!text.trim() && files.length === 0)}
                style={{
                  background: feeding ? 'rgba(255,46,81,0.4)' : '#ff2e51',
                  border: 'none', borderRadius: 12, padding: '10px 24px',
                  color: '#0a0a0a', fontSize: 13, fontWeight: 500,
                  fontFamily: 'system-ui, sans-serif',
                  cursor: feeding ? 'default' : 'pointer',
                  opacity: (!text.trim() && files.length === 0) ? 0.5 : 1,
                  transition: 'background 200ms ease',
                }}
              >
                {feeding ? 'Feeding Jarvis...' : 'Feed Jarvis'}
              </button>
            </div>
          </div>
        )}

        {tab === 'knows' && (
          <div style={{ display: 'flex', flexDirection: 'column', minHeight: 0, flex: 1 }}>
            <div style={{ flex: 1, overflowY: 'auto', minHeight: 100, maxHeight: 380 }} className="os1-scroll">
              {sourcesLoading && (
                <div className="os1-serif-micro" style={{ fontSize: 11, color: 'rgba(244,244,242,0.4)', padding: '20px 0', textAlign: 'center' }}>
                  Loading...
                </div>
              )}
              {!sourcesLoading && sources.length === 0 && (
                <div style={{ padding: '32px 0', textAlign: 'center' }}>
                  <BookOpen size={24} color="rgba(244,244,242,0.25)" style={{ marginBottom: 10 }} />
                  <div className="os1-serif-micro" style={{ fontSize: 11, color: 'rgba(244,244,242,0.4)' }}>
                    Nothing yet — paste something or drop a file in Feed Jarvis.
                  </div>
                </div>
              )}
              {sources.map(source => {
                const isSkill = source.kind === 'skill'
                const badge = isSkill ? (SKILL_TYPE_BADGE[source.skill_type] || SKILL_TYPE_BADGE.knowledge) : null
                const enabled = source.enabled !== false
                return (
                <div key={source.id} style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12,
                  padding: '12px 14px', marginBottom: 8,
                  background: 'rgba(244,244,242,0.03)',
                  border: '1px solid rgba(244,244,242,0.1)',
                  borderRadius: 10, opacity: isSkill && !enabled ? 0.5 : 1,
                }}>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                      <span style={{
                        fontFamily: 'var(--pixel)',
                        fontSize: 8, letterSpacing: '0.08em',
                        color: badge ? badge.color : '#ff2e51',
                        border: `1px solid ${badge ? badge.color : 'rgba(255,46,81,0.4)'}55`,
                        borderRadius: 4, padding: '2px 5px', flexShrink: 0,
                      }}>
                        {badge ? badge.label : (SOURCE_LABELS[source.source_type] || 'TEXT')}
                      </span>
                      <span style={{
                        color: '#f4f4f2', fontSize: 13,
                        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      }}>
                        {source.label}
                      </span>
                    </div>
                    <div className="os1-serif-micro" style={{ fontSize: 9, color: 'rgba(244,244,242,0.4)' }}>
                      {formatDate(source.created_at)} · {(SOURCE_LABELS[source.source_type] || 'text').toLowerCase()}
                      {isSkill && !enabled ? ' · off' : ''}
                    </div>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 4, flexShrink: 0 }}>
                    {isSkill && (
                      <button
                        onClick={() => toggleSkill(source.id, !enabled)}
                        disabled={togglingId === source.id}
                        title={enabled ? 'Enabled — click to turn off' : 'Disabled — click to turn on'}
                        style={{
                          width: 34, height: 18, borderRadius: 9, border: 'none', cursor: 'pointer',
                          background: enabled ? '#ff2e51' : 'rgba(244,244,242,0.18)',
                          position: 'relative', transition: 'background 150ms ease', marginRight: 4, flexShrink: 0,
                        }}
                      >
                        <span style={{
                          position: 'absolute', top: 2, left: enabled ? 18 : 2,
                          width: 14, height: 14, borderRadius: '50%', background: '#fff',
                          transition: 'left 150ms ease',
                        }} />
                      </button>
                    )}
                    {isSkill && (
                      <button onClick={() => openSkill(source.id, 'view')}
                        style={{ background: 'none', border: 'none', cursor: 'pointer', display: 'flex', padding: 6 }} title="View full content">
                        <Eye size={15} color="rgba(244,244,242,0.45)" />
                      </button>
                    )}
                    {isSkill && (
                      <button onClick={() => openSkill(source.id, 'edit')}
                        style={{ background: 'none', border: 'none', cursor: 'pointer', display: 'flex', padding: 6 }} title="Edit">
                        <Pencil size={14} color="rgba(244,244,242,0.45)" />
                      </button>
                    )}
                    <button
                      onClick={() => handleDelete(source.id)}
                      disabled={deletingId === source.id}
                      style={{ background: 'none', border: 'none', cursor: 'pointer', display: 'flex', padding: 6 }}
                      title="Delete"
                    >
                      <Trash2 size={15} color="rgba(244,244,242,0.4)" />
                    </button>
                  </div>
                </div>
                )
              })}
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
        )}

        {tab === 'wish' && (
          <div style={{ display: 'flex', flexDirection: 'column', minHeight: 0, flex: 1 }}>
            {!wishSubmitted ? (
              <>
                <div style={{
                  fontFamily: 'var(--pixel)',
                  fontSize: 13, color: '#f4f4f2', marginBottom: 4, lineHeight: 1.5,
                }}>
                  What do you wish Jarvis could do better — or have — that doesn't exist yet?
                </div>
                <div className="os1-serif-micro" style={{ fontSize: 9, color: 'rgba(244,244,242,0.45)', marginBottom: 16 }}>
                  every wish lands directly on the founder's desk.
                </div>
                <textarea
                  value={wishText}
                  onChange={e => setWishText(e.target.value)}
                  disabled={wishSubmitting}
                  placeholder="Tell Jarvis what's missing, what's broken, or what you wish it could do..."
                  rows={8}
                  style={{
                    width: '100%', boxSizing: 'border-box',
                    background: 'rgba(244,244,242,0.04)',
                    border: '1px solid rgba(244,244,242,0.12)',
                    borderRadius: 10, padding: '14px 16px',
                    color: '#f4f4f2',
                    fontFamily: 'ui-monospace, "SF Mono", Menlo, monospace',
                    fontSize: 13, lineHeight: 1.6, outline: 'none', resize: 'vertical',
                    marginBottom: 12,
                  }}
                />
                {wishError && (
                  <div className="os1-serif-micro" style={{ fontSize: 10, color: '#ff6b6b', marginBottom: 12 }}>
                    {wishError}
                  </div>
                )}
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 'auto' }}>
                  <button
                    onClick={onClose}
                    disabled={wishSubmitting}
                    style={{
                      background: 'transparent',
                      border: '1px solid rgba(244,244,242,0.1)',
                      borderRadius: 12, padding: '10px 24px',
                      color: 'rgba(244,244,242,0.7)', fontSize: 13,
                      fontFamily: 'system-ui, sans-serif', cursor: wishSubmitting ? 'default' : 'pointer',
                      transition: 'all 200ms ease',
                    }}
                  >
                    Close
                  </button>
                  <button
                    onClick={handleWishSubmit}
                    disabled={wishSubmitting || !wishText.trim()}
                    style={{
                      background: wishSubmitting ? 'rgba(255,46,81,0.4)' : '#ff2e51',
                      border: 'none', borderRadius: 12, padding: '10px 24px',
                      color: '#0a0a0a', fontSize: 13, fontWeight: 500,
                      fontFamily: 'system-ui, sans-serif',
                      cursor: wishSubmitting ? 'default' : 'pointer',
                      opacity: !wishText.trim() ? 0.5 : 1,
                      transition: 'background 200ms ease',
                    }}
                  >
                    {wishSubmitting ? 'Sending...' : 'Send'}
                  </button>
                </div>
              </>
            ) : (
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', textAlign: 'center', gap: 16, padding: '40px 0' }}>
                <div className="onboarding-pulse" style={{ width: 10, height: 10, background: '#ff2e51', borderRadius: 2 }} />
                <div style={{
                  fontFamily: 'var(--pixel)',
                  fontSize: 13, color: '#f4f4f2', lineHeight: 1.6, maxWidth: 340,
                }}>
                  Thanks! Keep your eyes on Jarvis — your request will be seen soon!
                </div>
                <button
                  onClick={() => setWishSubmitted(false)}
                  className="os1-serif-micro"
                  style={{ fontSize: 10, color: '#ff2e51', background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline' }}
                >
                  make another wish
                </button>
              </div>
            )}
          </div>
        )}

        {/* Skill view / edit overlay */}
        {editingSkill && (
          <div
            onClick={() => { setEditingSkill(null); setEditMode(false) }}
            style={{
              position: 'fixed', inset: 0, zIndex: 1001,
              background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(10px)',
              WebkitBackdropFilter: 'blur(10px)',
              display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20,
            }}
          >
            <div
              onClick={e => e.stopPropagation()}
              style={{
                width: '100%', maxWidth: 640, maxHeight: '86vh',
                background: 'rgba(15,15,18,0.92)',
                border: '1px solid rgba(244,244,242,0.15)', borderRadius: 18, padding: 24,
                display: 'flex', flexDirection: 'column', gap: 12,
                fontFamily: 'system-ui, sans-serif',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ fontFamily: 'var(--pixel)', fontSize: 11, color: '#ff2e51', letterSpacing: '0.1em', textTransform: 'uppercase' }}>
                  {editMode ? 'Edit Skill' : 'Skill'}
                </div>
                <button onClick={() => { setEditingSkill(null); setEditMode(false) }} style={{ background: 'none', border: 'none', cursor: 'pointer', display: 'flex', padding: 4 }}>
                  <X size={16} color="rgba(244,244,242,0.6)" />
                </button>
              </div>

              <div style={{ overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 12 }} className="os1-scroll">
                <label style={{ fontSize: 10, color: 'rgba(244,244,242,0.5)' }}>Name</label>
                <input
                  value={editingSkill.name || ''}
                  readOnly={!editMode}
                  onChange={e => setEditingSkill({ ...editingSkill, name: e.target.value })}
                  style={inputStyle(editMode)}
                />

                <label style={{ fontSize: 10, color: 'rgba(244,244,242,0.5)' }}>Type</label>
                <select
                  value={editingSkill.skill_type || 'knowledge'}
                  disabled={!editMode}
                  onChange={e => setEditingSkill({ ...editingSkill, skill_type: e.target.value })}
                  style={inputStyle(editMode)}
                >
                  <option value="knowledge">Knowledge</option>
                  <option value="behavior">Behavior</option>
                  <option value="both">Knowledge + Behavior</option>
                </select>

                <label style={{ fontSize: 10, color: 'rgba(244,244,242,0.5)' }}>Description (when this skill applies)</label>
                <input
                  value={editingSkill.description || ''}
                  readOnly={!editMode}
                  onChange={e => setEditingSkill({ ...editingSkill, description: e.target.value })}
                  style={inputStyle(editMode)}
                />

                {(editingSkill.skill_type === 'behavior' || editingSkill.skill_type === 'both') && (
                  <>
                    <label style={{ fontSize: 10, color: 'rgba(244,244,242,0.5)' }}>Operating instructions (how Jarvis should act)</label>
                    <textarea
                      value={editingSkill.operating_instructions || ''}
                      readOnly={!editMode}
                      onChange={e => setEditingSkill({ ...editingSkill, operating_instructions: e.target.value })}
                      rows={3}
                      style={{ ...inputStyle(editMode), resize: 'vertical', fontFamily: 'ui-monospace, monospace' }}
                    />
                  </>
                )}

                <label style={{ fontSize: 10, color: 'rgba(244,244,242,0.5)' }}>Full content (stored verbatim)</label>
                <textarea
                  value={editingSkill.full_content || ''}
                  readOnly={!editMode}
                  onChange={e => setEditingSkill({ ...editingSkill, full_content: e.target.value })}
                  rows={12}
                  style={{ ...inputStyle(editMode), resize: 'vertical', fontFamily: 'ui-monospace, monospace', fontSize: 12, lineHeight: 1.6 }}
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
                {!editMode ? (
                  <button onClick={() => setEditMode(true)} style={primaryBtnStyle(false)}>Edit</button>
                ) : (
                  <button onClick={saveSkill} disabled={skillSaving} style={primaryBtnStyle(skillSaving)}>
                    {skillSaving ? 'Saving...' : 'Save changes'}
                  </button>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function inputStyle(editable) {
  return {
    width: '100%', boxSizing: 'border-box',
    background: editable ? 'rgba(244,244,242,0.06)' : 'rgba(244,244,242,0.02)',
    border: '1px solid rgba(244,244,242,0.12)', borderRadius: 8,
    padding: '9px 12px', color: '#f4f4f2', fontSize: 13, outline: 'none',
    fontFamily: 'system-ui, sans-serif',
  }
}

function primaryBtnStyle(busy) {
  return {
    background: busy ? 'rgba(255,46,81,0.4)' : '#ff2e51', border: 'none', borderRadius: 12,
    padding: '9px 22px', color: '#0a0a0a', fontSize: 13, fontWeight: 500,
    fontFamily: 'system-ui, sans-serif', cursor: busy ? 'default' : 'pointer',
  }
}
