'use client'
import { useState } from 'react'
import { motion } from 'framer-motion'
import { Lock, Zap } from 'lucide-react'

export default function AutonomousToggle({ userId, apiUrl, isReady, onToggle }) {
  const [isEnabled, setIsEnabled] = useState(false)
  const [showTooltip, setShowTooltip] = useState(false)

  async function handleToggle() {
    if (!isReady) {
      setShowTooltip(true)
      setTimeout(() => setShowTooltip(false), 3000)
      return
    }

    const newState = !isEnabled
    setIsEnabled(newState)
    onToggle?.(newState)

    try {
      await fetch(`${apiUrl}/api/business/autonomous/toggle`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, enabled: newState }),
      })
    } catch (e) {
      console.error('Autonomous toggle failed:', e)
    }
  }

  const knobLeft = isEnabled && isReady ? 'calc(100% - 26px)' : '2px'

  return (
    <div style={{ position: 'relative', display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
      {/* Toggle switch */}
      <button
        onClick={handleToggle}
        title={!isReady ? 'Complete the readiness bar to unlock autonomous mode' : 'Toggle autonomous mode'}
        style={{
          position: 'relative',
          width: 52,
          height: 26,
          borderRadius: 13,
          border: `1px solid ${
            !isReady
              ? 'rgba(243,234,217,0.06)'
              : isEnabled
                ? 'rgba(200,75,49,0.3)'
                : 'rgba(243,234,217,0.1)'
          }`,
          background: !isReady
            ? 'rgba(243,234,217,0.02)'
            : isEnabled
              ? 'rgba(200,75,49,0.12)'
              : 'rgba(243,234,217,0.04)',
          cursor: !isReady ? 'not-allowed' : 'pointer',
          opacity: !isReady ? 0.45 : 1,
          transition: 'all 0.3s ease',
          overflow: 'hidden',
          padding: 0,
        }}
      >
        {/* Glow ring when enabled */}
        {isEnabled && isReady && (
          <div style={{
            position: 'absolute',
            inset: 0,
            borderRadius: 13,
            boxShadow: '0 0 10px rgba(200,75,49,0.2)',
            animation: 'pulse 2s infinite',
          }} />
        )}

        {/* Knob */}
        <motion.div
          animate={{ left: knobLeft }}
          transition={{ type: 'spring', stiffness: 500, damping: 30 }}
          style={{
            position: 'absolute',
            top: 1,
            width: 22,
            height: 22,
            borderRadius: 11,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: isEnabled && isReady
              ? '#c84b31'
              : 'rgba(243,234,217,0.15)',
            boxShadow: isEnabled && isReady ? '0 0 8px rgba(200,75,49,0.4)' : 'none',
            transition: 'background 0.2s ease',
          }}
        >
          {!isReady ? (
            <Lock size={9} color="rgba(243,234,217,0.3)" />
          ) : (
            <Zap size={9} color={isEnabled ? '#0a0a0a' : 'rgba(243,234,217,0.4)'} />
          )}
        </motion.div>
      </button>

      {/* Label */}
      <span style={{
        fontFamily: 'var(--font-arcade), monospace',
        fontSize: 6,
        letterSpacing: '0.1em',
        textTransform: 'uppercase',
        color: isEnabled && isReady ? '#c84b31' : 'rgba(243,234,217,0.2)',
        transition: 'color 0.3s ease',
        userSelect: 'none',
      }}>
        Auto
      </span>

      {/* "Not ready" tooltip */}
      {showTooltip && !isReady && (
        <motion.div
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0 }}
          style={{
            position: 'absolute',
            bottom: '100%',
            left: 0,
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
            fontSize: 6,
            letterSpacing: '0.08em',
            color: '#c84b31',
            marginBottom: 3,
          }}>
            Jarvis needs to know you better first
          </div>
          <div style={{
            fontFamily: 'var(--font-arcade), monospace',
            fontSize: 5,
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
