'use client'
import { useState } from 'react'
import { motion } from 'framer-motion'

// OS1 v2 — horizontal pixel rocker switch + "Autonomous Jarvis" label (per Figma).
// Batch 71 (Co-Founder Mode): now a controlled trigger — clicking it never flips
// the flag directly; it opens the CoFounderLever modal, which owns the whole
// engage/disengage moment. Parent (ChatCanvas) hydrates + owns `enabled`.
export default function AutonomousToggle({ isReady, enabled, onRequestToggle }) {
  const [showTooltip, setShowTooltip] = useState(false)

  function handleClick() {
    if (!isReady) {
      setShowTooltip(true)
      setTimeout(() => setShowTooltip(false), 3000)
      return
    }
    onRequestToggle?.()
  }

  const active = enabled && isReady

  return (
    <div style={{ position: 'relative', display: 'flex', alignItems: 'center', gap: 10 }}>
      {/* Horizontal pixel rocker switch */}
      <button
        onClick={handleClick}
        title={!isReady ? 'Complete the readiness bar to unlock' : 'Co-Founder Mode'}
        style={{
          position: 'relative',
          flexShrink: 0,
          width: 56,
          height: 26,
          borderRadius: 999,
          border: `1px solid ${active ? '#cf8a5b' : '#3a332b'}`,
          background: active ? 'rgba(207,138,91,0.25)' : '#221e19',
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
          fontSize: 7, lineHeight: 1, color: active ? '#cf8a5b' : '#6a6a6a', userSelect: 'none',
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
            background: active ? '#cf8a5b' : '#8c857b',
            boxShadow: active ? '0 0 10px rgba(207,138,91,0.6)' : 'none',
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
            background: '#171411',
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
