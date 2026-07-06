'use client'

import { useCallback, useRef, useState } from 'react'

// ─────────────────────────────────────────────────────────────────────────────
// The Comprehension Knob — a literal rotary dial (not a slider) with three
// snapping detents: Child / Graduate / Expert. Drag it or tap the nearest
// label; it snaps with a small bounce. Used full-size before the first lesson
// is generated, and as a compact "mini" version in the lesson header so
// re-explaining at a different depth is one twist, not a form.
// ─────────────────────────────────────────────────────────────────────────────

const CREAM = '#F3EAD9'

export const LEVELS = [
  { key: 'child', label: 'Child', angle: -58, color: '#ffc266', icon: '☀', caption: 'Explained like a curious 10-year-old — analogies, no jargon, playful tone.' },
  { key: 'graduate', label: 'Graduate', angle: 0, color: '#ff9072', icon: '\u{1F393}', caption: 'Clear and structured — the way a sharp classmate would explain it.' },
  { key: 'expert', label: 'Expert', angle: 58, color: '#c84b31', icon: '\u{1F9E0}', caption: 'Full technical depth — precise terms, edge cases, primary-source rigor.' },
]

function angleForLevel(key) {
  return LEVELS.find(l => l.key === key)?.angle ?? 0
}

function nearestLevel(angleDeg) {
  let best = LEVELS[1]
  let bestDist = Infinity
  for (const l of LEVELS) {
    const d = Math.abs(angleDeg - l.angle)
    if (d < bestDist) { bestDist = d; best = l }
  }
  return best
}

export default function ComprehensionKnob({ level, onChange, mini = false, disabled = false }) {
  const dialRef = useRef(null)
  const [dragging, setDragging] = useState(false)
  const [liveAngle, setLiveAngle] = useState(angleForLevel(level))
  const [justSnapped, setJustSnapped] = useState(false)

  const angle = dragging ? liveAngle : angleForLevel(level)
  const current = LEVELS.find(l => l.key === level) || LEVELS[1]
  const previewLevel = dragging ? nearestLevel(liveAngle) : current

  const angleFromEvent = useCallback((clientX, clientY) => {
    const el = dialRef.current
    if (!el) return 0
    const rect = el.getBoundingClientRect()
    const cx = rect.left + rect.width / 2
    const cy = rect.top + rect.height / 2
    const dx = clientX - cx
    const dy = clientY - cy
    const deg = Math.atan2(dx, -dy) * (180 / Math.PI)
    return Math.max(-75, Math.min(75, deg))
  }, [])

  const onPointerDown = (e) => {
    if (disabled) return
    e.currentTarget.setPointerCapture(e.pointerId)
    setDragging(true)
    setJustSnapped(false)
    setLiveAngle(angleFromEvent(e.clientX, e.clientY))
  }
  const onPointerMove = (e) => {
    if (!dragging || disabled) return
    setLiveAngle(angleFromEvent(e.clientX, e.clientY))
  }
  const onPointerUp = (e) => {
    if (!dragging) return
    setDragging(false)
    const nearest = nearestLevel(liveAngle)
    setJustSnapped(true)
    setTimeout(() => setJustSnapped(false), 260)
    if (nearest.key !== level) onChange(nearest.key)
  }

  const selectLevel = (key) => {
    if (disabled || key === level) return
    setJustSnapped(true)
    setTimeout(() => setJustSnapped(false), 260)
    onChange(key)
  }

  const size = mini ? 64 : 168
  const knobSize = mini ? 40 : 108
  const radius = mini ? 28 : 78

  return (
    <div style={{ display: 'flex', flexDirection: mini ? 'row' : 'column', alignItems: 'center', gap: mini ? 10 : 14, userSelect: 'none' }}>
      <style>{`
        @keyframes knobGlowPulse {
          0%, 100% { opacity: 0.55; }
          50% { opacity: 1; }
        }
      `}</style>

      <div
        ref={dialRef}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        style={{
          position: 'relative', width: size, height: size,
          cursor: disabled ? 'default' : 'grab', touchAction: 'none', flexShrink: 0,
        }}
      >
        {/* Tick labels around the arc (full size only) */}
        {!mini && LEVELS.map(l => {
          const rad = (l.angle * Math.PI) / 180
          const tx = size / 2 + Math.sin(rad) * radius
          const ty = size / 2 - Math.cos(rad) * radius
          const active = previewLevel.key === l.key
          return (
            <div
              key={l.key}
              onClick={() => selectLevel(l.key)}
              style={{
                position: 'absolute', left: tx, top: ty, transform: 'translate(-50%, -50%)',
                display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2,
                cursor: disabled ? 'default' : 'pointer', transition: 'opacity 180ms ease',
                opacity: active ? 1 : 0.45,
              }}
            >
              <span style={{ fontSize: 15 }}>{l.icon}</span>
              <span style={{ fontFamily: 'var(--sans)', fontSize: 10.5, fontWeight: 600, color: active ? l.color : CREAM, letterSpacing: '0.02em' }}>
                {l.label}
              </span>
            </div>
          )
        })}

        {/* Dial body */}
        <div style={{
          position: 'absolute', left: '50%', top: '50%', width: knobSize, height: knobSize,
          transform: 'translate(-50%, -50%)', borderRadius: '50%',
          background: 'radial-gradient(circle at 35% 30%, rgba(255,255,255,0.10), rgba(0,0,0,0.35))',
          border: `1px solid ${previewLevel.color}55`,
          boxShadow: `0 0 ${dragging ? 22 : 14}px ${previewLevel.color}40, inset 0 1px 2px rgba(255,255,255,0.08)`,
          transition: dragging ? 'none' : 'box-shadow 220ms ease, border-color 220ms ease',
        }}>
          {/* Pointer */}
          <div style={{
            position: 'absolute', left: '50%', top: '50%', width: 3, height: knobSize * 0.4,
            background: previewLevel.color, borderRadius: 2,
            transformOrigin: '50% 0%',
            transform: `translate(-50%, 0) rotate(${angle}deg)`,
            transition: dragging ? 'none' : justSnapped ? 'transform 260ms cubic-bezier(.34,1.56,.64,1)' : 'transform 220ms ease',
            boxShadow: `0 0 6px ${previewLevel.color}`,
          }} />
          {!mini && (
            <div style={{
              position: 'absolute', left: '50%', top: '50%', transform: 'translate(-50%, -50%)',
              fontSize: 20, animation: dragging ? 'none' : 'knobGlowPulse 2.4s ease-in-out infinite',
            }}>
              {previewLevel.icon}
            </div>
          )}
        </div>
      </div>

      {mini ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
          <span style={{ fontFamily: 'var(--sans)', fontSize: 12, fontWeight: 700, color: previewLevel.color }}>{previewLevel.label}</span>
          <span style={{ fontFamily: 'var(--sans)', fontSize: 10, color: 'rgba(243,234,217,0.5)' }}>tap arc to re-explain</span>
        </div>
      ) : (
        <div style={{ maxWidth: 230, textAlign: 'center', fontFamily: 'var(--sans)', fontSize: 12.5, lineHeight: 1.45, color: 'rgba(243,234,217,0.75)', minHeight: 36 }}>
          {previewLevel.caption}
        </div>
      )}
    </div>
  )
}
