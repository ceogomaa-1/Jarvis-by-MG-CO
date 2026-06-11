'use client'
import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'

// OS1 v2 — horizontal pixel rocker switch + "Autonomous Jarvis" label (per Figma)
export default function AutonomousToggle({ userId, apiUrl, isReady, onToggle }) {
  const [isEnabled, setIsEnabled] = useState(false)
  const [showTooltip, setShowTooltip] = useState(false)

  // Hydrate from backend so the switch survives refreshes/sessions.
  useEffect(() => {
    if (!userId) return
    fetch(`${apiUrl}/api/business/autonomous/state?user_id=${encodeURIComponent(userId)}`)
      .then(res => res.json())
      .then(data => {
        if (data?.enabled) {
          setIsEnabled(true)
          onToggle?.(true)
        }
      })
      .catch(console.error)
  }, [userId, apiUrl]) // eslint-disable-line react-hooks/exhaustive-deps

  function handleToggle() {
    if (!isReady) {
      setShowTooltip(true)
      setTimeout(() => setShowTooltip(false), 3000)
      return
    }
    const next = !isEnabled
    setIsEnabled(next)
    onToggle?.(next)
    fetch(`${apiUrl}/api/business/autonomous/toggle`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: userId, enabled: next }),
    }).catch(console.error)
  }

  const active = isEnabled && isReady

  return (
    <div style={{ position: 'relative', display: 'flex', alignItems: 'center', gap: 10 }}>
      {/* Horizontal pixel rocker switch */}
      <button
        onClick={handleToggle}
        title={!isReady ? 'Complete the readiness bar to unlock' : 'Autonomous Jarvis'}
        style={{
          position: 'relative',
          flexShrink: 0,
          width: 56,
          height: 26,
          borderRadius: 999,
          border: `1px solid ${active ? '#2d7ff9' : '#3d3d3d'}`,
          background: active ? 'rgba(45,127,249,0.25)' : '#2e2e2e',
          cursor: isReady ? 'pointer' : 'not-allowed',
          opacity: !isReady ? 0.45 : 1,
          padding: 0,
          transition: 'background 0.3s ease, border-color 0.3s ease, opacity 0.3s ease',
        }}
      >
        {/* Micro-labels */}
        <span className="font-pixel" style={{
          position: 'absolute', left: 6, top: '50%', transform: 'translateY(-50%)',
          fontSize: 7, lineHeight: 1, color: '#6a6a6a', userSelect: 'none',
        }}>
          OFF
        </span>
        <span className="font-pixel" style={{
          position: 'absolute', right: 6, top: '50%', transform: 'translateY(-50%)',
          fontSize: 7, lineHeight: 1, color: active ? '#2d7ff9' : '#6a6a6a', userSelect: 'none',
          transition: 'color 0.3s ease',
        }}>
          ON
        </span>

        {/* Knob */}
        <motion.div
          animate={{ x: active ? 30 : 0 }}
          transition={{ type: 'spring', stiffness: 500, damping: 30 }}
          style={{
            position: 'absolute', top: 2, left: 2,
            width: 20, height: 20, borderRadius: 4,
            background: active ? '#2d7ff9' : '#8a8a8a',
            boxShadow: active ? '0 0 10px rgba(45,127,249,0.6)' : 'none',
          }}
        />
      </button>

      {/* Label */}
      <div className="font-pixel" style={{
        fontSize: 12,
        lineHeight: 1.45,
        color: active ? 'var(--os1-text)' : 'var(--os1-text-dim)',
        transition: 'color 0.3s ease',
        userSelect: 'none',
        textAlign: 'left',
      }}>
        Autonomous<br />Jarvis
      </div>

      {/* Not-ready tooltip */}
      {showTooltip && !isReady && (
        <motion.div
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0 }}
          className="os1-card"
          style={{
            position: 'absolute',
            bottom: '100%',
            right: 0,
            marginBottom: 10,
            padding: '10px 13px',
            background: '#1a1a1a',
            whiteSpace: 'nowrap',
            zIndex: 50,
            pointerEvents: 'none',
          }}
        >
          <div className="font-pixel" style={{ fontSize: 12, color: 'var(--os1-text)', marginBottom: 3 }}>
            Jarvis needs to know you better first
          </div>
          <div className="font-pixel" style={{ fontSize: 10, color: 'var(--os1-text-faint)' }}>
            Complete the readiness bar to unlock
          </div>
        </motion.div>
      )}
    </div>
  )
}
