'use client'
import { useState } from 'react'
import { GripVertical, X, Plus, Trash2, RefreshCw, Check } from 'lucide-react'

const BACKEND = 'https://jarvis-backend-4oz6.onrender.com'

// Batch 68 — a user-created dashboard block. Five types, all on REAL data:
//   list (add/remove items + total) · note · metric · chart (bar/line/pie) · news (live web).
// Jarvis creates/edits these via the dashboard__control tool; list blocks are also editable
// directly here (add/remove) so the dashboard is interactive without chat.

function fmtAmount(n, unit) {
  const v = Number(n || 0)
  const s = v.toLocaleString(undefined, { maximumFractionDigits: 2 })
  if (unit === '$' || unit === 'USD') return `$${s}`
  return unit ? `${s} ${unit}` : s
}

function Header({ title, badge, onDelete }) {
  return (
    <div className="home-drag-handle" style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '10px 12px 8px', cursor: 'grab', flexShrink: 0,
      borderBottom: '1px solid var(--os1-border-soft, rgba(255,255,255,0.06))',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 7, minWidth: 0 }}>
        <GripVertical size={13} style={{ color: 'var(--os1-text-faint, #6E6E6C)', flexShrink: 0 }} />
        <span className="font-pixel" style={{ fontSize: 11.5, color: 'var(--os1-text, #F5F5F4)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {title}
        </span>
        {badge && <span className="os1-serif-micro" style={{ fontSize: 8, color: 'var(--home-accent, #5b9bff)', flexShrink: 0 }}>{badge}</span>}
      </div>
      <button onClick={(e) => { e.stopPropagation(); onDelete?.() }} onMouseDown={(e) => e.stopPropagation()}
        className="os1-iconbtn" title="Delete block (undo available)" style={{ padding: 2, color: 'var(--os1-text-faint, #6E6E6C)', flexShrink: 0 }}>
        <X size={13} />
      </button>
    </div>
  )
}

// ── list (e.g. My Expenses) ──────────────────────────────────────────────────
const inputStyle = {
  background: 'rgba(255,255,255,0.04)', border: '1px solid var(--os1-border-soft, rgba(255,255,255,0.08))',
  borderRadius: 7, padding: '5px 8px', color: 'var(--os1-text, #E8E8E6)', fontSize: 11, outline: 'none',
}
const editInputStyle = {
  ...inputStyle, background: 'rgba(255,255,255,0.06)', border: '1px solid var(--home-accent-border, rgba(207,138,91,0.3))',
  borderRadius: 6, padding: '3px 6px', fontSize: 11.5,
}

function fmtDue(d) {
  if (!d) return ''
  const parsed = new Date(`${d}T00:00:00`)
  if (Number.isNaN(parsed.getTime())) return d
  return parsed.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function ListBody({ block, userId, onChanged }) {
  const unit = block.config?.unit || '$'
  const items = block.data?.items || []
  const total = block.data?.total ?? items.reduce((s, i) => s + Number(i.amount || 0), 0)
  const [label, setLabel] = useState('')
  const [amount, setAmount] = useState('')
  const [dueDate, setDueDate] = useState('')
  const [busy, setBusy] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [editLabel, setEditLabel] = useState('')
  const [editAmount, setEditAmount] = useState('')
  const [editDue, setEditDue] = useState('')

  async function post(path, body) {
    setBusy(true)
    try {
      await fetch(`${BACKEND}/api/business/home/custom/${path}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, block_id: block.id, ...body }),
      })
      onChanged?.()
    } catch (e) { console.error(e) } finally { setBusy(false) }
  }

  const add = () => {
    if (!label.trim()) return
    const item = { label: label.trim() }
    if (amount !== '' && !Number.isNaN(Number(amount))) item.amount = Number(amount)
    if (dueDate) item.due_date = dueDate
    setLabel(''); setAmount(''); setDueDate('')
    post('add-item', { item })
  }

  const startEdit = (it) => {
    setEditingId(it.id)
    setEditLabel(it.label || '')
    setEditAmount(it.amount != null ? String(it.amount) : '')
    setEditDue(it.due_date || '')
  }

  const saveEdit = (it) => {
    const item = { id: it.id, new_label: editLabel.trim() || it.label, due_date: editDue || '' }
    if (editAmount !== '' && !Number.isNaN(Number(editAmount))) item.amount = Number(editAmount)
    setEditingId(null)
    post('update-item', { item })
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div className="os1-scroll" style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '8px 12px' }}>
        {items.length === 0 && (
          <div className="os1-serif-micro" style={{ fontSize: 10, color: 'var(--os1-text-faint, #6E6E6C)', padding: '6px 0' }}>
            Empty — add your first item below, or ask Jarvis to fill it.
          </div>
        )}
        {items.map((it) => editingId === it.id ? (
          <div key={it.id} style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '5px 0', borderBottom: '1px solid var(--os1-border-soft, rgba(255,255,255,0.05))' }}>
            <input autoFocus value={editLabel} onChange={(e) => setEditLabel(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') saveEdit(it); if (e.key === 'Escape') setEditingId(null) }}
              onMouseDown={(e) => e.stopPropagation()}
              style={{ ...editInputStyle, flex: 1, minWidth: 0 }} />
            <input value={editAmount} onChange={(e) => setEditAmount(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') saveEdit(it); if (e.key === 'Escape') setEditingId(null) }}
              placeholder={unit} inputMode="decimal" onMouseDown={(e) => e.stopPropagation()}
              style={{ ...editInputStyle, width: 46 }} />
            <input type="date" value={editDue} onChange={(e) => setEditDue(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') saveEdit(it); if (e.key === 'Escape') setEditingId(null) }}
              onMouseDown={(e) => e.stopPropagation()}
              style={{ ...editInputStyle, width: 88, fontSize: 9.5, colorScheme: 'dark' }} />
            <button onClick={() => saveEdit(it)} className="os1-iconbtn" title="Save" style={{ padding: 1, color: 'var(--home-accent, #5b9bff)' }}>
              <Check size={13} />
            </button>
          </div>
        ) : (
          <div key={it.id} onClick={() => startEdit(it)} title="Click to edit"
            style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, padding: '5px 0', borderBottom: '1px solid var(--os1-border-soft, rgba(255,255,255,0.05))', cursor: 'pointer' }}>
            <span style={{ minWidth: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
              <span style={{ fontSize: 12, color: 'var(--os1-text-dim, #C8C8C6)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{it.label}</span>
              {it.due_date && <span className="os1-serif-micro" style={{ fontSize: 9, color: 'var(--os1-text-faint, #6E6E6C)' }}>Due {fmtDue(it.due_date)}</span>}
            </span>
            <span style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
              {it.amount != null && <span className="font-pixel" style={{ fontSize: 11, color: 'var(--os1-text, #E8E8E6)' }}>{fmtAmount(it.amount, unit)}</span>}
              <button onClick={(e) => { e.stopPropagation(); post('remove-item', { item: { id: it.id } }) }} className="os1-iconbtn" title="Remove" style={{ padding: 1, color: 'var(--os1-text-faint, #6E6E6C)' }}>
                <Trash2 size={11} />
              </button>
            </span>
          </div>
        ))}
      </div>
      {items.some(i => i.amount != null) && (
        <div style={{ display: 'flex', justifyContent: 'space-between', padding: '7px 12px', borderTop: '1px solid var(--os1-border-soft, rgba(255,255,255,0.08))' }}>
          <span className="os1-serif-micro" style={{ fontSize: 9, color: 'var(--os1-text-faint, #6E6E6C)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Total</span>
          <span className="font-pixel" style={{ fontSize: 12, color: 'var(--home-accent, #5b9bff)' }}>{fmtAmount(total, unit)}</span>
        </div>
      )}
      <div style={{ display: 'flex', gap: 5, padding: '8px 12px', borderTop: '1px solid var(--os1-border-soft, rgba(255,255,255,0.06))' }}>
        <input value={label} onChange={(e) => setLabel(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && add()}
          placeholder="Item" onMouseDown={(e) => e.stopPropagation()}
          style={{ ...inputStyle, flex: 1, minWidth: 0 }} />
        <input value={amount} onChange={(e) => setAmount(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && add()}
          placeholder={unit} inputMode="decimal" onMouseDown={(e) => e.stopPropagation()}
          style={{ ...inputStyle, width: 48 }} />
        <input type="date" value={dueDate} onChange={(e) => setDueDate(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && add()}
          onMouseDown={(e) => e.stopPropagation()} title="Due date (optional)"
          style={{ ...inputStyle, width: 84, padding: '5px 4px', fontSize: 9.5, colorScheme: 'dark' }} />
        <button onClick={add} disabled={busy} className="os1-iconbtn" title="Add"
          style={{ padding: '5px 8px', border: '1px solid var(--home-accent-border, rgba(207,138,91,0.3))', borderRadius: 7, color: 'var(--home-accent, #5b9bff)' }}>
          <Plus size={14} />
        </button>
      </div>
    </div>
  )
}

// ── note ─────────────────────────────────────────────────────────────────────
function NoteBody({ block }) {
  const text = block.data?.text || ''
  return (
    <div className="os1-scroll" style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '10px 12px' }}>
      {text ? (
        <p style={{ margin: 0, fontSize: 12.5, lineHeight: 1.55, color: 'var(--os1-text-dim, #C8C8C6)', whiteSpace: 'pre-wrap' }}>{text}</p>
      ) : (
        <span className="os1-serif-micro" style={{ fontSize: 10, color: 'var(--os1-text-faint, #6E6E6C)' }}>Empty note — tell Jarvis what to write here.</span>
      )}
    </div>
  )
}

// ── metric ───────────────────────────────────────────────────────────────────
function MetricBody({ block }) {
  const d = block.data || {}
  const delta = d.delta
  const deltaNum = typeof delta === 'number' ? delta : parseFloat(delta)
  const up = !Number.isNaN(deltaNum) ? deltaNum >= 0 : null
  return (
    <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', justifyContent: 'center', padding: '8px 14px' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
        <span className="font-pixel" style={{ fontSize: 30, color: 'var(--os1-text, #F5F5F4)', lineHeight: 1 }}>
          {d.value != null ? String(d.value) : '—'}
        </span>
        {d.unit && <span className="font-pixel" style={{ fontSize: 13, color: 'var(--os1-text-dim, #A8A8A6)' }}>{d.unit}</span>}
      </div>
      {d.label && <div className="os1-serif-micro" style={{ fontSize: 10, color: 'var(--os1-text-faint, #6E6E6C)', marginTop: 6 }}>{d.label}</div>}
      {delta != null && delta !== '' && (
        <div className="font-pixel" style={{ fontSize: 11, marginTop: 6, color: up == null ? 'var(--os1-text-dim,#A8A8A6)' : up ? '#7fb069' : '#e0666c' }}>
          {up == null ? delta : `${up ? '▲' : '▼'} ${delta}`}
        </div>
      )}
    </div>
  )
}

// ── chart (bar / line / pie) ─────────────────────────────────────────────────
function ChartBody({ block }) {
  const series = (block.data?.series || []).filter(p => p && p.value != null)
  const kind = block.config?.kind || 'bar'
  const accent = 'var(--home-accent, #5b9bff)'
  const palette = ['#5b9bff', '#7fb069', '#e0a35b', '#c77dff', '#5bd6c0', '#e0666c']
  if (series.length === 0) {
    return <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--os1-text-faint, #6E6E6C)', fontSize: 11 }} className="os1-serif-micro">No data yet — give Jarvis the numbers.</div>
  }
  const W = 300, H = 150, pad = 22
  const max = Math.max(...series.map(p => Number(p.value)), 1)
  const innerW = W - pad * 2, innerH = H - pad * 2

  let body
  if (kind === 'pie') {
    const total = series.reduce((s, p) => s + Number(p.value), 0) || 1
    let a0 = -Math.PI / 2
    const cx = W / 2, cy = H / 2, r = Math.min(innerW, innerH) / 2
    body = series.map((p, i) => {
      const frac = Number(p.value) / total
      const a1 = a0 + frac * Math.PI * 2
      const x0 = cx + r * Math.cos(a0), y0 = cy + r * Math.sin(a0)
      const x1 = cx + r * Math.cos(a1), y1 = cy + r * Math.sin(a1)
      const large = frac > 0.5 ? 1 : 0
      const d = `M ${cx} ${cy} L ${x0.toFixed(1)} ${y0.toFixed(1)} A ${r} ${r} 0 ${large} 1 ${x1.toFixed(1)} ${y1.toFixed(1)} Z`
      a0 = a1
      return <path key={i} d={d} fill={palette[i % palette.length]} opacity="0.9" />
    })
  } else if (kind === 'line') {
    const step = series.length > 1 ? innerW / (series.length - 1) : 0
    const pts = series.map((p, i) => [pad + i * step, pad + innerH - (Number(p.value) / max) * innerH])
    body = (
      <>
        <polyline fill="none" stroke={accent} strokeWidth="2" points={pts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ')} />
        {pts.map(([x, y], i) => <circle key={i} cx={x} cy={y} r="2.5" fill={accent} />)}
      </>
    )
  } else {
    const bw = innerW / series.length
    body = series.map((p, i) => {
      const h = (Number(p.value) / max) * innerH
      return <rect key={i} x={pad + i * bw + bw * 0.18} y={pad + innerH - h} width={bw * 0.64} height={Math.max(1, h)} rx="2" fill={accent} opacity="0.9" />
    })
  }

  return (
    <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', padding: '8px 10px' }}>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', flex: 1, minHeight: 0 }} preserveAspectRatio="xMidYMid meet">
        {body}
      </svg>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '2px 10px', justifyContent: 'center', marginTop: 4 }}>
        {series.slice(0, 6).map((p, i) => (
          <span key={i} className="os1-serif-micro" style={{ fontSize: 8.5, color: 'var(--os1-text-faint, #6E6E6C)' }}>
            {kind === 'pie' && <span style={{ display: 'inline-block', width: 7, height: 7, borderRadius: 2, background: palette[i % palette.length], marginRight: 3, verticalAlign: 'middle' }} />}
            {p.label}: {Number(p.value).toLocaleString()}
          </span>
        ))}
      </div>
    </div>
  )
}

// ── news (live web) ──────────────────────────────────────────────────────────
function NewsBody({ block }) {
  const d = block.data || {}
  return (
    <div className="os1-scroll" style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '10px 12px' }}>
      <div className="os1-serif-micro" style={{ fontSize: 9, color: 'var(--home-accent, #5b9bff)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
        {d.topic || block.config?.topic || 'News'}
      </div>
      {d.summary ? (
        <p style={{ margin: 0, fontSize: 12, lineHeight: 1.5, color: 'var(--os1-text-dim, #C8C8C6)', whiteSpace: 'pre-wrap' }}>{d.summary}</p>
      ) : (
        <span className="os1-serif-micro" style={{ fontSize: 10, color: 'var(--os1-text-faint, #6E6E6C)' }}>Ask Jarvis to pull the latest on this topic.</span>
      )}
    </div>
  )
}

export default function CustomBlock({ block, userId, onChanged, onDelete }) {
  const accent = block.style?.accent
  const wrapStyle = {
    height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden',
    background: '#15151a', border: '1px solid var(--os1-border-soft, rgba(255,255,255,0.08))', borderRadius: 14,
  }
  if (accent) wrapStyle['--home-accent'] = accent

  const TYPE_LABEL = { list: 'list', note: 'note', metric: 'metric', chart: 'chart', news: 'live' }
  return (
    <div className="os1-card" style={wrapStyle}>
      <Header title={block.title || 'Block'} badge={TYPE_LABEL[block.custom_type]} onDelete={() => onDelete?.(block.id)} />
      {block.custom_type === 'list' && <ListBody block={block} userId={userId} onChanged={onChanged} />}
      {block.custom_type === 'note' && <NoteBody block={block} />}
      {block.custom_type === 'metric' && <MetricBody block={block} />}
      {block.custom_type === 'chart' && <ChartBody block={block} />}
      {block.custom_type === 'news' && <NewsBody block={block} />}
    </div>
  )
}
