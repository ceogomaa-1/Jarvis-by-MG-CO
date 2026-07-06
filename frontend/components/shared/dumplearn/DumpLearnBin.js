'use client'

import { useEffect, useRef, useState } from 'react'
import ComprehensionKnob from './ComprehensionKnob'
import { formatFileSize, truncateMiddle } from '../../../lib/attachments'
import {
  createBin, getBinStatus, updateBin, deleteItem,
  addFileItem, addUrlItem, addTextItem,
} from '../../../lib/dumpLearnApi'

// ─────────────────────────────────────────────────────────────────────────────
// Act 1 — The Bin. A literal intake bin: drag/drop or "+" anything in, watch
// it fall in and get digested, then twist the knob and hit "Learn This".
// ─────────────────────────────────────────────────────────────────────────────

const CREAM = '#F3EAD9'
const ACCENT = '#ff9072'

const KIND_ICON = { pdf: '📄', docx: '📝', pptx: '📊', url: '🔗', youtube: '▶', image: '🖼', text: '✎' }

function seededRotation(id) {
  let h = 0
  const s = String(id)
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0
  return ((h % 1200) / 100) - 6 // -6..6 deg
}

function mergeItems(prev, statusItems) {
  const byId = new Map(statusItems.map(s => [s.id, s]))
  const merged = prev.map(p => (byId.has(p.id) ? { ...p, ...byId.get(p.id) } : p))
  const known = new Set(merged.map(m => m.id))
  const extra = statusItems.filter(s => !known.has(s.id))
  return [...merged, ...extra]
}

// Honest comparison: how many tokens the raw file would cost if base64-encoded
// and sent as-is (~4/3 size inflation, ~4 chars/token) vs. what our clean-text
// extraction actually costs. Only shown for real file uploads (has byte size).
function shrinkStats(item) {
  if (!item.original_size_bytes) return null
  const naive = Math.round((item.original_size_bytes * 4) / 3 / 4)
  if (naive <= 0) return null
  const pct = Math.max(0, Math.min(99, Math.round((1 - (item.token_estimate || 0) / naive) * 100)))
  return { naive, pct }
}

function StatusChip({ item }) {
  if (item.status === 'pending' || item.status === 'parsing') {
    return (
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11.5, color: 'rgba(243,234,217,0.55)' }}>
        <span style={{ width: 6, height: 6, borderRadius: '50%', background: ACCENT, animation: 'dlPulse 1s ease-in-out infinite' }} />
        reading…
      </span>
    )
  }
  if (item.status === 'error') {
    return <span style={{ fontSize: 11.5, color: '#ff6b6b' }}>⚠ {item.error || 'Could not read this'}</span>
  }
  const shrink = shrinkStats(item)
  return (
    <div>
      <div style={{ fontSize: 11.5, color: 'rgba(243,234,217,0.6)' }}>
        {item.original_size_bytes ? `${formatFileSize(item.original_size_bytes)} → ` : ''}
        ~{(item.token_estimate || 0).toLocaleString()} tokens
        {shrink ? ` · ${shrink.pct}% leaner than a raw upload` : ''}
      </div>
      {shrink && (
        <div style={{ marginTop: 4, width: 120, height: 3, borderRadius: 2, background: 'rgba(255,255,255,0.08)', overflow: 'hidden' }}>
          <div style={{
            height: '100%', borderRadius: 2, background: `linear-gradient(90deg, ${ACCENT}, #6fd6a8)`,
            width: `${100 - shrink.pct}%`, transition: 'width 900ms cubic-bezier(.22,1,.36,1)',
          }} />
        </div>
      )}
    </div>
  )
}

function ScrapCard({ item, onRemove }) {
  const rot = seededRotation(item.id)
  return (
    <div style={{ animation: 'scrapFall 620ms cubic-bezier(.22,1,.36,1) both' }}>
      <div
        style={{
          transform: `rotate(${rot}deg)`, background: 'rgba(255,255,255,0.05)',
          border: '1px solid rgba(255,255,255,0.09)', borderRadius: 12, padding: '10px 12px',
          display: 'flex', alignItems: 'flex-start', gap: 10, minWidth: 200, maxWidth: 240,
          boxShadow: '0 4px 14px rgba(0,0,0,0.25)', position: 'relative',
        }}
      >
        <span style={{ fontSize: 18, lineHeight: 1 }}>{KIND_ICON[item.kind] || '📎'}</span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontFamily: 'var(--sans)', fontSize: 13, fontWeight: 600, color: CREAM, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {truncateMiddle(item.source_name || item.kind, 28)}
          </div>
          <div style={{ marginTop: 3 }}><StatusChip item={item} /></div>
        </div>
        <button
          onClick={() => onRemove(item.id)}
          aria-label="remove"
          style={{ position: 'absolute', top: 4, right: 6, background: 'none', border: 0, color: 'rgba(243,234,217,0.4)', cursor: 'pointer', fontSize: 13, padding: 2 }}
        >✕</button>
      </div>
    </div>
  )
}

export default function DumpLearnBin({ userId, onLearnThis, onClose }) {
  const [bin, setBin] = useState(null)
  const [items, setItems] = useState([])
  const [level, setLevel] = useState('graduate')
  const [addMenuOpen, setAddMenuOpen] = useState(false)
  const [linkMode, setLinkMode] = useState(false)
  const [textMode, setTextMode] = useState(false)
  const [linkValue, setLinkValue] = useState('')
  const [textValue, setTextValue] = useState('')
  const [dragOver, setDragOver] = useState(false)
  const [toast, setToast] = useState(null)
  const [starting, setStarting] = useState(false)

  const fileInputRef = useRef(null)
  const pollRef = useRef(null)
  const itemsRef = useRef([])
  useEffect(() => { itemsRef.current = items }, [items])

  useEffect(() => {
    let cancelled = false
    createBin(userId, 'New bin').then(b => { if (!cancelled) setBin(b) }).catch(() => {
      if (!cancelled) setToast('Could not start a bin — try again.')
    })
    return () => { cancelled = true }
  }, [userId])

  useEffect(() => {
    if (!bin?.id) return
    const tick = async () => {
      try {
        const status = await getBinStatus(userId, bin.id)
        setItems(prev => mergeItems(prev, status.items || []))
      } catch { /* best-effort */ }
    }
    tick()
    pollRef.current = setInterval(tick, 1200)
    return () => clearInterval(pollRef.current)
  }, [bin?.id, userId])

  const showToast = (msg) => { setToast(msg); setTimeout(() => setToast(null), 3200) }

  const pushOptimistic = (item) => setItems(prev => (prev.some(p => p.id === item.id) ? prev : [...prev, item]))

  const handleFiles = async (fileList) => {
    if (!bin?.id) return
    for (const file of Array.from(fileList)) {
      try {
        const item = await addFileItem(userId, bin.id, file)
        pushOptimistic(item)
      } catch (e) {
        showToast(e.message || `Could not add ${file.name}`)
      }
    }
  }

  const submitLink = async () => {
    const url = linkValue.trim()
    if (!url || !bin?.id) return
    setLinkValue(''); setLinkMode(false); setAddMenuOpen(false)
    try {
      const item = await addUrlItem(userId, bin.id, url)
      pushOptimistic(item)
    } catch (e) {
      showToast(e.message || 'Could not add that link')
    }
  }

  const submitText = async () => {
    const body = textValue.trim()
    if (!body || !bin?.id) return
    setTextValue(''); setTextMode(false); setAddMenuOpen(false)
    try {
      const item = await addTextItem(userId, bin.id, body, body.slice(0, 40))
      pushOptimistic(item)
    } catch (e) {
      showToast(e.message || 'Could not add that text')
    }
  }

  const removeItem = async (itemId) => {
    setItems(prev => prev.filter(i => i.id !== itemId))
    if (bin?.id) deleteItem(userId, bin.id, itemId).catch(() => {})
  }

  const onDrop = (e) => {
    e.preventDefault(); setDragOver(false)
    if (e.dataTransfer?.files?.length) handleFiles(e.dataTransfer.files)
  }

  const readyCount = items.filter(i => i.status === 'ready').length
  const totalTokens = items.filter(i => i.status === 'ready').reduce((s, i) => s + (i.token_estimate || 0), 0)
  const pendingCount = items.filter(i => i.status === 'pending' || i.status === 'parsing').length

  const learnThis = async () => {
    if (!bin?.id || readyCount === 0 || starting) return
    setStarting(true)
    try {
      await updateBin(userId, bin.id, { level })
      onLearnThis(bin.id, level)
    } catch {
      setStarting(false)
      showToast('Could not start the lesson — try again.')
    }
  }

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
      onDragLeave={() => setDragOver(false)}
      onDrop={onDrop}
      style={{
        position: 'fixed', inset: 0, zIndex: 30, background: '#1A1A1A',
        display: 'flex', flexDirection: 'column', animation: 'fadeUp 260ms ease both',
      }}
    >
      <style>{`
        @keyframes scrapFall {
          0% { opacity: 0; transform: translateY(-46px) scale(0.85); }
          60% { opacity: 1; transform: translateY(6px) scale(1.02); }
          100% { opacity: 1; transform: translateY(0) scale(1); }
        }
        @keyframes dlPulse { 0%,100% { opacity: 1; } 50% { opacity: 0.35; } }
        @keyframes binGlow { 0%,100% { box-shadow: 0 0 0 rgba(255,144,114,0); } 50% { box-shadow: 0 0 32px rgba(255,144,114,0.18); } }
      `}</style>

      {/* Header */}
      <div style={{ height: 56, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 16px' }}>
        <button onClick={onClose} aria-label="close" style={{ background: 'none', border: 0, color: CREAM, cursor: 'pointer', fontSize: 20, padding: 6 }}>✕</button>
        <input
          value={bin?.title || ''}
          onChange={(e) => setBin(b => ({ ...b, title: e.target.value }))}
          onBlur={() => bin?.id && updateBin(userId, bin.id, { title: bin.title }).catch(() => {})}
          placeholder="New bin"
          style={{
            background: 'none', border: 'none', outline: 'none', color: CREAM, textAlign: 'center',
            fontFamily: 'var(--font-display-round), var(--sans)', fontSize: 16, fontWeight: 600, width: 220,
          }}
        />
        <div style={{ width: 32 }} />
      </div>

      {toast && (
        <div style={{ margin: '0 16px 8px', padding: '10px 14px', borderRadius: 12, background: 'rgba(90,0,0,0.25)', border: '1px solid rgba(239,68,68,0.4)', color: CREAM, fontFamily: 'var(--sans)', fontSize: 13 }}>
          {toast}
        </div>
      )}

      {/* Intake area */}
      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '8px 16px 24px' }}>
        <div style={{
          marginTop: 8, width: '100%', maxWidth: 440, minHeight: 220, borderRadius: 24,
          border: `2px dashed ${dragOver ? ACCENT : 'rgba(255,255,255,0.16)'}`,
          background: dragOver ? 'rgba(255,144,114,0.06)' : 'rgba(255,255,255,0.02)',
          transition: 'border-color 200ms ease, background 200ms ease',
          animation: dragOver ? 'binGlow 1.1s ease-in-out infinite' : 'none',
          display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: items.length ? 'flex-start' : 'center',
          padding: 20, gap: 10,
        }}>
          {items.length === 0 ? (
            <div style={{ textAlign: 'center', color: 'rgba(243,234,217,0.5)', fontFamily: 'var(--sans)' }}>
              <div style={{ fontSize: 34, marginBottom: 8 }}>🗑</div>
              <div style={{ fontSize: 14.5 }}>Drop anything in — PDFs, docx, slides, links, YouTube, or just paste text.</div>
            </div>
          ) : (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, justifyContent: 'center', width: '100%' }}>
              {items.map(it => <ScrapCard key={it.id} item={it} onRemove={removeItem} />)}
            </div>
          )}
        </div>

        {/* Add menu */}
        <div style={{ position: 'relative', marginTop: 18 }}>
          {!linkMode && !textMode && (
            <button
              onClick={() => setAddMenuOpen(o => !o)}
              style={{
                width: 52, height: 52, borderRadius: '50%', background: ACCENT, border: 'none',
                color: '#1A1A1A', fontSize: 26, fontWeight: 300, cursor: 'pointer',
                boxShadow: '0 6px 18px rgba(255,144,114,0.35)',
              }}
              aria-label="add material"
            >+</button>
          )}

          {addMenuOpen && !linkMode && !textMode && (
            <div style={{
              position: 'absolute', bottom: 62, left: '50%', transform: 'translateX(-50%)',
              display: 'flex', flexDirection: 'column', gap: 8, background: '#242424',
              border: '1px solid rgba(255,255,255,0.1)', borderRadius: 14, padding: 8, minWidth: 190,
              animation: 'fadeUp 160ms ease both', boxShadow: '0 10px 28px rgba(0,0,0,0.4)',
            }}>
              {[
                { label: '📎 Upload files', action: () => { fileInputRef.current?.click(); setAddMenuOpen(false) } },
                { label: '🔗 Paste a link', action: () => { setLinkMode(true) } },
                { label: '✎ Paste text', action: () => { setTextMode(true) } },
              ].map(opt => (
                <button
                  key={opt.label}
                  onClick={opt.action}
                  style={{ background: 'none', border: 0, color: CREAM, textAlign: 'left', padding: '8px 10px', borderRadius: 8, cursor: 'pointer', fontFamily: 'var(--sans)', fontSize: 13.5 }}
                  onMouseEnter={e => { e.currentTarget.style.background = 'rgba(255,255,255,0.06)' }}
                  onMouseLeave={e => { e.currentTarget.style.background = 'none' }}
                >{opt.label}</button>
              ))}
            </div>
          )}

          {linkMode && (
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <input
                autoFocus value={linkValue} onChange={e => setLinkValue(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') submitLink(); if (e.key === 'Escape') setLinkMode(false) }}
                placeholder="Paste an article or YouTube link…"
                style={{ width: 260, padding: '10px 12px', borderRadius: 10, background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.14)', color: CREAM, fontFamily: 'var(--sans)', fontSize: 13.5, outline: 'none' }}
              />
              <button onClick={submitLink} style={{ background: ACCENT, border: 0, borderRadius: 10, padding: '10px 14px', color: '#1A1A1A', fontWeight: 600, cursor: 'pointer' }}>Add</button>
              <button onClick={() => { setLinkMode(false); setLinkValue('') }} style={{ background: 'none', border: 0, color: 'rgba(243,234,217,0.5)', cursor: 'pointer' }}>✕</button>
            </div>
          )}

          {textMode && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, alignItems: 'center' }}>
              <textarea
                autoFocus value={textValue} onChange={e => setTextValue(e.target.value)}
                placeholder="Paste text to study…" rows={4}
                style={{ width: 280, padding: '10px 12px', borderRadius: 10, background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.14)', color: CREAM, fontFamily: 'var(--sans)', fontSize: 13.5, outline: 'none', resize: 'vertical' }}
              />
              <div style={{ display: 'flex', gap: 8 }}>
                <button onClick={submitText} style={{ background: ACCENT, border: 0, borderRadius: 10, padding: '8px 14px', color: '#1A1A1A', fontWeight: 600, cursor: 'pointer' }}>Add</button>
                <button onClick={() => { setTextMode(false); setTextValue('') }} style={{ background: 'none', border: 0, color: 'rgba(243,234,217,0.5)', cursor: 'pointer' }}>Cancel</button>
              </div>
            </div>
          )}
        </div>

        <input
          ref={fileInputRef} type="file" multiple style={{ display: 'none' }}
          accept=".pdf,.docx,.pptx,image/*"
          onChange={(e) => { if (e.target.files?.length) handleFiles(e.target.files); e.target.value = '' }}
        />
      </div>

      {/* Footer — knob + running total + Learn This */}
      <div style={{ flexShrink: 0, borderTop: '1px solid rgba(255,255,255,0.08)', padding: '16px 20px 22px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 14 }}>
        <ComprehensionKnob level={level} onChange={setLevel} />
        <div style={{ fontFamily: 'var(--sans)', fontSize: 12.5, color: 'rgba(243,234,217,0.55)' }}>
          {items.length === 0
            ? 'Nothing in the bin yet'
            : `${readyCount} ready · ~${totalTokens.toLocaleString()} tokens${pendingCount ? ` · ${pendingCount} still reading…` : ''}`}
        </div>
        <button
          onClick={learnThis}
          disabled={readyCount === 0 || starting}
          style={{
            width: '100%', maxWidth: 320, padding: '14px 0', borderRadius: 999, border: 'none',
            background: readyCount === 0 ? 'rgba(255,144,114,0.25)' : ACCENT,
            color: readyCount === 0 ? 'rgba(26,26,26,0.6)' : '#1A1A1A',
            fontFamily: 'var(--sans)', fontSize: 15, fontWeight: 700, letterSpacing: '0.02em',
            cursor: readyCount === 0 || starting ? 'default' : 'pointer',
            boxShadow: readyCount === 0 ? 'none' : '0 8px 22px rgba(255,144,114,0.3)',
            transition: 'all 200ms ease',
          }}
        >
          {starting ? 'Digesting…' : 'Learn This'}
        </button>
      </div>
    </div>
  )
}
