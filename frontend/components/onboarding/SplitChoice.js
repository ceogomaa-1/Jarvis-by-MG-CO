'use client'
import { useState, useEffect, useRef } from 'react'
import { motion } from 'framer-motion'
import { supabase } from '../../lib/supabase'
import BusinessOnboardingModal from './BusinessOnboardingModal'

// ─── Minimal orb (self-contained, no props needed from page.js) ──────────────
function MiniOrb({ size = 180, accent = '#ff9072' }) {
  const canvasRef = useRef(null)
  const rafRef = useRef(null)
  const tRef = useRef(0)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    const dpr = window.devicePixelRatio || 1
    canvas.width = size * dpr
    canvas.height = size * dpr
    canvas.style.width = `${size}px`
    canvas.style.height = `${size}px`
    ctx.scale(dpr, dpr)

    const h = parseInt(accent.replace('#', ''), 16)
    const ar = (h >> 16) & 255
    const ag = (h >> 8) & 255
    const ab = h & 255

    const draw = () => {
      tRef.current += 0.016
      const t = tRef.current
      const cx = size / 2, cy = size / 2
      const r = size * 0.32

      ctx.clearRect(0, 0, size, size)

      // Sphere base
      const sphere = ctx.createRadialGradient(cx - r * 0.3, cy - r * 0.4, r * 0.05, cx, cy, r * 1.2)
      sphere.addColorStop(0, `rgba(${Math.min(ar + 40, 255)},${Math.min(ag + 30, 255)},${Math.min(ab + 30, 255)},0.9)`)
      sphere.addColorStop(0.5, `rgba(${ar},${ag},${ab},0.45)`)
      sphere.addColorStop(1, `rgba(${ar},${ag},${ab},0)`)
      ctx.fillStyle = sphere
      ctx.beginPath()
      ctx.arc(cx, cy, r * 1.15, 0, Math.PI * 2)
      ctx.fill()

      // Orbit particles
      ctx.save()
      ctx.globalCompositeOperation = 'screen'
      for (let i = 0; i < 4; i++) {
        const phase = t * (0.5 + i * 0.12) + i * 1.4
        const orbitR = r * (0.38 + 0.1 * Math.sin(t * 0.7 + i))
        const x = cx + Math.cos(phase) * orbitR
        const y = cy + Math.sin(phase * 1.1) * orbitR * 0.8
        const br = r * (0.38 + 0.15 * Math.sin(t * 1.1 + i))
        const hShift = i * 16 - 16
        const gr = ctx.createRadialGradient(x, y, 0, x, y, br)
        gr.addColorStop(0, `rgba(${Math.min(ar + hShift, 255)},${ag},${ab},0.5)`)
        gr.addColorStop(1, `rgba(${ar},${ag},${ab},0)`)
        ctx.fillStyle = gr
        ctx.beginPath()
        ctx.arc(x, y, br, 0, Math.PI * 2)
        ctx.fill()
      }
      ctx.restore()

      // Core highlight
      const core = ctx.createRadialGradient(cx, cy, 0, cx, cy, r * 0.5)
      core.addColorStop(0, `rgba(255,240,225,0.4)`)
      core.addColorStop(1, 'rgba(0,0,0,0)')
      ctx.fillStyle = core
      ctx.beginPath()
      ctx.arc(cx, cy, r * 0.5, 0, Math.PI * 2)
      ctx.fill()

      // Slow idle pulse ring
      const pulse = (Math.sin(t * 0.6) + 1) / 2
      ctx.beginPath()
      ctx.arc(cx, cy, r * (1.05 + pulse * 0.08), 0, Math.PI * 2)
      ctx.strokeStyle = `rgba(${ar},${ag},${ab},${0.25 + pulse * 0.15})`
      ctx.lineWidth = 1
      ctx.stroke()

      rafRef.current = requestAnimationFrame(draw)
    }
    draw()
    return () => cancelAnimationFrame(rafRef.current)
  }, [size, accent])

  return <canvas ref={canvasRef} style={{ display: 'block' }} />
}

// ─── Business geometric icon ──────────────────────────────────────────────────
function BusinessIcon({ size = 160 }) {
  const s = size
  const c = s / 2
  const amber = '#f59e0b'

  return (
    <svg width={s} height={s} viewBox={`0 0 ${s} ${s}`} fill="none" style={{ display: 'block' }}>
      {/* Outer ring */}
      <circle cx={c} cy={c} r={c * 0.78} stroke={amber} strokeWidth="0.8" strokeOpacity="0.2" />
      {/* Inner ring */}
      <circle cx={c} cy={c} r={c * 0.5} stroke={amber} strokeWidth="0.8" strokeOpacity="0.3" />

      {/* Building / graph bars */}
      {[0.28, 0.42, 0.56, 0.7].map((x, i) => {
        const heights = [0.35, 0.55, 0.45, 0.65]
        const bw = 0.1
        const bh = heights[i]
        const bx = c * (2 * x - 1) + c - (bw * s) / 2
        const by = c + c * 0.3 - bh * c * 0.7
        return (
          <rect
            key={i}
            x={bx} y={by}
            width={bw * s} height={bh * c * 0.7}
            rx={2}
            fill={amber}
            fillOpacity={0.15 + i * 0.12}
          />
        )
      })}

      {/* Trend line */}
      <polyline
        points={`${c * 0.38},${c * 1.12} ${c * 0.7},${c * 0.82} ${c * 0.98},${c * 0.95} ${c * 1.28},${c * 0.62} ${c * 1.62},${c * 0.78}`}
        stroke={amber}
        strokeWidth="1.5"
        strokeOpacity="0.85"
        fill="none"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* Arrow head */}
      <polyline
        points={`${c * 1.48},${c * 0.68} ${c * 1.62},${c * 0.78} ${c * 1.55},${c * 0.9}`}
        stroke={amber}
        strokeWidth="1.5"
        strokeOpacity="0.85"
        fill="none"
        strokeLinecap="round"
        strokeLinejoin="round"
      />

      {/* Connecting dots */}
      {[[0.38, 1.12], [0.7, 0.82], [0.98, 0.95], [1.28, 0.62], [1.62, 0.78]].map(([x, y], i) => (
        <circle key={i} cx={c * x} cy={c * y} r={2.5} fill={amber} fillOpacity={0.6} />
      ))}

      {/* Center glow */}
      <circle cx={c} cy={c} r={c * 0.12} fill={amber} fillOpacity="0.1" />
    </svg>
  )
}

// ─── Card component ───────────────────────────────────────────────────────────
function ChoiceCard({ mode, onPersonalClick, onBusinessClick }) {
  const isPersonal = mode === 'personal'
  const [hovered, setHovered] = useState(false)

  const accent = isPersonal ? '#ff9072' : '#f59e0b'
  const badge = isPersonal ? 'PERSONAL' : 'FOR BUSINESS'
  const title = 'JARVIS'
  const subtitle = isPersonal
    ? 'Your personal AI. Always present.'
    : 'Your business operator. Smarter than a 25-year veteran.'
  const tagline = isPersonal ? 'Memory · Voice · Companion.' : 'Insights · Action · Growth.'
  const cta = isPersonal ? 'Sign in with Google' : 'Get Started'

  const handleClick = isPersonal ? onPersonalClick : onBusinessClick

  return (
    <motion.div
      onHoverStart={() => setHovered(true)}
      onHoverEnd={() => setHovered(false)}
      whileHover={{ scale: 1.025 }}
      transition={{ duration: 0.25, ease: [0.25, 0.1, 0.25, 1] }}
      onClick={handleClick}
      style={{
        flex: 1,
        minWidth: 0,
        background: hovered
          ? `rgba(${isPersonal ? '255,144,114' : '245,158,11'},0.04)`
          : 'rgba(243,234,217,0.02)',
        border: `1px solid ${hovered
          ? `rgba(${isPersonal ? '255,144,114' : '245,158,11'},0.25)`
          : 'rgba(243,234,217,0.08)'}`,
        borderRadius: 20,
        padding: '48px 36px',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        cursor: 'pointer',
        transition: 'background 0.25s, border-color 0.25s',
        boxShadow: hovered
          ? `0 0 60px rgba(${isPersonal ? '255,144,114' : '245,158,11'},0.06)`
          : 'none',
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      {/* Top badge */}
      <div style={{
        fontFamily: 'system-ui, sans-serif',
        fontSize: 10,
        letterSpacing: '0.2em',
        color: accent,
        background: `rgba(${isPersonal ? '255,144,114' : '245,158,11'},0.1)`,
        border: `1px solid rgba(${isPersonal ? '255,144,114' : '245,158,11'},0.2)`,
        borderRadius: 100,
        padding: '3px 12px',
        marginBottom: 28,
      }}>
        {badge}
      </div>

      {/* Title */}
      <div style={{
        fontFamily: 'Georgia, serif',
        fontSize: 42,
        letterSpacing: '0.22em',
        color: '#f3ead9',
        fontWeight: 400,
        marginBottom: 20,
        lineHeight: 1,
      }}>
        {title}
      </div>

      {/* Visual */}
      <div style={{ marginBottom: 28, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        {isPersonal
          ? <MiniOrb size={160} accent="#ff9072" />
          : <BusinessIcon size={160} />
        }
      </div>

      {/* Subtitle */}
      <div style={{
        fontFamily: 'system-ui, sans-serif',
        fontSize: 14,
        color: 'rgba(243,234,217,0.6)',
        textAlign: 'center',
        lineHeight: 1.55,
        marginBottom: 14,
        maxWidth: 260,
      }}>
        {subtitle}
      </div>

      {/* Tagline */}
      <div style={{
        fontFamily: 'system-ui, sans-serif',
        fontSize: 11,
        letterSpacing: '0.14em',
        color: `rgba(${isPersonal ? '255,144,114' : '245,158,11'},0.7)`,
        marginBottom: 36,
      }}>
        {tagline}
      </div>

      {/* CTA */}
      <motion.button
        whileHover={{ scale: 1.04 }}
        whileTap={{ scale: 0.97 }}
        onClick={e => { e.stopPropagation(); handleClick() }}
        style={{
          padding: '12px 32px',
          background: `rgba(${isPersonal ? '255,144,114' : '245,158,11'},0.1)`,
          border: `1px solid rgba(${isPersonal ? '255,144,114' : '245,158,11'},0.3)`,
          borderRadius: 8,
          color: accent,
          fontFamily: 'system-ui, sans-serif',
          fontSize: 12,
          letterSpacing: '0.08em',
          cursor: 'pointer',
        }}
      >
        {cta}
      </motion.button>
    </motion.div>
  )
}

// ─── SplitChoice ──────────────────────────────────────────────────────────────
export default function SplitChoice() {
  const [showBizModal, setShowBizModal] = useState(false)

  const handlePersonalClick = async () => {
    if (!supabase) return
    await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: { redirectTo: `${window.location.origin}/auth/callback?next=${encodeURIComponent('/?onboard=personal')}` },
    })
  }

  return (
    <>
      <motion.div
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.55, ease: [0.25, 0.1, 0.25, 1] }}
        style={{
          minHeight: '100vh',
          background: '#0a0a0a',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '40px 24px',
        }}
      >
        {/* Wordmark */}
        <motion.div
          initial={{ opacity: 0, y: -16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1, duration: 0.5 }}
          style={{
            fontFamily: 'Georgia, serif',
            fontSize: 13,
            letterSpacing: '0.55em',
            color: 'rgba(243,234,217,0.35)',
            textTransform: 'uppercase',
            marginBottom: 56,
          }}
        >
          JARVIS
        </motion.div>

        {/* Cards */}
        <div style={{
          display: 'flex',
          flexDirection: 'row',
          gap: 24,
          width: '100%',
          maxWidth: 960,
        }}
          className="split-cards"
        >
          <ChoiceCard
            mode="personal"
            onPersonalClick={handlePersonalClick}
            onBusinessClick={() => setShowBizModal(true)}
          />
          <ChoiceCard
            mode="business"
            onPersonalClick={handlePersonalClick}
            onBusinessClick={() => setShowBizModal(true)}
          />
        </div>

        {/* Footer */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.4, duration: 0.6 }}
          style={{
            marginTop: 36,
            fontFamily: 'system-ui, sans-serif',
            fontSize: 11,
            color: 'rgba(243,234,217,0.2)',
            letterSpacing: '0.08em',
          }}
        >
          Choose your path. You can switch anytime.
        </motion.div>
      </motion.div>

      {showBizModal && (
        <BusinessOnboardingModal onClose={() => setShowBizModal(false)} />
      )}

      <style>{`
        @media (max-width: 768px) {
          .split-cards {
            flex-direction: column !important;
          }
        }
      `}</style>
    </>
  )
}
