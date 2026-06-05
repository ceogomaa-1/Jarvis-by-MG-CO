'use client'
import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'

export default function ReadinessBar({ userId, apiUrl, onReadinessUpdate }) {
  const [readiness, setReadiness] = useState(null)
  const [isExpanded, setIsExpanded] = useState(false)

  useEffect(() => {
    if (!userId) return
    fetchReadiness()
    const interval = setInterval(fetchReadiness, 30000)
    return () => clearInterval(interval)
  }, [userId])

  async function fetchReadiness() {
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
    { key: 'name_known',          label: 'Name',         icon: '👤' },
    { key: 'business_known',      label: 'Industry',     icon: '🏢' },
    { key: 'business_name',       label: 'Business',     icon: '📋' },
    { key: 'revenue_context',     label: 'Revenue Goals',icon: '💰' },
    { key: 'first_connector',     label: '1st Tool',     icon: '🔗' },
    { key: 'power_connected',     label: '3+ Tools',     icon: '⚡' },
    { key: 'north_star_set',      label: 'North Star',   icon: '🎯' },
    { key: 'five_memories',       label: '5+ Memories',  icon: '🧠' },
    { key: 'deep_knowledge',      label: 'Deep Context', icon: '📚' },
    { key: 'conversation_depth',  label: 'Chat Depth',   icon: '💬' },
  ]

  return (
    <div style={{ width: '100%', padding: '6px 40px 0' }}>
      <div style={{ maxWidth: 760, margin: '0 auto' }}>

        {/* Compact clickable bar */}
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          style={{ width: '100%', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
            <span style={{
              fontFamily: 'var(--font-arcade), monospace',
              fontSize: 9,
              letterSpacing: '0.12em',
              color: 'rgba(243,234,217,0.3)',
              textTransform: 'uppercase',
            }}>
              {is_ready ? '⚡ Jarvis Ready' : '◈ Jarvis Learning'}
            </span>
            <span style={{
              fontFamily: 'var(--font-arcade), monospace',
              fontSize: 10,
              letterSpacing: '0.1em',
              color: '#c84b31',
            }}>
              {score}%
            </span>
          </div>

          {/* 8-bit progress bar */}
          <div style={{
            position: 'relative',
            width: '100%',
            height: 6,
            borderRadius: 2,
            overflow: 'hidden',
            border: '1px solid rgba(243,234,217,0.08)',
            background: '#0a0a0a',
            imageRendering: 'pixelated',
          }}>
            {/* Pixel grid overlay */}
            <div style={{
              position: 'absolute',
              inset: 0,
              opacity: 0.08,
              backgroundImage: [
                'repeating-linear-gradient(90deg, rgba(243,234,217,0.4) 0px, rgba(243,234,217,0.4) 1px, transparent 1px, transparent 8px)',
                'repeating-linear-gradient(0deg, rgba(243,234,217,0.4) 0px, rgba(243,234,217,0.4) 1px, transparent 1px, transparent 3px)',
              ].join(', '),
              backgroundSize: '8px 3px',
            }} />

            {/* Fill */}
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${score}%` }}
              transition={{ duration: 0.8, ease: 'easeOut' }}
              style={{
                height: '100%',
                position: 'relative',
                background: is_ready
                  ? 'linear-gradient(90deg, #c84b31, #e8634a, #c84b31)'
                  : 'linear-gradient(90deg, #c84b31, #a03d28)',
                boxShadow: is_ready ? '0 0 8px rgba(200,75,49,0.5)' : 'none',
                overflow: 'hidden',
              }}
            >
              {!is_ready && (
                <div style={{
                  position: 'absolute',
                  inset: 0,
                  background: 'linear-gradient(90deg, transparent, rgba(255,255,255,0.12), transparent)',
                  animation: 'shimmer 2s infinite',
                }} />
              )}
            </motion.div>

            {/* Segment markers every 10% */}
            {[...Array(9)].map((_, i) => (
              <div key={i} style={{
                position: 'absolute',
                top: 0,
                bottom: 0,
                width: 1,
                background: 'rgba(243,234,217,0.06)',
                left: `${(i + 1) * 10}%`,
              }} />
            ))}
          </div>
        </button>

        {/* Expanded checkpoint grid */}
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            style={{
              marginTop: 8,
              padding: '10px 12px',
              borderRadius: 10,
              background: 'rgba(243,234,217,0.02)',
              border: '1px solid rgba(243,234,217,0.05)',
              overflow: 'hidden',
            }}
          >
            <div style={{
              display: 'grid',
              gridTemplateColumns: '1fr 1fr',
              gap: '6px 12px',
            }}>
              {CHECKPOINTS.map(item => (
                <div key={item.key} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span style={{ fontSize: 9 }}>{checkpoints[item.key] ? '✅' : '⬜'}</span>
                  <span style={{
                    fontFamily: 'var(--font-arcade), monospace',
                    fontSize: 8,
                    letterSpacing: '0.08em',
                    color: checkpoints[item.key] ? 'rgba(243,234,217,0.55)' : 'rgba(243,234,217,0.2)',
                  }}>
                    {item.label}
                  </span>
                </div>
              ))}
            </div>

            {!is_ready && (
              <div style={{
                marginTop: 8,
                paddingTop: 8,
                borderTop: '1px solid rgba(243,234,217,0.04)',
              }}>
                <span style={{
                  fontFamily: 'var(--font-arcade), monospace',
                  fontSize: 5,
                  letterSpacing: '0.08em',
                  color: 'rgba(200,75,49,0.6)',
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
