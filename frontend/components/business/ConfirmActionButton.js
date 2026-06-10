'use client'
import { useState, useRef } from 'react'
import { motion } from 'framer-motion'
import { Check, X } from 'lucide-react'

const HOLD_DURATION = 2000

export default function ConfirmActionButton({ action, onConfirm, onCancel }) {
  const [state, setState] = useState('idle') // idle | holding | confirmed | cancelled
  const [progress, setProgress] = useState(0)
  const timerRef = useRef(null)
  const intervalRef = useRef(null)
  const startRef = useRef(0)

  function startHold() {
    if (state !== 'idle') return
    setState('holding')
    setProgress(0)
    startRef.current = Date.now()

    intervalRef.current = setInterval(() => {
      const elapsed = Date.now() - startRef.current
      const pct = Math.min((elapsed / HOLD_DURATION) * 100, 100)
      setProgress(pct)
      if (pct >= 100) clearInterval(intervalRef.current)
    }, 30)

    timerRef.current = setTimeout(() => {
      setState('confirmed')
      clearInterval(intervalRef.current)
      if (navigator?.vibrate) navigator.vibrate(60)
      onConfirm?.()
    }, HOLD_DURATION)
  }

  function cancelHold() {
    if (state !== 'holding') return
    clearTimeout(timerRef.current)
    clearInterval(intervalRef.current)
    setProgress(0)
    setState('idle')
  }

  function handleCancel() {
    setState('cancelled')
    onCancel?.()
  }

  if (state === 'confirmed') {
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, paddingTop: 8, paddingBottom: 8 }}>
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          padding: '6px 12px',
          borderRadius: 10,
          background: 'rgba(127,176,105,0.08)',
          border: '1px solid rgba(127,176,105,0.2)',
        }}>
          <Check size={11} color="#7fb069" />
          <span style={{
            fontFamily: 'var(--font-pixel), monospace',
            fontSize: 10,
            letterSpacing: '0.08em',
            color: '#7fb069',
          }}>
            Confirmed
          </span>
        </div>
      </div>
    )
  }

  if (state === 'cancelled') {
    return (
      <div style={{ paddingTop: 8, paddingBottom: 8 }}>
        <span style={{
          fontFamily: 'var(--font-pixel), monospace',
          fontSize: 7,
          letterSpacing: '0.08em',
          color: 'rgba(232,232,232,0.25)',
        }}>
          Action cancelled
        </span>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, paddingTop: 8, paddingBottom: 8 }}>
      {/* Hold-to-confirm button */}
      <button
        onMouseDown={startHold}
        onMouseUp={cancelHold}
        onMouseLeave={cancelHold}
        onTouchStart={startHold}
        onTouchEnd={cancelHold}
        style={{
          position: 'relative',
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '8px 14px',
          borderRadius: 10,
          fontFamily: 'var(--font-pixel), monospace',
          fontSize: 7,
          letterSpacing: '0.08em',
          textTransform: 'uppercase',
          cursor: 'pointer',
          userSelect: 'none',
          overflow: 'hidden',
          border: state === 'holding'
            ? '1px solid rgba(45,127,249,0.4)'
            : '1px solid rgba(45,127,249,0.2)',
          background: state === 'holding'
            ? '#2d7ff9'
            : 'rgba(45,127,249,0.08)',
          color: state === 'holding' ? '#0a0a0a' : '#2d7ff9',
          transform: state === 'holding' ? 'scale(0.98)' : 'scale(1)',
          transition: 'background 0.15s ease, color 0.15s ease, transform 0.1s ease',
        }}
      >
        {/* Sweep-drain overlay while holding */}
        {state === 'holding' && (
          <div style={{
            position: 'absolute',
            top: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(0,0,0,0.15)',
            width: `${100 - progress}%`,
            transition: 'width 30ms linear',
            pointerEvents: 'none',
          }} />
        )}

        {/* Circular progress ring */}
        {state === 'holding' && (
          <svg
            width={16}
            height={16}
            viewBox="0 0 36 36"
            style={{ flexShrink: 0, position: 'relative', zIndex: 1 }}
          >
            <circle cx="18" cy="18" r="15.9" fill="none" stroke="rgba(10,10,10,0.2)" strokeWidth="3" />
            <circle
              cx="18" cy="18" r="15.9"
              fill="none"
              stroke="#0a0a0a"
              strokeWidth="3"
              strokeLinecap="round"
              strokeDasharray={`${progress} 100`}
              transform="rotate(-90 18 18)"
            />
          </svg>
        )}

        <span style={{ position: 'relative', zIndex: 1 }}>
          {state === 'holding' ? 'Hold…' : `Confirm: ${action}`}
        </span>
      </button>

      {/* Cancel */}
      <button
        onClick={handleCancel}
        style={{
          padding: '8px 12px',
          borderRadius: 10,
          fontFamily: 'var(--font-pixel), monospace',
          fontSize: 7,
          letterSpacing: '0.08em',
          color: 'rgba(232,232,232,0.3)',
          background: 'none',
          border: '1px solid rgba(232,232,232,0.06)',
          cursor: 'pointer',
          transition: 'color 0.2s ease, border-color 0.2s ease',
        }}
        onMouseEnter={e => {
          e.currentTarget.style.color = 'rgba(232,232,232,0.6)'
          e.currentTarget.style.borderColor = 'rgba(232,232,232,0.1)'
        }}
        onMouseLeave={e => {
          e.currentTarget.style.color = 'rgba(232,232,232,0.3)'
          e.currentTarget.style.borderColor = 'rgba(232,232,232,0.06)'
        }}
      >
        Cancel
      </button>
    </div>
  )
}
