'use client'
import { useState } from 'react'
import { motion } from 'framer-motion'
import { Lock } from 'lucide-react'

export default function AutonomousToggle({ userId, apiUrl, isReady, onToggle }) {
  const [isEnabled, setIsEnabled] = useState(false)
  const [showTooltip, setShowTooltip] = useState(false)

  function handleClick() {
    if (!isReady) {
      setShowTooltip(true)
      setTimeout(() => setShowTooltip(false), 3000)
      return
    }
    const newState = !isEnabled
    setIsEnabled(newState)
    onToggle?.(newState)
    fetch(`${apiUrl}/api/business/autonomous/toggle`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: userId, enabled: newState }),
    }).catch(console.error)
  }

  const containerClass = [
    'lever-toggle',
    isEnabled && isReady ? 'enabled' : '',
    !isReady ? 'locked' : '',
  ].filter(Boolean).join(' ')

  return (
    <div style={{ position: 'relative', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 5 }}>
      {/* Lever switch */}
      <div className={containerClass} onClick={handleClick} title={!isReady ? 'Complete the readiness bar to unlock' : undefined}>
        <div className="lever-toggle-handle-wrapper">
          <div className="lever-toggle-handle">
            <div className="lever-toggle-knob">
              {!isReady && <Lock size={6} color="rgba(243,234,217,0.35)" />}
            </div>
            <div className="lever-toggle-bar-wrapper">
              <div className="lever-toggle-bar" />
            </div>
          </div>
        </div>
        <div className="lever-toggle-base">
          <div className="lever-toggle-base-inside" />
        </div>
      </div>

      {/* Label */}
      <span style={{
        fontFamily: 'var(--font-arcade), monospace',
        fontSize: 9,
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
