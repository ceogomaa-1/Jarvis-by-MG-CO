'use client'
import { useState } from 'react'
import { motion } from 'framer-motion'

// OS1 v2 — pixel-art lever switch + "Autonomous Jarvis" label (per Figma)
export default function AutonomousToggle({ userId, apiUrl, isReady, onToggle }) {
  const [isEnabled, setIsEnabled] = useState(false)
  const [showTooltip, setShowTooltip] = useState(false)

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
      {/* Pixel lever */}
      <button
        onClick={handleToggle}
        title={!isReady ? 'Complete the readiness bar to unlock' : 'Autonomous Jarvis'}
        style={{
          position: 'relative',
          width: 34,
          height: 44,
          background: 'transparent',
          border: 'none',
          cursor: isReady ? 'pointer' : 'not-allowed',
          opacity: !isReady ? 0.45 : 1,
          padding: 0,
          transition: 'opacity 0.3s ease',
        }}
      >
        <svg width="34" height="44" viewBox="0 0 34 44" style={{ display: 'block' }}>
          {/* Base block (pixel) */}
          <rect x="6" y="34" width="22" height="8" fill="none" stroke={active ? 'var(--os1-blue)' : 'var(--os1-text-dim)'} strokeWidth="2" />
          <rect x="12" y="37" width="10" height="2" fill={active ? 'var(--os1-blue)' : 'var(--os1-text-dim)'} />
          {/* Lever arm — angled when off, upright when on */}
          <motion.g
            animate={{ rotate: active ? 0 : 38 }}
            transition={{ type: 'spring', stiffness: 260, damping: 17 }}
            style={{ originX: '17px', originY: '34px' }}
          >
            <rect x="15.5" y="12" width="3" height="22" fill={active ? 'var(--os1-blue)' : 'var(--os1-text-dim)'} />
            {/* Knob — pixel circle */}
            <rect x="11" y="4" width="12" height="3" fill={active ? 'var(--os1-blue)' : 'var(--os1-text-dim)'} />
            <rect x="9" y="7" width="16" height="6" fill={active ? 'var(--os1-blue)' : 'var(--os1-text-dim)'} />
            <rect x="11" y="13" width="12" height="3" fill={active ? 'var(--os1-blue)' : 'var(--os1-text-dim)'} />
          </motion.g>
        </svg>
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
