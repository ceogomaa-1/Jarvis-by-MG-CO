'use client'
import { useState, useEffect, useRef } from 'react'
import { motion } from 'framer-motion'

// Minimum gap between readiness fetches. Readiness barely changes minute-to-minute,
// so polling it every second (the old behavior) just floods the backend and
// compounds latency. Fetch on mount + after an action change, but never more than
// once per this window.
const MIN_FETCH_INTERVAL_MS = 60000

export default function ReadinessBar({ userId, apiUrl, onReadinessUpdate, refreshSignal }) {
  const [readiness, setReadiness] = useState(null)
  const [isExpanded, setIsExpanded] = useState(false)
  const lastFetchRef = useRef(0)

  useEffect(() => {
    if (!userId) return
    fetchReadiness(true)
    const interval = setInterval(() => fetchReadiness(true), MIN_FETCH_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [userId])

  // Refresh after a connection/action change — but throttled to once per window.
  useEffect(() => {
    if (!userId || !refreshSignal) return
    fetchReadiness(false)
  }, [refreshSignal])

  async function fetchReadiness(force = false) {
    const now = Date.now()
    if (!force && now - lastFetchRef.current < MIN_FETCH_INTERVAL_MS) return
    lastFetchRef.current = now
    try {
      const res = await fetch(`${apiUrl}/api/business/readiness?user_id=${encodeURIComponent(userId)}`)
      const data = await res.json()
      setReadiness(data)
      onReadinessUpdate?.(data)
    } catch (e) {
      console.error('Readiness fetch failed:', e)
    }
  }

  if (!readiness) return null

  const { score, is_ready, next_milestone, checkpoints } = readiness

  const CHECKPOINTS = [
    { key: 'name_known',          label: 'Name' },
    { key: 'business_known',      label: 'Industry' },
    { key: 'business_name',       label: 'Business' },
    { key: 'revenue_context',     label: 'Revenue Goals' },
    { key: 'first_connector',     label: '1st Tool' },
    { key: 'power_connected',     label: '2 Tools' },
    { key: 'north_star_set',      label: 'North Star' },
    { key: 'five_memories',       label: '5+ Memories' },
    { key: 'deep_knowledge',      label: 'Deep Context' },
    { key: 'conversation_depth',  label: 'Chat Depth' },
  ]

  return (
    <div style={{ width: '100%', padding: '18px 70px 0', position: 'relative', zIndex: 20 }}>
      <div style={{ maxWidth: 480, margin: '0 auto' }}>

        {/* Compact clickable bar — label centered above, % to the right of the bar */}
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          style={{ width: '100%', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
        >
          <div className="font-pixel" style={{
            fontSize: 13,
            color: 'var(--os1-text)',
            textAlign: 'center',
            marginBottom: 8,
            letterSpacing: '0.03em',
          }}>
            {is_ready ? 'Jarvis Knows You' : 'Jarvis Knows About Me...'}
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            {/* Track */}
            <div style={{
              position: 'relative',
              flex: 1,
              height: 7,
              borderRadius: 999,
              overflow: 'hidden',
              background: '#3b3b3b',
            }}>
              {/* Fill — blue */}
              <motion.div
                initial={{ width: 0 }}
                animate={{ width: `${score}%` }}
                transition={{ duration: 0.8, ease: 'easeOut' }}
                style={{
                  height: '100%',
                  borderRadius: 999,
                  background: 'var(--os1-blue)',
                  boxShadow: is_ready ? '0 0 10px rgba(207,138,91,0.55)' : 'none',
                  position: 'relative',
                  overflow: 'hidden',
                }}
              >
                {!is_ready && (
                  <div style={{
                    position: 'absolute',
                    inset: 0,
                    background: 'linear-gradient(90deg, transparent, rgba(255,255,255,0.18), transparent)',
                    animation: 'shimmer 2s infinite',
                  }} />
                )}
              </motion.div>
            </div>

            <span className="font-pixel" style={{
              fontSize: 13,
              color: 'var(--os1-text)',
              flexShrink: 0,
              minWidth: 36,
              textAlign: 'left',
            }}>
              {score}%
            </span>
          </div>
        </button>

        {/* Expanded checkpoint grid */}
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="os1-card"
            style={{
              marginTop: 10,
              padding: '12px 14px',
              overflow: 'hidden',
              background: '#151310',
            }}
          >
            <div style={{
              display: 'grid',
              gridTemplateColumns: '1fr 1fr',
              gap: '7px 14px',
            }}>
              {CHECKPOINTS.map(item => (
                <div key={item.key} style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                  <span style={{
                    width: 9, height: 9, flexShrink: 0,
                    background: checkpoints[item.key] ? 'var(--os1-blue)' : 'transparent',
                    border: `1px solid ${checkpoints[item.key] ? 'var(--os1-blue)' : 'var(--os1-border)'}`,
                  }} />
                  <span className="font-pixel" style={{
                    fontSize: 11,
                    color: checkpoints[item.key] ? 'var(--os1-text-dim)' : 'var(--os1-text-faint)',
                  }}>
                    {item.label}
                  </span>
                </div>
              ))}
            </div>

            {!is_ready && (
              <div style={{
                marginTop: 10,
                paddingTop: 10,
                borderTop: '1px solid var(--os1-border-soft)',
              }}>
                <span className="font-pixel" style={{
                  fontSize: 10,
                  color: 'var(--os1-text-faint)',
                }}>
                  Next: {next_milestone}
                </span>
              </div>
            )}
          </motion.div>
        )}
      </div>
    </div>
  )
}
