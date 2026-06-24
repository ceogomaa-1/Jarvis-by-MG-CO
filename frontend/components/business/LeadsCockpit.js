'use client'
import { useEffect, useRef, useState, useCallback, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { X, MessageSquare, RefreshCw, Phone, Globe, MapPin, Star, Check } from 'lucide-react'
import ChatCanvas from './ChatCanvas'

const BACKEND = 'https://jarvis-backend-4oz6.onrender.com'

// mgcoleads — the Leads cockpit. Mirrors CrmCockpit 1:1: a full-screen shell with a main
// panel (here: the scored A/B/C lead pipeline, native — not an iframe) and the SAME docked
// ChatCanvas on the right, scoped to run find_leads / list_leads / push_to_crm. After a
// leads action the chat fires onLeadsChanged and we reload the panel ("feels live").
// Additive — does NOT touch the CRM cockpit, Personal, onboarding, or provisioning.

const TIER_STYLE = {
  A: { bg: 'rgba(52,199,89,0.14)', fg: '#34C759', label: 'A' },
  B: { bg: 'rgba(255,179,64,0.14)', fg: '#FFB340', label: 'B' },
  C: { bg: 'rgba(168,168,166,0.12)', fg: '#A8A8A6', label: 'C' },
}

function cityFromAddress(address) {
  if (!address) return null
  const parts = address.split(',').map(p => p.trim()).filter(Boolean)
  return parts.length >= 2 ? parts[1] : null
}

function hostFromUrl(url) {
  if (!url) return null
  try {
    const h = new URL(url).hostname.toLowerCase()
    return h.startsWith('www.') ? h.slice(4) : h
  } catch { return url }
}

function TierBadge({ tier }) {
  const s = TIER_STYLE[(tier || 'C').toUpperCase()] || TIER_STYLE.C
  return (
    <span className="font-pixel" style={{
      fontSize: 11, fontWeight: 700, color: s.fg, background: s.bg,
      borderRadius: 6, padding: '2px 8px', lineHeight: 1.4, flexShrink: 0,
    }}>{s.label}</span>
  )
}

function LeadCard({ lead, selected, onToggle }) {
  const city = cityFromAddress(lead.address)
  const site = hostFromUrl(lead.website)
  return (
    <div
      onClick={() => !lead.pushed_to_crm && onToggle(lead.id)}
      className="os1-card"
      style={{
        padding: '14px 16px', marginBottom: 10, cursor: lead.pushed_to_crm ? 'default' : 'pointer',
        border: selected ? '1px solid var(--os1-accent, #2d7ff9)' : '1px solid var(--os1-border-soft, rgba(255,255,255,0.08))',
        opacity: lead.pushed_to_crm ? 0.7 : 1, position: 'relative',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
        {/* select box */}
        {!lead.pushed_to_crm && (
          <span style={{
            width: 16, height: 16, borderRadius: 4, flexShrink: 0, marginTop: 2,
            border: `1.5px solid ${selected ? 'var(--os1-accent, #2d7ff9)' : 'var(--os1-text-faint, #6E6E6C)'}`,
            background: selected ? 'var(--os1-accent, #2d7ff9)' : 'transparent',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            {selected && <Check size={11} color="#fff" />}
          </span>
        )}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <TierBadge tier={lead.tier} />
            <span className="font-pixel" style={{ fontSize: 13, color: 'var(--os1-text, #F5F5F4)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {lead.name}
            </span>
            <span className="os1-serif-micro" style={{ fontSize: 10, color: 'var(--os1-text-faint, #6E6E6C)', flexShrink: 0 }}>
              score {lead.score}
            </span>
            {lead.pushed_to_crm && (
              <span className="os1-serif-micro" style={{ fontSize: 9, color: '#34C759', flexShrink: 0 }}>✓ in CRM</span>
            )}
          </div>

          {/* meta row */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, marginBottom: 7 }}>
            {lead.category && (
              <span className="os1-serif-micro" style={{ fontSize: 10, color: 'var(--os1-text-dim, #A8A8A6)' }}>{lead.category}</span>
            )}
            {(lead.rating != null) && (
              <span className="os1-serif-micro" style={{ fontSize: 10, color: 'var(--os1-text-dim, #A8A8A6)', display: 'flex', alignItems: 'center', gap: 3 }}>
                <Star size={10} /> {lead.rating} · {lead.review_count || 0} reviews
              </span>
            )}
            {lead.phone && (
              <span className="os1-serif-micro" style={{ fontSize: 10, color: 'var(--os1-text-dim, #A8A8A6)', display: 'flex', alignItems: 'center', gap: 3 }}>
                <Phone size={10} /> {lead.phone}
              </span>
            )}
            <span className="os1-serif-micro" style={{ fontSize: 10, color: site ? 'var(--os1-text-dim, #A8A8A6)' : '#FFB340', display: 'flex', alignItems: 'center', gap: 3 }}>
              <Globe size={10} /> {site || 'no website'}
            </span>
            {city && (
              <span className="os1-serif-micro" style={{ fontSize: 10, color: 'var(--os1-text-dim, #A8A8A6)', display: 'flex', alignItems: 'center', gap: 3 }}>
                <MapPin size={10} /> {city}
              </span>
            )}
          </div>

          {/* gap + pitch */}
          {lead.why && (
            <div className="os1-serif-micro" style={{ fontSize: 11, color: 'var(--os1-text-dim, #A8A8A6)', lineHeight: 1.45 }}>
              {lead.why}
            </div>
          )}
          {lead.pitch && (
            <div className="os1-serif-micro" style={{ fontSize: 10.5, color: 'var(--os1-text-faint, #6E6E6C)', lineHeight: 1.4, marginTop: 3 }}>
              Pitch: {lead.pitch}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default function LeadsCockpit({ open, onClose, userId }) {
  const [chatOpen, setChatOpen] = useState(true)
  const [conversationId, setConversationId] = useState(null)
  const [leads, setLeads] = useState([])
  const [tierCounts, setTierCounts] = useState({ A: 0, B: 0, C: 0 })
  const [loading, setLoading] = useState(false)
  const [tierFilter, setTierFilter] = useState('ALL')
  const [industryFilter, setIndustryFilter] = useState('ALL')
  const [cityFilter, setCityFilter] = useState('ALL')
  const [sortBy, setSortBy] = useState('score')
  const [selected, setSelected] = useState(() => new Set())
  const [pushing, setPushing] = useState(false)
  const [reloadTick, setReloadTick] = useState(0)

  const refreshLeads = useCallback(() => setReloadTick(t => t + 1), [])

  // Load the pipeline whenever the cockpit opens or a leads action fires.
  useEffect(() => {
    if (!open || !userId) return
    let cancelled = false
    setLoading(true)
    fetch(`${BACKEND}/api/business/leads/list?user_id=${encodeURIComponent(userId)}&limit=200`)
      .then(r => r.json())
      .then(d => {
        if (cancelled) return
        setLeads(Array.isArray(d.leads) ? d.leads : [])
        setTierCounts(d.tier_counts || { A: 0, B: 0, C: 0 })
      })
      .catch(() => { if (!cancelled) setLeads([]) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [open, userId, reloadTick])

  // Distinct industries/cities for the filter dropdowns (derived from the loaded rows).
  const industries = useMemo(
    () => Array.from(new Set(leads.map(l => l.category).filter(Boolean))).sort(),
    [leads])
  const cities = useMemo(
    () => Array.from(new Set(leads.map(l => cityFromAddress(l.address)).filter(Boolean))).sort(),
    [leads])

  const visible = useMemo(() => {
    let rows = leads
    if (tierFilter !== 'ALL') rows = rows.filter(l => (l.tier || 'C').toUpperCase() === tierFilter)
    if (industryFilter !== 'ALL') rows = rows.filter(l => l.category === industryFilter)
    if (cityFilter !== 'ALL') rows = rows.filter(l => cityFromAddress(l.address) === cityFilter)
    const key = sortBy === 'rating' ? 'rating' : sortBy === 'reviews' ? 'review_count' : 'score'
    return [...rows].sort((a, b) => (b[key] || 0) - (a[key] || 0))
  }, [leads, tierFilter, industryFilter, cityFilter, sortBy])

  const selectableVisible = useMemo(() => visible.filter(l => !l.pushed_to_crm), [visible])

  const toggle = useCallback((id) => {
    setSelected(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }, [])

  const allSelected = selectableVisible.length > 0 && selectableVisible.every(l => selected.has(l.id))
  const toggleAll = () => {
    setSelected(allSelected ? new Set() : new Set(selectableVisible.map(l => l.id)))
  }

  const pushSelected = async () => {
    const names = leads.filter(l => selected.has(l.id)).map(l => l.name).filter(Boolean)
    if (!names.length) return
    setPushing(true)
    try {
      const res = await fetch(`${BACKEND}/api/business/leads/push`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId || '', names, limit: names.length }),
      })
      await res.json().catch(() => ({}))
      setSelected(new Set())
      refreshLeads()
    } catch {
      // best-effort; the panel reload below surfaces the true state
      refreshLeads()
    } finally {
      setPushing(false)
    }
  }

  if (!open) return null

  const selectStyle = {
    background: '#1b1b1e', color: 'var(--os1-text, #F5F5F4)', fontSize: 11,
    border: '1px solid var(--os1-border-soft, rgba(255,255,255,0.08))',
    borderRadius: 6, padding: '4px 8px', cursor: 'pointer',
  }

  return (
    <AnimatePresence>
      <motion.div
        key="leads-cockpit"
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
            <span className="font-pixel" style={{ fontSize: 14, color: 'var(--os1-text, #F5F5F4)' }}>Leads</span>
            <span className="os1-serif-micro" style={{ fontSize: 9, color: 'var(--os1-text-faint, #6E6E6C)' }}>
              {leads.length} scored · {tierCounts.A || 0} A · {tierCounts.B || 0} B · {tierCounts.C || 0} C
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <button onClick={refreshLeads} className="os1-iconbtn" title="Refresh leads"><RefreshCw size={16} /></button>
            <button onClick={() => setChatOpen(o => !o)} className="os1-iconbtn" title={chatOpen ? 'Hide chat' : 'Show chat'}>
              <MessageSquare size={16} />
            </button>
            <button onClick={onClose} className="os1-iconbtn" title="Close Leads"><X size={18} /></button>
          </div>
        </div>

        {/* Body: leads panel + docked chat */}
        <div style={{ flex: 1, minHeight: 0, display: 'flex' }}>
          <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', background: '#0B0B0C' }}>
            {/* Filter / sort / bulk bar */}
            <div style={{
              display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap',
              padding: '10px 16px', borderBottom: '1px solid var(--os1-border-soft, rgba(255,255,255,0.08))',
              flexShrink: 0,
            }}>
              {/* tier chips */}
              <div style={{ display: 'flex', gap: 4 }}>
                {['ALL', 'A', 'B', 'C'].map(t => (
                  <button
                    key={t}
                    onClick={() => setTierFilter(t)}
                    className="font-pixel"
                    style={{
                      fontSize: 11, padding: '4px 10px', borderRadius: 6, cursor: 'pointer',
                      border: '1px solid var(--os1-border-soft, rgba(255,255,255,0.08))',
                      background: tierFilter === t ? 'var(--os1-accent, #2d7ff9)' : 'transparent',
                      color: tierFilter === t ? '#fff' : 'var(--os1-text-dim, #A8A8A6)',
                    }}
                  >
                    {t === 'ALL' ? 'All' : t}{t !== 'ALL' ? ` ${tierCounts[t] || 0}` : ''}
                  </button>
                ))}
              </div>

              <select value={industryFilter} onChange={e => setIndustryFilter(e.target.value)} style={selectStyle}>
                <option value="ALL">All industries</option>
                {industries.map(i => <option key={i} value={i}>{i}</option>)}
              </select>
              <select value={cityFilter} onChange={e => setCityFilter(e.target.value)} style={selectStyle}>
                <option value="ALL">All cities</option>
                {cities.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
              <select value={sortBy} onChange={e => setSortBy(e.target.value)} style={selectStyle}>
                <option value="score">Sort: score</option>
                <option value="rating">Sort: rating</option>
                <option value="reviews">Sort: reviews</option>
              </select>

              <div style={{ flex: 1 }} />

              {selectableVisible.length > 0 && (
                <button onClick={toggleAll} className="os1-serif-micro"
                  style={{ fontSize: 10, background: 'transparent', border: 'none', color: 'var(--os1-text-dim, #A8A8A6)', cursor: 'pointer' }}>
                  {allSelected ? 'Clear' : 'Select all'}
                </button>
              )}
              <button
                onClick={pushSelected}
                disabled={selected.size === 0 || pushing}
                className="font-pixel"
                style={{
                  fontSize: 11, padding: '5px 12px', borderRadius: 6,
                  border: '1px solid var(--os1-border-soft, rgba(255,255,255,0.08))',
                  background: selected.size === 0 ? 'transparent' : 'var(--os1-accent, #2d7ff9)',
                  color: selected.size === 0 ? 'var(--os1-text-faint, #6E6E6C)' : '#fff',
                  cursor: selected.size === 0 || pushing ? 'default' : 'pointer',
                }}
              >
                {pushing ? 'Pushing…' : `Push ${selected.size || ''} to CRM`}
              </button>
            </div>

            {/* Leads list */}
            <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '14px 16px' }} className="os1-scroll">
              {loading && leads.length === 0 ? (
                <div className="os1-serif-micro" style={{ fontSize: 11, color: 'var(--os1-text-faint, #6E6E6C)', textAlign: 'center', marginTop: 40 }}>
                  Loading your pipeline…
                </div>
              ) : visible.length === 0 ? (
                <div style={{ textAlign: 'center', marginTop: 60, color: 'var(--os1-text-dim, #A8A8A6)' }}>
                  <div className="font-pixel" style={{ fontSize: 13, marginBottom: 8 }}>No leads yet</div>
                  <div className="os1-serif-micro" style={{ fontSize: 11, lineHeight: 1.5 }}>
                    Ask Jarvis in the chat → e.g. <span style={{ color: 'var(--os1-text, #F5F5F4)' }}>“find leads: salons in Toronto”</span>
                  </div>
                </div>
              ) : (
                visible.map(l => (
                  <LeadCard key={l.id} lead={l} selected={selected.has(l.id)} onToggle={toggle} />
                ))
              )}
            </div>
          </div>

          {/* Docked chat — reuses ChatCanvas; collapsible (mirrors CrmCockpit) */}
          <AnimatePresence>
            {chatOpen && (
              <motion.div
                key="leads-chat-dock"
                initial={{ width: 0, opacity: 0 }}
                animate={{ width: 'min(440px, 38vw)', opacity: 1 }}
                exit={{ width: 0, opacity: 0 }}
                transition={{ duration: 0.2, ease: 'easeOut' }}
                style={{
                  borderLeft: '1px solid var(--os1-border-soft, rgba(255,255,255,0.08))',
                  background: '#131313', display: 'flex', flexDirection: 'column',
                  minWidth: 320, flexShrink: 0, overflow: 'hidden',
                }}
              >
                <div style={{ flex: 1, minHeight: 0, minWidth: 0, position: 'relative' }}>
                  <ChatCanvas
                    userId={userId}
                    activeConversationId={conversationId}
                    onConversationCreated={setConversationId}
                    onConversationsUpdated={() => {}}
                    onMemoryCountUpdate={() => {}}
                    onLeadsChanged={refreshLeads}
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
