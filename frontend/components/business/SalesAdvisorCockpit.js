'use client'
import { useEffect, useMemo, useRef, useState, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  X, MessageSquare, RefreshCw, Plus, Trash2, Copy, Crosshair, ChevronRight,
} from 'lucide-react'
import ChatCanvas from './ChatCanvas'

import { BACKEND } from '@/lib/backend'

// Sales Advisor — the closer cockpit. Mirrors LeadsCockpit 1:1: a full-screen shell with
// the SAME docked ChatCanvas on the right. Main panel: point Rue at ONE business (Google
// Maps link and/or name + any intel you have) → the backend deep-researches it (Places
// profile + reviews, stealth website scrape, web intel, digital audit) and generates a
// closer-grade pitch report (kill shots, offer, 10-12 slide deck with exact words to say,
// call script, objection kills). Left rail = report history; poll while a job runs; the
// docked chat fires onSalesChanged so panel and chat always agree.
// Additive — does NOT touch the CRM cockpit, Leads cockpit, Personal, or onboarding.

const SECTIONS = [
  { key: 'snapshot',   label: 'Snapshot' },
  { key: 'kill_shots', label: 'Kill Shots' },
  { key: 'offer',      label: 'The Offer' },
  { key: 'deck',       label: 'Pitch Deck' },
  { key: 'script',     label: 'Call Script' },
  { key: 'objections', label: 'Objections' },
  { key: 'close',      label: 'Close' },
]

const STATUS_STYLE = {
  running:  { fg: '#FFB340', label: 'running' },
  complete: { fg: '#34C759', label: 'ready' },
  failed:   { fg: '#FF453A', label: 'failed' },
}

function fmtDate(iso) {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  } catch { return '' }
}

function CopyBtn({ text }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      onClick={(e) => {
        e.stopPropagation()
        try { navigator.clipboard.writeText(text || '') } catch {}
        setCopied(true); setTimeout(() => setCopied(false), 1200)
      }}
      className="os1-iconbtn" title="Copy"
      style={{ width: 22, height: 22, flexShrink: 0 }}
    >
      {copied
        ? <span className="os1-serif-micro" style={{ fontSize: 8, color: '#34C759' }}>ok</span>
        : <Copy size={11} />}
    </button>
  )
}

function SectionTitle({ children, sub }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <div className="font-pixel" style={{ fontSize: 13, color: 'var(--os1-text, #F5F5F4)' }}>{children}</div>
      {sub && <div className="os1-serif-micro" style={{ fontSize: 10, color: 'var(--os1-text-faint, #6E6E6C)', marginTop: 3 }}>{sub}</div>}
    </div>
  )
}

// "Say this" — the words Mohamed literally says on the call. Visually distinct + copyable.
function SayThis({ text }) {
  if (!text) return null
  return (
    <div style={{
      display: 'flex', alignItems: 'flex-start', gap: 8, marginTop: 8,
      background: 'rgba(45,127,249,0.07)', borderLeft: '2px solid var(--os1-accent, #2d7ff9)',
      borderRadius: '0 8px 8px 0', padding: '9px 10px',
    }}>
      <div className="os1-serif-micro" style={{ fontSize: 11.5, color: 'var(--os1-text, #F5F5F4)', lineHeight: 1.55, flex: 1, fontStyle: 'italic' }}>
        “{text}”
      </div>
      <CopyBtn text={text} />
    </div>
  )
}

function ReportView({ report }) {
  const [section, setSection] = useState('snapshot')
  const snap = report?.business_snapshot || {}
  const pulse = snap.review_pulse || {}
  const offer = report?.offer || {}
  const script = report?.call_script || {}

  const body = () => {
    if (section === 'snapshot') return (
      <div>
        <SectionTitle sub={[snap.category, snap.city].filter(Boolean).join(' · ')}>{snap.name || 'Snapshot'}</SectionTitle>
        {snap.summary && (
          <div className="os1-serif-micro" style={{ fontSize: 12, color: 'var(--os1-text-dim, #A8A8A6)', lineHeight: 1.6, marginBottom: 16 }}>
            {snap.summary}
          </div>
        )}
        {(pulse.rating != null || (pulse.themes || []).length > 0) && (
          <div className="os1-card" style={{ padding: '13px 15px', marginBottom: 10 }}>
            <div className="font-pixel" style={{ fontSize: 11, color: 'var(--os1-text, #F5F5F4)', marginBottom: 8 }}>
              Review pulse{pulse.rating != null ? ` — ${pulse.rating}★ · ${pulse.count || 0} reviews` : ''}
            </div>
            {(pulse.themes || []).map((t, i) => (
              <div key={i} className="os1-serif-micro" style={{ fontSize: 10.5, color: 'var(--os1-text-dim, #A8A8A6)', lineHeight: 1.5 }}>· {t}</div>
            ))}
            {(pulse.quotes || []).map((q, i) => (
              <div key={i} className="os1-serif-micro" style={{ fontSize: 10.5, color: 'var(--os1-text-faint, #6E6E6C)', lineHeight: 1.5, marginTop: 6, fontStyle: 'italic' }}>“{q}”</div>
            ))}
          </div>
        )}
        {report?.confidence_notes && (
          <div className="os1-serif-micro" style={{ fontSize: 10, color: '#FFB340', lineHeight: 1.55, marginTop: 12 }}>
            Before the call: {report.confidence_notes}
          </div>
        )}
      </div>
    )

    if (section === 'kill_shots') return (
      <div>
        <SectionTitle sub="The gaps you found — each one maps to an MG&CO service and a cost of pain.">Kill Shots</SectionTitle>
        {(report?.kill_shots || []).map((k, i) => (
          <div key={i} className="os1-card" style={{ padding: '14px 16px', marginBottom: 10, borderLeft: '2px solid #FF453A' }}>
            <div className="font-pixel" style={{ fontSize: 12, color: 'var(--os1-text, #F5F5F4)', marginBottom: 6 }}>{i + 1}. {k.gap}</div>
            <div className="os1-serif-micro" style={{ fontSize: 10.5, color: 'var(--os1-text-dim, #A8A8A6)', lineHeight: 1.55 }}>
              Evidence: {k.evidence}
            </div>
            <div className="os1-serif-micro" style={{ fontSize: 10.5, color: '#FF9F0A', lineHeight: 1.55, marginTop: 4 }}>
              Cost of pain: {k.cost_of_pain}
            </div>
            <div className="os1-serif-micro" style={{ fontSize: 10.5, color: '#34C759', lineHeight: 1.55, marginTop: 4 }}>
              The fix: {k.mgco_service}
            </div>
            <SayThis text={k.one_liner} />
          </div>
        ))}
      </div>
    )

    if (section === 'offer') return (
      <div>
        <SectionTitle sub={offer.dream_outcome}>{offer.name || 'The Offer'}</SectionTitle>
        {(offer.stack || []).map((s, i) => (
          <div key={i} className="os1-card" style={{ padding: '11px 14px', marginBottom: 8 }}>
            <div className="font-pixel" style={{ fontSize: 11.5, color: 'var(--os1-text, #F5F5F4)' }}>{s.item}</div>
            <div className="os1-serif-micro" style={{ fontSize: 10.5, color: 'var(--os1-text-dim, #A8A8A6)', lineHeight: 1.5, marginTop: 3 }}>{s.why_it_matters}</div>
          </div>
        ))}
        {[['Guarantee', offer.guarantee, '#34C759'], ['Why now', offer.urgency, '#FFB340'],
          ['Price frame', offer.price_frame, 'var(--os1-accent, #2d7ff9)'], ['ROI math', offer.roi_math, 'var(--os1-text-dim, #A8A8A6)']]
          .filter(([, v]) => v).map(([label, v, color]) => (
            <div key={label} style={{ marginTop: 12 }}>
              <div className="font-pixel" style={{ fontSize: 10.5, color, marginBottom: 4 }}>{label}</div>
              <div className="os1-serif-micro" style={{ fontSize: 11, color: 'var(--os1-text-dim, #A8A8A6)', lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>{v}</div>
            </div>
          ))}
      </div>
    )

    if (section === 'deck') return (
      <div>
        <SectionTitle sub="Story arc, not feature tour. Each slide: the goal, the exact words, the backup points.">Pitch Deck</SectionTitle>
        {(report?.pitch_deck || []).map((s, i) => (
          <div key={i} className="os1-card" style={{ padding: '14px 16px', marginBottom: 10 }}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
              <span className="font-pixel" style={{ fontSize: 10, color: 'var(--os1-accent, #2d7ff9)', flexShrink: 0 }}>
                {String(s.n ?? i + 1).padStart(2, '0')}
              </span>
              <span className="font-pixel" style={{ fontSize: 12, color: 'var(--os1-text, #F5F5F4)' }}>{s.title}</span>
            </div>
            {s.goal && (
              <div className="os1-serif-micro" style={{ fontSize: 10, color: 'var(--os1-text-faint, #6E6E6C)', marginTop: 4 }}>
                Goal: {s.goal}
              </div>
            )}
            <SayThis text={s.say_this} />
            {(s.talking_points || []).length > 0 && (
              <div style={{ marginTop: 8 }}>
                {s.talking_points.map((t, j) => (
                  <div key={j} className="os1-serif-micro" style={{ fontSize: 10.5, color: 'var(--os1-text-dim, #A8A8A6)', lineHeight: 1.55 }}>· {t}</div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    )

    if (section === 'script') return (
      <div>
        <SectionTitle sub="Opener → discovery → transition → close. Word-for-word.">Call Script</SectionTitle>
        {script.opener && (<div style={{ marginBottom: 14 }}>
          <div className="font-pixel" style={{ fontSize: 10.5, color: 'var(--os1-text, #F5F5F4)', marginBottom: 2 }}>Opener</div>
          <SayThis text={script.opener} />
        </div>)}
        {(script.discovery_questions || []).length > 0 && (<div style={{ marginBottom: 14 }}>
          <div className="font-pixel" style={{ fontSize: 10.5, color: 'var(--os1-text, #F5F5F4)', marginBottom: 6 }}>Discovery questions</div>
          {script.discovery_questions.map((q, i) => (
            <div key={i} className="os1-serif-micro" style={{ fontSize: 11, color: 'var(--os1-text-dim, #A8A8A6)', lineHeight: 1.6 }}>{i + 1}. {q}</div>
          ))}
        </div>)}
        {script.transition && (<div style={{ marginBottom: 14 }}>
          <div className="font-pixel" style={{ fontSize: 10.5, color: 'var(--os1-text, #F5F5F4)', marginBottom: 2 }}>Transition into the pitch</div>
          <SayThis text={script.transition} />
        </div>)}
        {script.close && (<div>
          <div className="font-pixel" style={{ fontSize: 10.5, color: 'var(--os1-text, #F5F5F4)', marginBottom: 2 }}>The close</div>
          <SayThis text={script.close} />
        </div>)}
      </div>
    )

    if (section === 'objections') return (
      <div>
        <SectionTitle sub="What they'll throw at you, why they're really saying it, and how you kill it.">Objections</SectionTitle>
        {(report?.objections || []).map((o, i) => (
          <div key={i} className="os1-card" style={{ padding: '14px 16px', marginBottom: 10 }}>
            <div className="font-pixel" style={{ fontSize: 12, color: '#FF9F0A', marginBottom: 5 }}>“{o.objection}”</div>
            <div className="os1-serif-micro" style={{ fontSize: 10, color: 'var(--os1-text-faint, #6E6E6C)', lineHeight: 1.5 }}>
              What they really mean: {o.why_they_say_it}
            </div>
            <SayThis text={o.response} />
            {o.proof_point && (
              <div className="os1-serif-micro" style={{ fontSize: 10.5, color: 'var(--os1-text-dim, #A8A8A6)', lineHeight: 1.5, marginTop: 6 }}>
                Proof: {o.proof_point}
              </div>
            )}
            {o.follow_up_question && (
              <div className="os1-serif-micro" style={{ fontSize: 10.5, color: 'var(--os1-accent, #2d7ff9)', lineHeight: 1.5, marginTop: 4 }}>
                Then ask: “{o.follow_up_question}”
              </div>
            )}
          </div>
        ))}
      </div>
    )

    // close
    return (
      <div>
        <SectionTitle sub="Assumptive closes — pick the one that fits the moment.">Closing Moves</SectionTitle>
        {(report?.closing_moves || []).map((c, i) => (
          <div key={i} style={{ marginBottom: 4 }}><SayThis text={c} /></div>
        ))}
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      {/* Section pills */}
      <div style={{
        display: 'flex', gap: 6, flexWrap: 'wrap', padding: '12px 20px',
        borderBottom: '1px solid var(--os1-border-soft, rgba(255,255,255,0.08))', flexShrink: 0,
      }}>
        {SECTIONS.map(s => (
          <button
            key={s.key}
            onClick={() => setSection(s.key)}
            className="font-pixel"
            style={{
              fontSize: 10.5, padding: '6px 12px', borderRadius: 999, cursor: 'pointer',
              border: `1px solid ${section === s.key ? 'var(--os1-accent, #2d7ff9)' : 'var(--os1-border-soft, rgba(255,255,255,0.08))'}`,
              background: section === s.key ? 'rgba(45,127,249,0.12)' : 'transparent',
              color: section === s.key ? 'var(--os1-accent, #2d7ff9)' : 'var(--os1-text-dim, #A8A8A6)',
            }}
          >{s.label}</button>
        ))}
      </div>
      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '18px 20px 30px' }}>
        {body()}
      </div>
    </div>
  )
}

export default function SalesAdvisorCockpit({ open, onClose, userId }) {
  const [chatOpen, setChatOpen] = useState(true)
  const [conversationId, setConversationId] = useState(null)
  const [reports, setReports] = useState([])
  const [activeId, setActiveId] = useState(null)
  const [active, setActive] = useState(null)      // full report row (polled while running)
  const [showForm, setShowForm] = useState(false)
  const [reloadTick, setReloadTick] = useState(0)

  // New-analysis form
  const [mapsUrl, setMapsUrl] = useState('')
  const [bizName, setBizName] = useState('')
  const [notes, setNotes] = useState('')
  const [starting, setStarting] = useState(false)
  const [formMsg, setFormMsg] = useState(null)

  const refresh = useCallback(() => setReloadTick(t => t + 1), [])

  // History list — reload on open and whenever a sales action fires (chat or panel).
  useEffect(() => {
    if (!open || !userId) return
    let cancelled = false
    fetch(`${BACKEND}/api/business/sales-advisor/list?user_id=${encodeURIComponent(userId)}&limit=50`)
      .then(r => r.json())
      .then(d => {
        if (cancelled) return
        const rows = d?.data?.reports || []
        setReports(rows)
        // Auto-focus: keep the current selection; otherwise take the newest row.
        setActiveId(prev => (prev && rows.some(r => r.id === prev)) ? prev : (rows[0]?.id || null))
      })
      .catch(() => { if (!cancelled) setReports([]) })
    return () => { cancelled = true }
  }, [open, userId, reloadTick])

  // Load + poll the active report while it's running.
  useEffect(() => {
    if (!open || !userId || !activeId) { setActive(null); return }
    let cancelled = false
    let timer = null
    const load = () => {
      fetch(`${BACKEND}/api/business/sales-advisor/report?user_id=${encodeURIComponent(userId)}&report_id=${encodeURIComponent(activeId)}`)
        .then(r => r.json())
        .then(d => {
          if (cancelled || !d?.ok) return
          setActive(d.data)
          if (d.data?.status === 'running') {
            timer = setTimeout(load, 2500)
          } else {
            // status flipped → refresh the rail so the dot goes green/red
            setReports(prev => prev.map(r => r.id === d.data.id
              ? { ...r, status: d.data.status, business_name: d.data.business_name, progress: d.data.progress } : r))
          }
        })
        .catch(() => { if (!cancelled) timer = setTimeout(load, 4000) })
    }
    load()
    return () => { cancelled = true; if (timer) clearTimeout(timer) }
  }, [open, userId, activeId])

  const startAnalysis = async () => {
    if (starting || (!mapsUrl.trim() && !bizName.trim())) return
    setStarting(true); setFormMsg(null)
    try {
      const res = await fetch(`${BACKEND}/api/business/sales-advisor/analyze`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: userId || '', maps_url: mapsUrl.trim() || null,
          business_name: bizName.trim() || null, notes: notes.trim() || null,
        }),
      })
      const d = await res.json().catch(() => ({}))
      if (d?.ok && d?.data?.report_id) {
        setMapsUrl(''); setBizName(''); setNotes(''); setShowForm(false)
        setActiveId(d.data.report_id)
        refresh()
      } else {
        setFormMsg(d?.error || 'Could not start the analysis.')
      }
    } catch {
      setFormMsg('Could not start the analysis — check your connection.')
    } finally {
      setStarting(false)
    }
  }

  const deleteReport = async (id) => {
    try {
      await fetch(`${BACKEND}/api/business/sales-advisor/delete`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId || '', report_id: id }),
      })
    } catch {}
    if (id === activeId) { setActiveId(null); setActive(null) }
    refresh()
  }

  const activeRow = useMemo(() => reports.find(r => r.id === activeId) || null, [reports, activeId])

  if (!open) return null

  const inputStyle = {
    width: '100%', background: '#1b1b1e', color: 'var(--os1-text, #F5F5F4)', fontSize: 12,
    border: '1px solid var(--os1-border-soft, rgba(255,255,255,0.08))',
    borderRadius: 8, padding: '10px 12px', outline: 'none',
  }

  const showFormView = showForm || (!activeId && reports.length === 0)

  return (
    <AnimatePresence>
      <motion.div
        key="sales-cockpit"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.2 }}
        style={{
          position: 'fixed', inset: 0, zIndex: 60,
          background: '#0B0B0C', display: 'flex', flexDirection: 'column',
        }}
      >
        {/* Cockpit top bar */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '10px 16px', borderBottom: '1px solid var(--os1-border-soft, rgba(255,255,255,0.08))',
          background: '#131316', flexShrink: 0,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Crosshair size={15} style={{ color: 'var(--os1-accent, #2d7ff9)' }} />
            <span className="font-pixel" style={{ fontSize: 14, color: 'var(--os1-text, #F5F5F4)' }}>Sales Advisor</span>
            <span className="os1-serif-micro" style={{ fontSize: 9, color: 'var(--os1-text-faint, #6E6E6C)' }}>
              deep research → a pitch built to close
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <button onClick={refresh} className="os1-iconbtn" title="Refresh"><RefreshCw size={16} /></button>
            <button onClick={() => setChatOpen(o => !o)} className="os1-iconbtn" title={chatOpen ? 'Hide chat' : 'Show chat'}>
              <MessageSquare size={16} />
            </button>
            <button onClick={onClose} className="os1-iconbtn" title="Close Sales Advisor"><X size={18} /></button>
          </div>
        </div>

        {/* Body: [history rail | main] + docked chat */}
        <div style={{ flex: 1, minHeight: 0, display: 'flex' }}>
          {/* Left rail: report history */}
          <div style={{
            width: 250, flexShrink: 0, display: 'flex', flexDirection: 'column',
            borderRight: '1px solid var(--os1-border-soft, rgba(255,255,255,0.08))', background: '#0e0e10',
          }}>
            <div style={{ padding: '12px 12px 8px' }}>
              <button
                onClick={() => { setShowForm(true); setFormMsg(null) }}
                className="font-pixel"
                style={{
                  width: '100%', fontSize: 11, padding: '9px 12px', borderRadius: 8,
                  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                  border: 'none', background: 'var(--os1-accent, #2d7ff9)', color: '#fff', cursor: 'pointer',
                }}
              >
                <Plus size={13} /> New Pitch
              </button>
            </div>
            <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '0 8px 12px' }}>
              {reports.length === 0 && (
                <div className="os1-serif-micro" style={{ fontSize: 10, color: 'var(--os1-text-faint, #6E6E6C)', padding: '10px 6px', lineHeight: 1.6 }}>
                  No pitches yet. Drop a Google Maps link of any business and I'll build you the pitch that closes them.
                </div>
              )}
              {reports.map(r => {
                const st = STATUS_STYLE[r.status] || STATUS_STYLE.running
                const isActive = r.id === activeId && !showFormView
                return (
                  <div
                    key={r.id}
                    onClick={() => { setActiveId(r.id); setShowForm(false) }}
                    style={{
                      padding: '9px 10px', marginBottom: 4, borderRadius: 8, cursor: 'pointer',
                      background: isActive ? 'rgba(45,127,249,0.08)' : 'transparent',
                      border: `1px solid ${isActive ? 'rgba(45,127,249,0.4)' : 'transparent'}`,
                      position: 'relative',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                      <span style={{
                        width: 7, height: 7, borderRadius: 99, flexShrink: 0, background: st.fg,
                        boxShadow: r.status === 'running' ? `0 0 6px ${st.fg}` : 'none',
                      }} />
                      <span className="font-pixel" style={{
                        fontSize: 11, color: 'var(--os1-text, #F5F5F4)', flex: 1, minWidth: 0,
                        whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                      }}>{r.business_name}</span>
                      <span className="os1-serif-micro" style={{ fontSize: 8.5, color: 'var(--os1-text-faint, #6E6E6C)', flexShrink: 0 }}>
                        {fmtDate(r.created_at)}
                      </span>
                      <span
                        onClick={(e) => { e.stopPropagation(); deleteReport(r.id) }}
                        title="Delete report" className="os1-iconbtn"
                        style={{ width: 20, height: 20, flexShrink: 0 }}
                      ><Trash2 size={11} /></span>
                    </div>
                    <div className="os1-serif-micro" style={{ fontSize: 9, color: st.fg, marginTop: 3, marginLeft: 14 }}>
                      {st.label}{r.status === 'running' && r.progress ? ` · ${r.progress}` : ''}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>

          {/* Main panel */}
          <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', position: 'relative' }}>
            {showFormView ? (
              /* ── New analysis form ── */
              <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 }}>
                <div style={{ width: 'min(560px, 92%)' }}>
                  <div className="font-pixel" style={{ fontSize: 16, color: 'var(--os1-text, #F5F5F4)', marginBottom: 6 }}>
                    Who are we closing?
                  </div>
                  <div className="os1-serif-micro" style={{ fontSize: 11, color: 'var(--os1-text-dim, #A8A8A6)', lineHeight: 1.6, marginBottom: 18 }}>
                    Drop the Google Maps link of the business. I'll pull their profile and reviews, scrape their
                    website, scan the web, find every gap — and hand you the offer, the deck, the script, and the
                    objection kills. Built on everything MG&CO sells.
                  </div>
                  <input
                    value={mapsUrl} onChange={e => setMapsUrl(e.target.value)}
                    placeholder="Google Maps link (maps.app.goo.gl/… or google.com/maps/place/…)"
                    style={{ ...inputStyle, marginBottom: 10 }}
                  />
                  <input
                    value={bizName} onChange={e => setBizName(e.target.value)}
                    placeholder="Business name + city (optional if you gave the link)"
                    style={{ ...inputStyle, marginBottom: 10 }}
                  />
                  <textarea
                    value={notes} onChange={e => setNotes(e.target.value)}
                    placeholder="Anything else you've got on them — who the owner is, past contact, what you noticed… (optional)"
                    rows={4}
                    style={{ ...inputStyle, resize: 'vertical', marginBottom: 14, fontFamily: 'inherit' }}
                  />
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <button
                      onClick={startAnalysis}
                      disabled={starting || (!mapsUrl.trim() && !bizName.trim())}
                      className="font-pixel"
                      style={{
                        fontSize: 12, padding: '11px 20px', borderRadius: 8, border: 'none',
                        display: 'flex', alignItems: 'center', gap: 8,
                        background: (!mapsUrl.trim() && !bizName.trim()) ? '#1b1b1e' : 'var(--os1-accent, #2d7ff9)',
                        color: (!mapsUrl.trim() && !bizName.trim()) ? 'var(--os1-text-faint, #6E6E6C)' : '#fff',
                        cursor: starting || (!mapsUrl.trim() && !bizName.trim()) ? 'default' : 'pointer',
                      }}
                    >
                      <Crosshair size={14} /> {starting ? 'Starting…' : 'Build My Pitch'}
                    </button>
                    {reports.length > 0 && (
                      <button
                        onClick={() => setShowForm(false)}
                        className="os1-serif-micro"
                        style={{ fontSize: 10.5, background: 'none', border: 'none', color: 'var(--os1-text-faint, #6E6E6C)', cursor: 'pointer' }}
                      >back to reports</button>
                    )}
                  </div>
                  {formMsg && (
                    <div className="os1-serif-micro" style={{ fontSize: 10.5, color: '#FF453A', marginTop: 10 }}>{formMsg}</div>
                  )}
                </div>
              </div>
            ) : !active ? (
              <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <span className="os1-serif-micro" style={{ fontSize: 11, color: 'var(--os1-text-faint, #6E6E6C)' }}>
                  {activeRow ? 'Loading report…' : 'Pick a report, or build a new pitch.'}
                </span>
              </div>
            ) : active.status === 'running' ? (
              /* ── Running: staged progress ── */
              <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 }}>
                <div style={{ textAlign: 'center', maxWidth: 380 }}>
                  <motion.div
                    animate={{ scale: [1, 1.15, 1], opacity: [0.7, 1, 0.7] }}
                    transition={{ duration: 1.8, repeat: Infinity, ease: 'easeInOut' }}
                    style={{ display: 'inline-flex', marginBottom: 18 }}
                  >
                    <Crosshair size={30} style={{ color: 'var(--os1-accent, #2d7ff9)' }} />
                  </motion.div>
                  <div className="font-pixel" style={{ fontSize: 13, color: 'var(--os1-text, #F5F5F4)', marginBottom: 8 }}>
                    Hunting: {active.business_name}
                  </div>
                  <div className="os1-serif-micro" style={{ fontSize: 11, color: 'var(--os1-text-dim, #A8A8A6)', lineHeight: 1.6 }}>
                    {active.progress || 'Working…'}
                  </div>
                  <div className="os1-serif-micro" style={{ fontSize: 9.5, color: 'var(--os1-text-faint, #6E6E6C)', marginTop: 14 }}>
                    Usually 1-3 minutes. You can keep chatting — I'll have it ready here.
                  </div>
                </div>
              </div>
            ) : active.status === 'failed' ? (
              <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 }}>
                <div style={{ textAlign: 'center', maxWidth: 420 }}>
                  <div className="font-pixel" style={{ fontSize: 13, color: '#FF453A', marginBottom: 8 }}>Analysis failed</div>
                  <div className="os1-serif-micro" style={{ fontSize: 10.5, color: 'var(--os1-text-dim, #A8A8A6)', lineHeight: 1.6, marginBottom: 16 }}>
                    {active.error || 'Something broke mid-research.'}
                  </div>
                  <button
                    onClick={() => { setShowForm(true); setBizName(active.business_name !== 'Resolving from Maps link…' ? active.business_name : ''); setMapsUrl(active.maps_url || '') }}
                    className="font-pixel"
                    style={{
                      fontSize: 11, padding: '9px 16px', borderRadius: 8, border: '1px solid var(--os1-border-soft, rgba(255,255,255,0.08))',
                      background: 'transparent', color: 'var(--os1-text, #F5F5F4)', cursor: 'pointer',
                      display: 'inline-flex', alignItems: 'center', gap: 6,
                    }}
                  >
                    Try again <ChevronRight size={12} />
                  </button>
                </div>
              </div>
            ) : (
              /* ── Complete: the report ── */
              <ReportView report={active.report || {}} />
            )}
          </div>

          {/* Docked chat — reuses ChatCanvas; collapsible (mirrors CrmCockpit/LeadsCockpit) */}
          <AnimatePresence>
            {chatOpen && (
              <motion.div
                key="sales-chat-dock"
                initial={{ width: 0, opacity: 0 }}
                animate={{ width: 'min(440px, 32vw)', opacity: 1 }}
                exit={{ width: 0, opacity: 0 }}
                transition={{ duration: 0.2, ease: 'easeOut' }}
                style={{
                  borderLeft: '1px solid var(--os1-border-soft, rgba(255,255,255,0.08))',
                  background: '#131313', display: 'flex', flexDirection: 'column',
                  minWidth: 300, flexShrink: 0, overflow: 'hidden',
                }}
              >
                <div style={{ flex: 1, minHeight: 0, minWidth: 0, position: 'relative' }}>
                  <ChatCanvas
                    userId={userId}
                    activeConversationId={conversationId}
                    onConversationCreated={setConversationId}
                    onConversationsUpdated={() => {}}
                    onMemoryCountUpdate={() => {}}
                    onLeadsChanged={() => {}}
                    onSalesChanged={refresh}
                    onCrmChanged={() => {}}
                    compact
                  />
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </motion.div>
    </AnimatePresence>
  )
}
