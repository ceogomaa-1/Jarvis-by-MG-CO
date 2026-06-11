'use client'
import { useEffect, useRef, useState } from 'react'
import { BookOpen, Upload, X, Trash2 } from 'lucide-react'

const BACKEND = 'https://jarvis-backend-4oz6.onrender.com'
const ACCEPT = '.pdf,.png,.jpg,.jpeg,.txt,.md,.csv,.docx,.zip'

const SOURCE_LABELS = {
  text: 'TEXT', pasted: 'TEXT', url: 'URL', pdf: 'PDF',
  docx: 'DOCX', image: 'IMAGE', zip: 'ZIP',
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
    const n = item.fact_count || 0
    return `[LEARNED ${n} fact${n === 1 ? '' : 's'}]`
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

export default function KnowledgeBaseModal({ open, onClose, userId }) {
  const [tab, setTab] = useState('feed')
  const [text, setText] = useState('')
  const [files, setFiles] = useState([])
  const [dragOver, setDragOver] = useState(false)
  const [progress, setProgress] = useState([])
  const [feeding, setFeeding] = useState(false)
  const [sources, setSources] = useState([])
  const [sourcesLoading, setSourcesLoading] = useState(false)
  const [deletingId, setDeletingId] = useState(null)
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
          border: '1px solid rgba(232,232,232,0.15)',
          borderRadius: 20, padding: 28,
          fontFamily: 'system-ui, sans-serif',
          boxShadow: '0 24px 60px rgba(0,0,0,0.55), inset 0 1px 0 rgba(232,232,232,0.06)',
          display: 'flex', flexDirection: 'column',
          maxHeight: '88vh',
        }}
      >
        <div style={{
          fontFamily: 'var(--font-pixel), monospace',
          fontSize: 10, letterSpacing: '0.12em',
          color: '#2d7ff9', marginBottom: 8, textTransform: 'uppercase',
        }}>
          KNOWLEDGE BASE
        </div>
        <div style={{
          fontFamily: 'var(--font-pixel), monospace',
          fontSize: 13, color: '#e8e8e8', marginBottom: 4, lineHeight: 1.5,
        }}>
          Feed Jarvis what it should know
        </div>
        <div className="os1-serif-micro" style={{ fontSize: 9, color: 'rgba(232,232,232,0.45)', marginBottom: 16 }}>
          stuff you're ready to paste and want me to know right away
        </div>

        {/* Tabs */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
          {[
            { key: 'feed', label: 'Feed Jarvis' },
            { key: 'knows', label: 'What Jarvis Knows' },
          ].map(t => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              style={{
                background: tab === t.key ? 'rgba(45,127,249,0.15)' : 'transparent',
                border: `1px solid ${tab === t.key ? '#2d7ff9' : 'rgba(232,232,232,0.12)'}`,
                borderRadius: 10, padding: '8px 16px',
                color: tab === t.key ? '#2d7ff9' : 'rgba(232,232,232,0.6)',
                fontFamily: 'var(--font-pixel), monospace',
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
                background: 'rgba(232,232,232,0.04)',
                border: '1px solid rgba(232,232,232,0.12)',
                borderRadius: 10, padding: '14px 16px',
                color: '#e8e8e8',
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
                border: `1px dashed ${dragOver ? '#2d7ff9' : 'rgba(232,232,232,0.18)'}`,
                borderRadius: 10, padding: '16px',
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10,
                cursor: 'pointer', marginBottom: 12,
                background: dragOver ? 'rgba(45,127,249,0.08)' : 'transparent',
                transition: 'all 150ms ease',
              }}
            >
              <Upload size={16} color="rgba(232,232,232,0.5)" />
              <span className="os1-serif-micro" style={{ fontSize: 10, color: 'rgba(232,232,232,0.5)' }}>
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
                    background: 'rgba(232,232,232,0.06)',
                    border: '1px solid rgba(232,232,232,0.12)',
                    borderRadius: 8, padding: '5px 8px 5px 10px',
                  }}>
                    <span className="os1-serif-micro" style={{ fontSize: 10, color: '#e8e8e8' }}>{f.name}</span>
                    <button
                      onClick={() => removeFile(idx)}
                      disabled={feeding}
                      style={{ background: 'none', border: 'none', cursor: 'pointer', display: 'flex', padding: 2 }}
                    >
                      <X size={12} color="rgba(232,232,232,0.5)" />
                    </button>
                  </div>
                ))}
              </div>
            )}

            {/* Progress lines */}
            {progress.length > 0 && (
              <div style={{
                background: 'rgba(0,0,0,0.35)',
                border: '1px solid rgba(232,232,232,0.1)',
                borderRadius: 10, padding: '12px 14px',
                marginBottom: 12, maxHeight: 160, overflowY: 'auto',
              }} className="os1-scroll">
                {progress.map((item, idx) => (
                  <div key={idx} className="os1-serif-micro" style={{
                    fontSize: 10, lineHeight: 1.8,
                    color: item.status === 'error' ? '#ff6b6b'
                      : item.status === 'learned' ? '#2d7ff9'
                      : 'rgba(232,232,232,0.55)',
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
                  border: '1px solid rgba(232,232,232,0.1)',
                  borderRadius: 12, padding: '10px 24px',
                  color: 'rgba(232,232,232,0.7)', fontSize: 13,
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
                  background: feeding ? 'rgba(45,127,249,0.4)' : '#2d7ff9',
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
                <div className="os1-serif-micro" style={{ fontSize: 11, color: 'rgba(232,232,232,0.4)', padding: '20px 0', textAlign: 'center' }}>
                  Loading...
                </div>
              )}
              {!sourcesLoading && sources.length === 0 && (
                <div style={{ padding: '32px 0', textAlign: 'center' }}>
                  <BookOpen size={24} color="rgba(232,232,232,0.25)" style={{ marginBottom: 10 }} />
                  <div className="os1-serif-micro" style={{ fontSize: 11, color: 'rgba(232,232,232,0.4)' }}>
                    Nothing yet — paste something or drop a file in Feed Jarvis.
                  </div>
                </div>
              )}
              {sources.map(source => (
                <div key={source.id} style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12,
                  padding: '12px 14px', marginBottom: 8,
                  background: 'rgba(232,232,232,0.03)',
                  border: '1px solid rgba(232,232,232,0.1)',
                  borderRadius: 10,
                }}>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                      <span style={{
                        fontFamily: 'var(--font-pixel), monospace',
                        fontSize: 8, letterSpacing: '0.08em',
                        color: '#2d7ff9', border: '1px solid rgba(45,127,249,0.4)',
                        borderRadius: 4, padding: '2px 5px', flexShrink: 0,
                      }}>
                        {SOURCE_LABELS[source.source_type] || 'TEXT'}
                      </span>
                      <span style={{
                        color: '#e8e8e8', fontSize: 13,
                        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      }}>
                        {source.label}
                      </span>
                    </div>
                    <div className="os1-serif-micro" style={{ fontSize: 9, color: 'rgba(232,232,232,0.4)' }}>
                      {formatDate(source.created_at)} · {source.fact_count} fact{source.fact_count === 1 ? '' : 's'}
                    </div>
                  </div>
                  <button
                    onClick={() => handleDelete(source.id)}
                    disabled={deletingId === source.id}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', display: 'flex', flexShrink: 0, padding: 6 }}
                    title="Delete"
                  >
                    <Trash2 size={15} color="rgba(232,232,232,0.4)" />
                  </button>
                </div>
              ))}
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 16 }}>
              <button
                onClick={onClose}
                style={{
                  background: 'transparent',
                  border: '1px solid rgba(232,232,232,0.1)',
                  borderRadius: 12, padding: '10px 24px',
                  color: 'rgba(232,232,232,0.7)', fontSize: 13,
                  fontFamily: 'system-ui, sans-serif', cursor: 'pointer',
                  transition: 'all 200ms ease',
                }}
              >
                Close
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
