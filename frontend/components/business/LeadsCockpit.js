'use client'
import { useEffect, useRef, useState, useCallback, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { X, MessageSquare, RefreshCw, Phone, Globe, MapPin, Star, Check, Search } from 'lucide-react'
import ChatCanvas from './ChatCanvas'
import { loadGoogleMaps, mapsBrowserKey } from '../../lib/googleMaps'

const BACKEND = 'https://jarvis-backend-4oz6.onrender.com'

// mgcoleads — the Leads cockpit. Mirrors CrmCockpit 1:1: a full-screen shell with the SAME
// docked ChatCanvas on the right. Main panel = the old mgcoleads layout: a "Client Discovery"
// control panel (niche + city + Discover) over a scored A/B/C list AND a live Google Map that
// plots every scored lead as a tier-colored pin. List and map stay in sync (focus in one →
// highlight in the other). After a leads action the chat fires onLeadsChanged and we reload.
// Additive — does NOT touch the CRM cockpit, Personal, onboarding, or provisioning.

const TIER_STYLE = {
  A: { bg: 'rgba(52,199,89,0.14)', fg: '#34C759', pin: '#34C759', label: 'A' },
  B: { bg: 'rgba(255,179,64,0.14)', fg: '#FFB340', pin: '#FFB340', label: 'B' },
  C: { bg: 'rgba(168,168,166,0.12)', fg: '#A8A8A6', pin: '#A8A8A6', label: 'C' },
}

// Target-niche options for the Client Discovery dropdown (B2B categories MG&CO sells to).
const NICHES = [
  'Dental clinics', 'Salons & spas', 'Hair & barber shops', 'Law firms',
  'Real estate agents', 'Restaurants & cafes', 'Auto repair shops',
  'HVAC & plumbing', 'Medical clinics', 'Chiropractors & physio',
  'Accounting & bookkeeping', 'Cleaning services', 'Landscaping',
  'Roofing & contractors', 'Veterinary clinics', 'Insurance brokers',
]

const tierOf = (l) => (l.tier || 'C').toUpperCase()

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

function LeadCard({ lead, selected, focused, onToggle, onFocus }) {
  const city = cityFromAddress(lead.address)
  const site = hostFromUrl(lead.website)
  return (
    <div
      onClick={() => onFocus(lead.id)}
      className="os1-card"
      style={{
        padding: '14px 16px', marginBottom: 10, cursor: 'pointer',
        border: focused ? '1px solid var(--os1-accent, #2d7ff9)'
          : selected ? '1px solid rgba(45,127,249,0.5)'
          : '1px solid var(--os1-border-soft, rgba(255,255,255,0.08))',
        background: focused ? 'rgba(45,127,249,0.06)' : undefined,
        opacity: lead.pushed_to_crm ? 0.75 : 1, position: 'relative',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
        {/* select box — its own click target (stops focus) */}
        {!lead.pushed_to_crm && (
          <span
            onClick={(e) => { e.stopPropagation(); onToggle(lead.id) }}
            title="Select for bulk push"
            style={{
              width: 16, height: 16, borderRadius: 4, flexShrink: 0, marginTop: 2, cursor: 'pointer',
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

// Live Google Map — plots each lead with lat/lng as a tier-colored pin. Self-contained:
// loads the Maps JS API (browser key), rebuilds markers when the lead set changes, and bumps
// the focused marker. Calls onMarkerClick(id) so the parent can show the lead card in sync.
function LeadsMap({ leads, focusedId, onMarkerClick }) {
  const containerRef = useRef(null)
  const mapRef = useRef(null)
  const markersRef = useRef(new Map())   // lead.id -> google.maps.Marker
  const [status, setStatus] = useState('loading') // loading | ready | error | nokey
  const [errMsg, setErrMsg] = useState('')

  const pinned = useMemo(
    () => leads.filter(l => l.lat != null && l.lng != null),
    [leads])
  // Signature of the plotted set → only refit bounds when it actually changes.
  const setSig = pinned.map(l => l.id).join(',')

  useEffect(() => {
    if (!mapsBrowserKey()) { setStatus('nokey'); return }
    let cancelled = false
    // Surface Google's own auth errors (RefererNotAllowedMapError, etc.) into the overlay.
    if (typeof window !== 'undefined') {
      window.gm_authFailure = () => {
        if (!cancelled) { setErrMsg('Google rejected the key (gm_authFailure) — check API key referrer / API restrictions'); setStatus('error') }
      }
    }
    loadGoogleMaps()
      .then((maps) => {
        if (cancelled || !containerRef.current) return
        if (!mapRef.current) {
          mapRef.current = new maps.Map(containerRef.current, {
            center: { lat: 43.7, lng: -79.42 }, zoom: 10,
            disableDefaultUI: true, zoomControl: true,
            backgroundColor: '#0B0B0C',
            styles: DARK_MAP_STYLE,
          })
        }
        setStatus('ready')
      })
      .catch((e) => { if (!cancelled) { setErrMsg(e?.message || String(e)); setStatus('error') } })
    return () => { cancelled = true }
  }, [])

  // Rebuild markers whenever the plotted set changes.
  useEffect(() => {
    const maps = typeof window !== 'undefined' ? window.google?.maps : null
    if (status !== 'ready' || !maps || !mapRef.current) return

    // clear old
    markersRef.current.forEach(m => m.setMap(null))
    markersRef.current.clear()

    const bounds = new maps.LatLngBounds()
    pinned.forEach(l => {
      const pos = { lat: Number(l.lat), lng: Number(l.lng) }
      const color = (TIER_STYLE[tierOf(l)] || TIER_STYLE.C).pin
      const marker = new maps.Marker({
        position: pos, map: mapRef.current, title: l.name,
        icon: {
          path: maps.SymbolPath.CIRCLE, scale: 7,
          fillColor: color, fillOpacity: 0.95,
          strokeColor: '#0B0B0C', strokeWeight: 2,
        },
      })
      marker.addListener('click', () => onMarkerClick(l.id))
      markersRef.current.set(l.id, marker)
      bounds.extend(pos)
    })
    if (pinned.length === 1) {
      mapRef.current.setCenter(bounds.getCenter()); mapRef.current.setZoom(14)
    } else if (pinned.length > 1) {
      mapRef.current.fitBounds(bounds, 60)
    }
  }, [status, setSig]) // eslint-disable-line react-hooks/exhaustive-deps

  // Highlight the focused marker (bigger, white stroke) + pan to it.
  useEffect(() => {
    const maps = typeof window !== 'undefined' ? window.google?.maps : null
    if (status !== 'ready' || !maps) return
    markersRef.current.forEach((m, id) => {
      const lead = pinned.find(l => l.id === id)
      const color = (TIER_STYLE[tierOf(lead || {})] || TIER_STYLE.C).pin
      const isF = id === focusedId
      m.setIcon({
        path: maps.SymbolPath.CIRCLE, scale: isF ? 11 : 7,
        fillColor: color, fillOpacity: isF ? 1 : 0.95,
        strokeColor: isF ? '#FFFFFF' : '#0B0B0C', strokeWeight: isF ? 3 : 2,
      })
      m.setZIndex(isF ? 999 : 1)
    })
    if (focusedId && markersRef.current.has(focusedId)) {
      mapRef.current.panTo(markersRef.current.get(focusedId).getPosition())
    }
  }, [focusedId, status, setSig]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div style={{ position: 'absolute', inset: 0 }}>
      <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
      {status !== 'ready' && (
        <div style={{
          position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center',
          textAlign: 'center', padding: 24, color: 'var(--os1-text-dim, #A8A8A6)', pointerEvents: 'none',
        }}>
          <div>
            <div className="font-pixel" style={{ fontSize: 13, marginBottom: 8 }}>
              {status === 'nokey' ? 'Map key not configured'
                : status === 'error' ? 'Map failed to load'
                : 'Loading map…'}
            </div>
            {status === 'nokey' && (
              <div className="os1-serif-micro" style={{ fontSize: 10.5, lineHeight: 1.5, maxWidth: 280 }}>
                Set NEXT_PUBLIC_MAPS_BROWSER_KEY (Maps JavaScript API, restricted to the
                jarvismgco.com referrer). The list still works without it.
              </div>
            )}
            {status === 'error' && errMsg && (
              <div className="os1-serif-micro" style={{ fontSize: 10, lineHeight: 1.5, maxWidth: 320, color: 'var(--os1-text-faint, #6E6E6C)', marginTop: 6 }}>
                {errMsg}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// Minimal dark map style so the map sits in the OS1 palette instead of bright white.
const DARK_MAP_STYLE = [
  { elementType: 'geometry', stylers: [{ color: '#1b1b1e' }] },
  { elementType: 'labels.text.stroke', stylers: [{ color: '#0B0B0C' }] },
  { elementType: 'labels.text.fill', stylers: [{ color: '#8a8a88' }] },
  { featureType: 'poi', stylers: [{ visibility: 'off' }] },
  { featureType: 'transit', stylers: [{ visibility: 'off' }] },
  { featureType: 'road', elementType: 'geometry', stylers: [{ color: '#2a2a2e' }] },
  { featureType: 'road', elementType: 'labels.text.fill', stylers: [{ color: '#6E6E6C' }] },
  { featureType: 'water', elementType: 'geometry', stylers: [{ color: '#0e0e10' }] },
]

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
  const [focusedId, setFocusedId] = useState(null)

  // Client Discovery controls
  const [niche, setNiche] = useState('')
  const [city, setCity] = useState('')
  const [discovering, setDiscovering] = useState(false)
  const [discoverMsg, setDiscoverMsg] = useState(null)

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
    if (tierFilter !== 'ALL') rows = rows.filter(l => tierOf(l) === tierFilter)
    if (industryFilter !== 'ALL') rows = rows.filter(l => l.category === industryFilter)
    if (cityFilter !== 'ALL') rows = rows.filter(l => cityFromAddress(l.address) === cityFilter)
    const key = sortBy === 'rating' ? 'rating' : sortBy === 'reviews' ? 'review_count' : 'score'
    return [...rows].sort((a, b) => (b[key] || 0) - (a[key] || 0))
  }, [leads, tierFilter, industryFilter, cityFilter, sortBy])

  const selectableVisible = useMemo(() => visible.filter(l => !l.pushed_to_crm), [visible])
  const focusedLead = useMemo(() => leads.find(l => l.id === focusedId) || null, [leads, focusedId])

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

  const pushNames = async (names) => {
    if (!names.length) return
    setPushing(true)
    try {
      await fetch(`${BACKEND}/api/business/leads/push`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId || '', names, limit: names.length }),
      }).then(r => r.json()).catch(() => ({}))
    } finally {
      setPushing(false)
      refreshLeads()
    }
  }

  const pushSelected = async () => {
    const names = leads.filter(l => selected.has(l.id)).map(l => l.name).filter(Boolean)
    if (!names.length) return
    await pushNames(names)
    setSelected(new Set())
  }

  const discover = async () => {
    if (!niche.trim() || discovering) return
    setDiscovering(true)
    setDiscoverMsg(null)
    try {
      const res = await fetch(`${BACKEND}/api/business/leads/discover`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId || '', niche: niche.trim(), city: city.trim() }),
      })
      const d = await res.json().catch(() => ({}))
      if (d.ok) {
        const n = d.data?.count ?? 0
        setDiscoverMsg(`Found ${n} business${n === 1 ? '' : 'es'}.`)
      } else {
        setDiscoverMsg(d.error || 'Discovery failed.')
      }
    } catch {
      setDiscoverMsg('Discovery failed — check your connection.')
    } finally {
      setDiscovering(false)
      refreshLeads()
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

        {/* Client Discovery control panel — niche + city + Discover (old mgcoleads layout) */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap',
          padding: '12px 16px', borderBottom: '1px solid var(--os1-border-soft, rgba(255,255,255,0.08))',
          background: '#101012', flexShrink: 0,
        }}>
          <span className="font-pixel" style={{ fontSize: 12, color: 'var(--os1-text, #F5F5F4)', marginRight: 4 }}>
            Client Discovery
          </span>
          <select value={niche} onChange={e => setNiche(e.target.value)} style={{ ...selectStyle, padding: '7px 10px', minWidth: 170 }}>
            <option value="">Target niche…</option>
            {NICHES.map(n => <option key={n} value={n}>{n}</option>)}
          </select>
          <input
            value={city}
            onChange={e => setCity(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') discover() }}
            placeholder="City (e.g. Toronto)"
            style={{
              ...selectStyle, padding: '7px 10px', minWidth: 160, cursor: 'text',
            }}
          />
          <button
            onClick={discover}
            disabled={!niche.trim() || discovering}
            className="font-pixel"
            style={{
              fontSize: 11, padding: '8px 14px', borderRadius: 6, display: 'flex', alignItems: 'center', gap: 6,
              border: '1px solid var(--os1-border-soft, rgba(255,255,255,0.08))',
              background: !niche.trim() ? 'transparent' : 'var(--os1-accent, #2d7ff9)',
              color: !niche.trim() ? 'var(--os1-text-faint, #6E6E6C)' : '#fff',
              cursor: !niche.trim() || discovering ? 'default' : 'pointer',
            }}
          >
            <Search size={13} /> {discovering ? 'Discovering…' : 'Discover Businesses'}
          </button>
          {discoverMsg && (
            <span className="os1-serif-micro" style={{ fontSize: 10, color: 'var(--os1-text-dim, #A8A8A6)' }}>{discoverMsg}</span>
          )}
        </div>

        {/* Body: [list | map] + docked chat */}
        <div style={{ flex: 1, minHeight: 0, display: 'flex' }}>
          {/* Left: filters + scored list */}
          <div style={{
            width: 'min(420px, 38%)', minWidth: 320, flexShrink: 0,
            display: 'flex', flexDirection: 'column', background: '#0B0B0C',
            borderRight: '1px solid var(--os1-border-soft, rgba(255,255,255,0.08))',
          }}>
            {/* Filter / sort / bulk bar */}
            <div style={{
              display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap',
              padding: '10px 16px', borderBottom: '1px solid var(--os1-border-soft, rgba(255,255,255,0.08))',
              flexShrink: 0,
            }}>
              <div style={{ display: 'flex', gap: 4 }}>
                {['ALL', 'A', 'B', 'C'].map(t => (
                  <button
                    key={t}
                    onClick={() => setTierFilter(t)}
                    className="font-pixel"
                    style={{
                      fontSize: 11, padding: '4px 9px', borderRadius: 6, cursor: 'pointer',
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
            </div>

            {/* Bulk push row */}
            <div style={{
              display: 'flex', alignItems: 'center', gap: 10,
              padding: '8px 16px', borderBottom: '1px solid var(--os1-border-soft, rgba(255,255,255,0.08))',
              flexShrink: 0,
            }}>
              {selectableVisible.length > 0 && (
                <button onClick={toggleAll} className="os1-serif-micro"
                  style={{ fontSize: 10, background: 'transparent', border: 'none', color: 'var(--os1-text-dim, #A8A8A6)', cursor: 'pointer' }}>
                  {allSelected ? 'Clear' : 'Select all'}
                </button>
              )}
              <div style={{ flex: 1 }} />
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
                    Use Client Discovery above, or ask Jarvis →<br />
                    <span style={{ color: 'var(--os1-text, #F5F5F4)' }}>“find leads: salons in Toronto”</span>
                  </div>
                </div>
              ) : (
                visible.map(l => (
                  <LeadCard
                    key={l.id} lead={l}
                    selected={selected.has(l.id)}
                    focused={l.id === focusedId}
                    onToggle={toggle}
                    onFocus={setFocusedId}
                  />
                ))
              )}
            </div>
          </div>

          {/* Middle: live map */}
          <div style={{ flex: 1, minWidth: 0, position: 'relative', background: '#0B0B0C' }}>
            <LeadsMap leads={visible} focusedId={focusedId} onMarkerClick={setFocusedId} />

            {/* Focused-lead card overlay (from a marker or list click) */}
            <AnimatePresence>
              {focusedLead && (
                <motion.div
                  key="focused-card"
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: 12 }}
                  transition={{ duration: 0.16 }}
                  className="os1-panel"
                  style={{
                    position: 'absolute', left: 16, bottom: 16, width: 'min(340px, calc(100% - 32px))',
                    padding: '14px 16px', background: '#16161a',
                    border: '1px solid var(--os1-border-soft, rgba(255,255,255,0.1))',
                    boxShadow: '0 12px 40px rgba(0,0,0,0.5)', zIndex: 5,
                  }}
                >
                  <button onClick={() => setFocusedId(null)} className="os1-iconbtn"
                    title="Close" style={{ position: 'absolute', top: 8, right: 8 }}>
                    <X size={14} />
                  </button>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6, paddingRight: 22 }}>
                    <TierBadge tier={focusedLead.tier} />
                    <span className="font-pixel" style={{ fontSize: 13, color: 'var(--os1-text, #F5F5F4)' }}>{focusedLead.name}</span>
                    <span className="os1-serif-micro" style={{ fontSize: 10, color: 'var(--os1-text-faint, #6E6E6C)' }}>score {focusedLead.score}</span>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginBottom: 8 }}>
                    {focusedLead.category && (
                      <span className="os1-serif-micro" style={{ fontSize: 10.5, color: 'var(--os1-text-dim, #A8A8A6)' }}>{focusedLead.category}</span>
                    )}
                    {focusedLead.phone && (
                      <span className="os1-serif-micro" style={{ fontSize: 10.5, color: 'var(--os1-text-dim, #A8A8A6)', display: 'flex', alignItems: 'center', gap: 4 }}>
                        <Phone size={11} /> {focusedLead.phone}
                      </span>
                    )}
                    <span className="os1-serif-micro" style={{ fontSize: 10.5, color: hostFromUrl(focusedLead.website) ? 'var(--os1-text-dim, #A8A8A6)' : '#FFB340', display: 'flex', alignItems: 'center', gap: 4 }}>
                      <Globe size={11} /> {hostFromUrl(focusedLead.website) || 'no website'}
                    </span>
                    {focusedLead.address && (
                      <span className="os1-serif-micro" style={{ fontSize: 10.5, color: 'var(--os1-text-dim, #A8A8A6)', display: 'flex', alignItems: 'flex-start', gap: 4 }}>
                        <MapPin size={11} style={{ marginTop: 1, flexShrink: 0 }} /> {focusedLead.address}
                      </span>
                    )}
                  </div>
                  {focusedLead.why && (
                    <div className="os1-serif-micro" style={{ fontSize: 10.5, color: 'var(--os1-text-dim, #A8A8A6)', lineHeight: 1.45, marginBottom: 4 }}>
                      {focusedLead.why}
                    </div>
                  )}
                  {focusedLead.pitch && (
                    <div className="os1-serif-micro" style={{ fontSize: 10, color: 'var(--os1-text-faint, #6E6E6C)', lineHeight: 1.4, marginBottom: 10 }}>
                      Pitch: {focusedLead.pitch}
                    </div>
                  )}
                  {focusedLead.pushed_to_crm ? (
                    <div className="os1-serif-micro" style={{ fontSize: 10.5, color: '#34C759' }}>✓ Already in CRM</div>
                  ) : (
                    <button
                      onClick={() => pushNames([focusedLead.name])}
                      disabled={pushing}
                      className="font-pixel"
                      style={{
                        width: '100%', fontSize: 11, padding: '7px 12px', borderRadius: 6,
                        border: 'none', background: 'var(--os1-accent, #2d7ff9)', color: '#fff',
                        cursor: pushing ? 'default' : 'pointer',
                      }}
                    >
                      {pushing ? 'Pushing…' : 'Push to CRM'}
                    </button>
                  )}
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {/* Docked chat — reuses ChatCanvas; collapsible (mirrors CrmCockpit) */}
          <AnimatePresence>
            {chatOpen && (
              <motion.div
                key="leads-chat-dock"
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
