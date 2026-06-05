'use client'
import { useState } from 'react'
import { motion } from 'framer-motion'
import { Lock, Zap } from 'lucide-react'

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
    <div style={{ position: 'relative', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 5 }}>
      {/* Lever housing */}
      <button
        onClick={handleToggle}
        title={!isReady ? 'Complete the readiness bar to unlock' : undefined}
        style={{
          position: 'relative',
          width: 40,
          height: 80,
          borderRadius: 12,
          background: 'rgba(243,234,217,0.03)',
          border: `1px solid ${active ? 'rgba(200,75,49,0.25)' : 'rgba(243,234,217,0.08)'}`,
          cursor: isReady ? 'pointer' : 'not-allowed',
          opacity: !isReady ? 0.45 : 1,
          overflow: 'hidden',
          transition: 'border-color 0.3s ease, opacity 0.3s ease',
          padding: 0,
        }}
      >
        {/* Groove track */}
        <div style={{
          position: 'absolute',
          left: '50%',
          top: 10,
          bottom: 10,
          width: 3,
          transform: 'translateX(-50%)',
          borderRadius: 2,
          background: 'rgba(243,234,217,0.05)',
        }} />

        {/* OFF label — top */}
        <span style={{
          position: 'absolute',
          top: 3,
          left: '50%',
          transform: 'translateX(-50%)',
          fontFamily: 'var(--font-arcade), monospace',
          fontSize: 5,
          letterSpacing: '0.08em',
          color: active ? 'rgba(243,234,217,0.1)' : 'rgba(243,234,217,0.22)',
          userSelect: 'none',
          transition: 'color 0.3s ease',
        }}>
          OFF
        </span>

        {/* ON label — bottom */}
        <span style={{
          position: 'absolute',
          bottom: 3,
          left: '50%',
          transform: 'translateX(-50%)',
          fontFamily: 'var(--font-arcade), monospace',
          fontSize: 5,
          letterSpacing: '0.08em',
          color: active ? '#c84b31' : 'rgba(243,234,217,0.12)',
          userSelect: 'none',
          transition: 'color 0.3s ease',
        }}>
          ON
        </span>

        {/* Lever handle — rod + knob, moves as a unit */}
        <motion.div
          animate={{ top: active ? 38 : 12 }}
          transition={{ type: 'spring', stiffness: 280, damping: 18, mass: 1.2 }}
          style={{
            position: 'absolute',
            left: '50%',
            transform: 'translateX(-50%)',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: 0,
          }}
        >
          {/* Rod */}
          <div style={{
            width: 3,
            height: 14,
            borderRadius: 2,
            background: active
              ? 'linear-gradient(180deg, rgba(200,75,49,0.6), #c84b31)'
              : 'rgba(243,234,217,0.12)',
            transition: 'background 0.28s ease',
          }} />

          {/* Knob */}
          <div style={{
            width: 22,
            height: 22,
            borderRadius: '50%',
            background: active
              ? 'radial-gradient(circle at 35% 35%, #e8634a, #c84b31)'
              : 'rgba(243,234,217,0.07)',
            border: `1.5px solid ${active ? 'rgba(200,75,49,0.5)' : 'rgba(243,234,217,0.15)'}`,
            boxShadow: active ? '0 0 14px rgba(200,75,49,0.55), 0 0 4px rgba(200,75,49,0.9)' : 'none',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            transition: 'background 0.28s ease, border-color 0.28s ease, box-shadow 0.28s ease',
            flexShrink: 0,
          }}>
            {!isReady
              ? <Lock size={8} color="rgba(243,234,217,0.3)" />
              : <Zap size={8} color={active ? '#0a0a0a' : 'rgba(243,234,217,0.3)'} />
            }
          </div>
        </motion.div>
      </button>

      {/* Label */}
      <span style={{
        fontFamily: 'var(--font-arcade), monospace',
        fontSize: 9,
        letterSpacing: '0.1em',
        textTransform: 'uppercase',
        color: active ? '#c84b31' : 'rgba(243,234,217,0.2)',
        transition: 'color 0.3s ease',
        userSelect: 'none',
      }}>
        Auto
      </span>

      {/* Not-ready tooltip */}
      {showTooltip && !isReady && (
        <motion.div
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0 }}
          style={{
            position: 'absolute',
            bottom: '100%',
            left: '50%',
            transform: 'translateX(-50%)',
            marginBottom: 8,
            padding: '8px 12px',
            borderRadius: 10,
            background: 'rgba(15,15,18,0.95)',
            border: '1px solid rgba(243,234,217,0.08)',
            whiteSpace: 'nowrap',
            zIndex: 50,
            pointerEvents: 'none',
          }}
        >
          <div style={{
            fontFamily: 'var(--font-arcade), monospace',
            fontSize: 9,
            letterSpacing: '0.08em',
            color: '#c84b31',
            marginBottom: 3,
          }}>
            Jarvis needs to know you better first
          </div>
          <div style={{
            fontFamily: 'var(--font-arcade), monospace',
            fontSize: 8,
            letterSpacing: '0.08em',
            color: 'rgba(243,234,217,0.35)',
          }}>
            Complete the readiness bar to unlock
          </div>
        </motion.div>
      )}
    </div>
  )
}
