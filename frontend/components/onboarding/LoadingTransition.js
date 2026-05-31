'use client'
import { useEffect, useRef, useState } from 'react'
import { playSound } from '../../lib/soundPlayer'

const STAGES = [
  'Initializing...',
  'Learning your profile...',
  'Waking up...',
  'Ready.',
]

export default function LoadingTransition({ onComplete }) {
  const [progress, setProgress] = useState(0)
  const [stageIndex, setStageIndex] = useState(0)
  const [fading, setFading] = useState(false)
  const completedRef = useRef(false)

  useEffect(() => {
    const total = 2800
    const interval = 30
    let elapsed = 0

    const timer = setInterval(() => {
      elapsed += interval
      const pct = Math.min(elapsed / total, 1)
      setProgress(pct)
      setStageIndex(Math.min(Math.floor(pct * STAGES.length), STAGES.length - 1))

      if (pct >= 1 && !completedRef.current) {
        completedRef.current = true
        clearInterval(timer)
        playSound('transition')
        setTimeout(() => {
          setFading(true)
          setTimeout(onComplete, 600)
        }, 400)
      }
    }, interval)

    return () => clearInterval(timer)
  }, [onComplete])

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 100,
      background: '#0a0a0a',
      display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center',
      opacity: fading ? 0 : 1,
      transition: 'opacity 600ms ease',
    }}>
      {/* Orb pulse */}
      <div style={{
        width: 80, height: 80, borderRadius: '50%',
        background: 'radial-gradient(circle at 35% 35%, rgba(255,180,160,0.9), rgba(200,75,49,0.4) 60%, transparent)',
        boxShadow: `0 0 ${40 + progress * 40}px rgba(200,75,49,${(0.2 + progress * 0.3).toFixed(2)})`,
        marginBottom: 40,
        animation: 'orbPulse 1.8s ease-in-out infinite',
      }} />

      {/* Progress bar */}
      <div style={{
        width: 240, height: 1,
        background: 'rgba(243,234,217,0.1)',
        borderRadius: 1, marginBottom: 20, overflow: 'hidden',
      }}>
        <div style={{
          height: '100%',
          width: `${progress * 100}%`,
          background: 'linear-gradient(90deg, rgba(200,75,49,0.6), #c84b31)',
          borderRadius: 1,
          transition: 'width 30ms linear',
        }} />
      </div>

      {/* Stage label */}
      <div style={{
        fontFamily: 'system-ui, sans-serif',
        fontSize: 11,
        letterSpacing: '0.22em',
        color: 'rgba(243,234,217,0.4)',
        textTransform: 'uppercase',
      }}>
        {STAGES[stageIndex]}
      </div>

      <style>{`
        @keyframes orbPulse {
          0%, 100% { transform: scale(1); opacity: 0.8; }
          50%       { transform: scale(1.12); opacity: 1; }
        }
      `}</style>
    </div>
  )
}
