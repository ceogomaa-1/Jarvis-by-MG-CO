'use client'

import { useState, useEffect, useRef } from 'react'
import { useRouter } from 'next/navigation'
import ReactMarkdown from 'react-markdown'
import { supabase } from '../lib/supabase'
import { getJarvisMode, setJarvisMode } from '../lib/userPreferences'
import ModeToggle from '../components/shared/ModeToggle'
import SignOutDrawer from '../components/shared/SignOutDrawer'
import TimezoneStep from '../components/onboarding/TimezoneStep'
import { JarvisVoice } from '../lib/jarvisVoice'

const BACKEND = 'https://jarvis-backend-4oz6.onrender.com'
const DEV_MODE = true

const OPENING_MESSAGE = {
  id: 0,
  role: 'assistant',
  content:
    "I'm Jarvis. Before I'm actually useful to you, I need to know you — not through a form, through a conversation. What's the one thing taking up the most space in your head right now?",
}

// ─── Orb helpers ──────────────────────────────────────────────────────────────

function hexToRgb(hex) {
  const h = hex.replace('#', '')
  const n = parseInt(h.length === 3 ? h.split('').map(c => c + c).join('') : h, 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}

function drawAurora(ctx, cx, cy, r, t, amp, rgb, state, env) {
  const [ar, ag, ab] = rgb
  const ts = t * 0.45
  const sphere = ctx.createRadialGradient(cx - r * 0.3, cy - r * 0.4, r * 0.05, cx, cy, r * 1.2)
  sphere.addColorStop(0, `rgba(${Math.min(ar + 40, 255)},${Math.min(ag + 30, 255)},${Math.min(ab + 30, 255)},0.95)`)
  sphere.addColorStop(0.4, `rgba(${ar},${ag},${ab},0.55)`)
  sphere.addColorStop(0.8, `rgba(${Math.max(ar - 80, 0)},${Math.max(ag - 80, 0)},${Math.max(ab - 60, 0)},0.4)`)
  sphere.addColorStop(1, `rgba(${ar},${ag},${ab},0)`)
  ctx.fillStyle = sphere
  ctx.beginPath()
  ctx.arc(cx, cy, r * 1.15, 0, Math.PI * 2)
  ctx.fill()

  ctx.save()
  ctx.globalCompositeOperation = 'screen'
  for (let i = 0; i < 5; i++) {
    const phase = ts * (0.45 + i * 0.13) + i * 1.3
    const orbitR = r * (0.35 + 0.12 * Math.sin(ts * 0.6 + i))
    const x = cx + Math.cos(phase) * orbitR
    const y = cy + Math.sin(phase * 1.1) * orbitR * 0.85
    const br = r * (0.45 + 0.18 * Math.sin(ts * 1.2 + i) + amp * 0.25)
    const hueShift = i * 18 - 18
    const r2 = Math.max(0, Math.min(255, ar + hueShift))
    const g2 = Math.max(0, Math.min(255, ag + hueShift * 0.3))
    const b2 = Math.max(0, Math.min(255, ab - hueShift * 0.5))
    const g = ctx.createRadialGradient(x, y, 0, x, y, br)
    g.addColorStop(0, `rgba(${r2},${g2},${b2},${0.55 + amp * 0.2})`)
    g.addColorStop(1, `rgba(${r2},${g2},${b2},0)`)
    ctx.fillStyle = g
    ctx.beginPath()
    ctx.arc(x, y, br, 0, Math.PI * 2)
    ctx.fill()
  }
  ctx.restore()

  const core = ctx.createRadialGradient(cx, cy, 0, cx, cy, r * 0.55)
  core.addColorStop(0, `rgba(255,240,225,${0.45 + amp * 0.3})`)
  core.addColorStop(0.5, `rgba(${ar},${ag},${ab},${0.18 + amp * 0.15})`)
  core.addColorStop(1, 'rgba(0,0,0,0)')
  ctx.fillStyle = core
  ctx.beginPath()
  ctx.arc(cx, cy, r * 0.55, 0, Math.PI * 2)
  ctx.fill()

  ctx.beginPath()
  ctx.arc(cx, cy, r * 1.02, 0, Math.PI * 2)
  ctx.strokeStyle = `rgba(${ar},${ag},${ab},${0.35 + amp * 0.25})`
  ctx.lineWidth = 1.2
  ctx.stroke()

  if (state === 'speaking' && env > 0) {
    ctx.beginPath()
    const steps = 96
    for (let i = 0; i <= steps; i++) {
      const a = (i / steps) * Math.PI * 2
      const wobble =
        Math.sin(a * 4 + ts * 1.6) * 0.04 +
        Math.sin(a * 7 - ts * 2.4) * 0.025 +
        Math.sin(a * 11 + ts * 1.1) * 0.018
      const rr = r * (1.08 + wobble * (0.6 + amp * 1.4) * env)
      const x = cx + Math.cos(a) * rr
      const y = cy + Math.sin(a) * rr
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y)
    }
    ctx.strokeStyle = `rgba(255,230,210,${(0.5 + amp * 0.3) * env})`
    ctx.lineWidth = 1.3
    ctx.stroke()
  }
}

function drawPulse(ctx, cx, cy, r, t, amp, rgb) {
  const [ar, ag, ab] = rgb
  const ts = t * 0.5
  const sphere = ctx.createRadialGradient(cx, cy, 0, cx, cy, r)
  sphere.addColorStop(0, `rgba(${ar},${ag},${ab},${0.55 + amp * 0.2})`)
  sphere.addColorStop(0.6, `rgba(${ar},${ag},${ab},0.18)`)
  sphere.addColorStop(1, `rgba(${ar},${ag},${ab},0)`)
  ctx.fillStyle = sphere
  ctx.beginPath()
  ctx.arc(cx, cy, r, 0, Math.PI * 2)
  ctx.fill()

  for (let i = 0; i < 8; i++) {
    const phase = ((ts * 0.18 + i / 8) % 1)
    const rr = r * (0.5 + phase * 1.3)
    const fade = 1 - phase
    const alpha = (fade * fade * (3 - 2 * fade)) * 0.4
    ctx.beginPath()
    ctx.arc(cx, cy, rr, 0, Math.PI * 2)
    ctx.strokeStyle = `rgba(${ar},${ag},${ab},${alpha})`
    ctx.lineWidth = 1
    ctx.stroke()
  }

  const core = ctx.createRadialGradient(cx, cy, 0, cx, cy, r * 0.4)
  core.addColorStop(0, `rgba(255,240,225,${0.7 + amp * 0.2})`)
  core.addColorStop(1, 'rgba(0,0,0,0)')
  ctx.fillStyle = core
  ctx.beginPath()
  ctx.arc(cx, cy, r * 0.4, 0, Math.PI * 2)
  ctx.fill()
}

function drawParticles(ctx, cx, cy, r, t, amp, rgb) {
  const [ar, ag, ab] = rgb
  const ts = t * 0.5
  const sphere = ctx.createRadialGradient(cx, cy, 0, cx, cy, r * 1.1)
  sphere.addColorStop(0, `rgba(${ar},${ag},${ab},0.25)`)
  sphere.addColorStop(1, `rgba(${ar},${ag},${ab},0)`)
  ctx.fillStyle = sphere
  ctx.beginPath()
  ctx.arc(cx, cy, r * 1.1, 0, Math.PI * 2)
  ctx.fill()

  ctx.save()
  ctx.globalCompositeOperation = 'screen'
  for (let i = 0; i < 130; i++) {
    const seed = i * 12.9898
    const lat = Math.acos(2 * ((Math.sin(seed) * 43758.5453) % 1 + 1) % 1 - 1)
    const lon = i * 2.39996 + ts * (0.18 + amp * 0.35)
    const x3 = Math.sin(lat) * Math.cos(lon)
    const y3 = Math.cos(lat)
    const z3 = Math.sin(lat) * Math.sin(lon)
    const depth = (z3 + 1) / 2
    const px = cx + x3 * r
    const py = cy + y3 * r
    const rad = 0.5 + depth * 1.6 + amp * 0.6
    ctx.fillStyle = `rgba(${ar},${ag},${ab},${0.15 + depth * 0.7})`
    ctx.beginPath()
    ctx.arc(px, py, rad, 0, Math.PI * 2)
    ctx.fill()
  }
  ctx.restore()

  const core = ctx.createRadialGradient(cx, cy, 0, cx, cy, r * 0.3)
  core.addColorStop(0, `rgba(255,235,215,${0.4 + amp * 0.3})`)
  core.addColorStop(1, 'rgba(0,0,0,0)')
  ctx.fillStyle = core
  ctx.beginPath()
  ctx.arc(cx, cy, r * 0.3, 0, Math.PI * 2)
  ctx.fill()
}

// ─── Orb component ────────────────────────────────────────────────────────────

function Orb({ state = 'idle', orbStyle = 'aurora', accent = '#ff9072', size = 340 }) {
  const canvasRef = useRef(null)
  const stateRef = useRef(state)
  const styleRef = useRef(orbStyle)
  const accentRef = useRef(accent)

  useEffect(() => { stateRef.current = state }, [state])
  useEffect(() => { styleRef.current = orbStyle }, [orbStyle])
  useEffect(() => { accentRef.current = accent }, [accent])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const dpr = window.devicePixelRatio || 1
    canvas.width = size * dpr
    canvas.height = size * dpr
    const ctx = canvas.getContext('2d')
    ctx.scale(dpr, dpr)

    let raf
    const t0 = performance.now()
    let speakAmp = 0
    let stateEnv = 0
    let renderState = stateRef.current
    let listenPulse = 0
    let ripples = []

    const easeInOut = (x) => x * x * (3 - 2 * x)

    const render = () => {
      const t = (performance.now() - t0) / 1000
      const target = stateRef.current
      const sty = styleRef.current
      const acc = accentRef.current
      const [ar, ag, ab] = hexToRgb(acc)

      if (target !== 'idle') {
        if (renderState === 'idle' || renderState !== target) renderState = target
      } else {
        if (stateEnv < 0.02) renderState = 'idle'
      }

      const isActive = target !== 'idle'
      const targetEnv = isActive ? 1 : 0
      const k = isActive ? 0.028 : 0.011
      stateEnv += (targetEnv - stateEnv) * k
      if (Math.abs(stateEnv - targetEnv) < 0.003) stateEnv = targetEnv
      const env = easeInOut(Math.max(0, Math.min(1, stateEnv)))

      const baseIdle   = 0.18 + 0.04 * Math.sin(t * 0.6)
      const baseListen = 0.32 + 0.04 * Math.sin(t * 0.9)
      const baseSpeak  = 0.42 + 0.22 * Math.abs(Math.sin(t * 2.1)) + 0.1 * Math.sin(t * 4.3)
      const baseThink  = 0.22 + 0.06 * Math.sin(t * 1.1)

      const stateAmp =
        renderState === 'speaking'  ? baseSpeak  :
        renderState === 'thinking'  ? baseThink  :
        renderState === 'listening' ? baseListen :
        baseIdle

      const targetAmp = baseIdle * (1 - env) + stateAmp * env
      speakAmp += (targetAmp - speakAmp) * 0.035

      if (renderState === 'listening' && target === 'listening' && env > 0.5) {
        listenPulse += 1
        if (listenPulse % 90 === 0) ripples.push({ r: 0, life: 1 })
      }
      ripples = ripples.filter(rp => rp.life > 0)
      ripples.forEach(rp => { rp.r += 0.55; rp.life -= 0.005 })

      const s = renderState
      ctx.clearRect(0, 0, size, size)

      const cx = size / 2, cy = size / 2
      const baseR = size * 0.22
      const r = baseR * (1 + speakAmp * 0.22)

      const glow = ctx.createRadialGradient(cx, cy, r * 0.4, cx, cy, size * 0.5)
      glow.addColorStop(0, `rgba(${ar},${ag},${ab},${0.22 + speakAmp * 0.18})`)
      glow.addColorStop(0.35, `rgba(${ar},${ag},${ab},${0.08 + speakAmp * 0.08})`)
      glow.addColorStop(1, 'rgba(0,0,0,0)')
      ctx.fillStyle = glow
      ctx.fillRect(0, 0, size, size)

      if (ripples.length) {
        ripples.forEach(rp => {
          const lifeEased = easeInOut(rp.life)
          ctx.beginPath()
          ctx.arc(cx, cy, baseR + rp.r, 0, Math.PI * 2)
          ctx.strokeStyle = `rgba(${ar},${ag},${ab},${lifeEased * 0.35})`
          ctx.lineWidth = 1
          ctx.stroke()
        })
      }

      if (sty === 'aurora') drawAurora(ctx, cx, cy, r, t, speakAmp, [ar, ag, ab], s, env)
      else if (sty === 'pulse') drawPulse(ctx, cx, cy, r, t, speakAmp, [ar, ag, ab], s, env)
      else if (sty === 'particles') drawParticles(ctx, cx, cy, r, t, speakAmp, [ar, ag, ab], s, env)

      if (s === 'thinking' || (renderState === 'thinking' && env > 0)) {
        const thinkAlpha = s === 'thinking' ? env : 0
        for (let i = 0; i < 3; i++) {
          ctx.beginPath()
          const rr = r * (1.25 + i * 0.18)
          const start = t * (0.35 + i * 0.12) + i * 1.7
          ctx.arc(cx, cy, rr, start, start + Math.PI * (0.4 + i * 0.1))
          ctx.strokeStyle = `rgba(${ar},${ag},${ab},${(0.45 - i * 0.1) * thinkAlpha})`
          ctx.lineWidth = 1.4
          ctx.stroke()
        }
      }

      raf = requestAnimationFrame(render)
    }
    render()
    return () => cancelAnimationFrame(raf)
  }, [size])

  return (
    <canvas
      ref={canvasRef}
      style={{ width: size, height: size, display: 'block', filter: 'saturate(1.05)' }}
    />
  )
}

// ─── UI components ────────────────────────────────────────────────────────────

function Wordmark() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2, userSelect: 'none' }}>
      <div className="wordmark-main" style={{ fontFamily: 'var(--display)', fontSize: 22, letterSpacing: '0.55em', paddingLeft: '0.55em', color: 'var(--ink)', fontWeight: 400 }}>
        JARVIS
      </div>
      <div className="wordmark-sub" style={{ fontFamily: 'var(--sans)', fontSize: 9, letterSpacing: '0.4em', paddingLeft: '0.4em', color: 'var(--ink-mute)', textTransform: 'uppercase', fontWeight: 400 }}>
        by MG &amp; Co
      </div>
    </div>
  )
}

function StatusPill({ state }) {
  const label =
    state === 'listening' ? 'Listening' :
    state === 'speaking'  ? 'Speaking'  :
    state === 'thinking'  ? 'Thinking'  :
    'Present'
  return (
    <div style={{
      display: 'inline-flex', alignItems: 'center', gap: 10,
      padding: '6px 16px', borderRadius: 999,
      background: 'rgba(243,234,217,0.04)', border: '1px solid var(--line)',
      fontFamily: 'var(--sans)', fontSize: 10.5, letterSpacing: '0.32em',
      textTransform: 'uppercase', color: 'var(--ink-soft)', fontWeight: 400,
    }}>
      <span style={{
        display: 'inline-block', width: 6, height: 6, borderRadius: 999,
        background: state === 'idle' ? 'var(--ink-mute)' : 'var(--accent)',
        boxShadow: state !== 'idle' ? '0 0 12px var(--accent)' : 'none',
        animation: state !== 'idle' ? 'inkPulse 1.4s ease-in-out infinite' : 'none',
      }} />
      {label}
    </div>
  )
}

function PermissionChip({ icon, label, granted }) {
  return (
    <div style={{
      display: 'inline-flex', alignItems: 'center', gap: 8,
      padding: '6px 12px', borderRadius: 999,
      background: granted ? 'rgba(255,144,114,0.08)' : 'rgba(243,234,217,0.03)',
      border: `1px solid ${granted ? 'rgba(255,144,114,0.25)' : 'var(--line)'}`,
      fontFamily: 'var(--sans)', fontSize: 10, letterSpacing: '0.18em',
      textTransform: 'uppercase', color: granted ? 'var(--accent)' : 'var(--ink-mute)', fontWeight: 400,
    }}>
      <span style={{ fontSize: 11 }}>{icon}</span>
      {label}
    </div>
  )
}

function ProactiveBanner({ hint, onDismiss, onAct }) {
  if (!hint) return null
  return (
    <div style={{
      position: 'absolute', top: 80, right: 32, maxWidth: 320,
      padding: '14px 16px 14px 18px',
      background: 'rgba(15,12,10,0.85)', border: '1px solid rgba(255,144,114,0.22)',
      borderLeft: '2px solid var(--accent)', borderRadius: 8,
      backdropFilter: 'blur(14px)', animation: 'fadeUp 500ms ease both',
      fontFamily: 'var(--sans)', zIndex: 10,
    }}>
      <div style={{ fontSize: 9, letterSpacing: '0.35em', textTransform: 'uppercase', color: 'var(--accent)', marginBottom: 8, fontWeight: 500 }}>
        Proactive · just now
      </div>
      <div style={{ fontSize: 14, color: 'var(--ink)', lineHeight: 1.5, fontWeight: 300, marginBottom: 12 }}>
        {hint}
      </div>
      <div style={{ display: 'flex', gap: 14 }}>
        <button onClick={onAct} style={{ background: 'transparent', border: 0, padding: 0, cursor: 'pointer', fontFamily: 'var(--sans)', fontSize: 11, letterSpacing: '0.22em', textTransform: 'uppercase', color: 'var(--accent)', fontWeight: 500 }}>
          Handle it
        </button>
        <button onClick={onDismiss} style={{ background: 'transparent', border: 0, padding: 0, cursor: 'pointer', fontFamily: 'var(--sans)', fontSize: 11, letterSpacing: '0.22em', textTransform: 'uppercase', color: 'var(--ink-mute)', fontWeight: 500 }}>
          Dismiss
        </button>
      </div>
    </div>
  )
}

// ─── Knowledge panel ──────────────────────────────────────────────────────────

function KnowledgePanel({ userId, onClose }) {
  const [model, setModel] = useState(null)

  useEffect(() => {
    fetch(`${BACKEND}/api/user/model/${userId}`)
      .then(r => r.json())
      .then(setModel)
      .catch(() => setModel({}))
  }, [userId])

  const safeItemText = (item) => {
    if (typeof item === 'string') {
      try {
        const parsed = JSON.parse(item)
        if (parsed && typeof parsed === 'object') {
          const parts = [parsed.name, parsed.label, parsed.details].filter(Boolean)
          return parts.length > 0 ? parts.join(' — ') : JSON.stringify(parsed)
        }
      } catch (_) {}
      return item
    }
    if (typeof item === 'object' && item !== null) {
      const parts = [item.name, item.label, item.details].filter(Boolean)
      return parts.length > 0 ? parts.join(' — ') : JSON.stringify(item)
    }
    return String(item)
  }

  const Section = ({ title, items }) => {
    if (!items || items.length === 0) return null
    const seen = new Set()
    const safeItems = items.map(safeItemText).filter(t => {
      if (seen.has(t)) return false
      seen.add(t)
      return true
    })
    return (
      <div style={{ marginBottom: '1.25rem' }}>
        <p style={{ fontFamily: 'var(--sans)', color: 'var(--accent)', fontSize: '0.6rem', letterSpacing: '0.15em', textTransform: 'uppercase', opacity: 0.6, margin: '0 0 0.5rem' }}>{title}</p>
        {safeItems.map((item, i) => (
          <p key={i} style={{ fontFamily: 'var(--sans)', color: 'var(--ink)', fontSize: '0.8rem', lineHeight: 1.6, margin: '0.2rem 0', opacity: 0.85 }}>
            <span style={{ color: 'var(--accent)', marginRight: '0.4rem' }}>●</span>{item}
          </p>
        ))}
      </div>
    )
  }

  const id = model?.identity || {}
  const focus = model?.current_focus || {}
  const relationship = model?.jarvis_relationship || {}
  const work = model?.work_context || {}

  const identityItems = [
    id.name && typeof id.name === 'string' && `Name: ${id.name}`,
    id.role && typeof id.role === 'string' && `Role: ${id.role}`,
    id.company && typeof id.company === 'string' && `Company: ${id.company}`,
    id.location && typeof id.location === 'string' && `Based in: ${id.location}`,
  ].filter(Boolean)

  const trustLabel = relationship.trust_level
    ? `${relationship.trust_level} (${relationship.interaction_count || 0} interactions)`
    : 'new (0 interactions)'

  return (
    <>
      <div className="fixed inset-0 z-40" style={{ backgroundColor: 'rgba(0,0,0,0.4)' }} onClick={onClose} />
      <div className="panel-slide fixed top-0 right-0 h-full z-50 overflow-y-auto" style={{
        width: '320px', backgroundColor: '#0f0e0c',
        borderLeft: '1px solid var(--line)', padding: '1.5rem',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
          <p style={{ fontFamily: 'var(--sans)', color: 'var(--accent)', fontSize: '0.65rem', letterSpacing: '0.2em', textTransform: 'uppercase', margin: 0 }}>
            Jarvis Knows
          </p>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'var(--ink-mute)', cursor: 'pointer', fontSize: '1.1rem', lineHeight: 1 }}>
            ×
          </button>
        </div>
        {!model ? (
          <p style={{ fontFamily: 'var(--sans)', color: 'var(--ink-mute)', fontSize: '0.8rem' }}>Loading...</p>
        ) : (
          <>
            <Section title="Identity" items={identityItems} />
            <Section title="Current Focus" items={focus.top_goals} />
            <Section title="Active Projects" items={focus.active_projects} />
            <Section title="Biggest Challenges" items={focus.biggest_challenges} />
            <Section title="Key People" items={work.key_people} />
            <Section title="Never Forget" items={relationship.things_jarvis_should_never_forget} />
            {trustLabel && (
              <div style={{ marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid var(--line)' }}>
                <p style={{ fontFamily: 'var(--sans)', color: 'var(--ink-mute)', fontSize: '0.7rem', letterSpacing: '0.1em' }}>TRUST LEVEL</p>
                <p style={{ fontFamily: 'var(--sans)', color: 'var(--ink)', fontSize: '0.8rem', opacity: 0.7 }}>{trustLabel}</p>
              </div>
            )}
          </>
        )}
      </div>
    </>
  )
}

// ─── Conversation ─────────────────────────────────────────────────────────────

function BlinkCaret() {
  return (
    <span style={{
      display: 'inline-block', width: 8, height: 18, marginLeft: 4,
      background: 'var(--accent)', verticalAlign: -2,
      animation: 'jarvisBlink 1s steps(1) infinite', borderRadius: 1,
    }} />
  )
}

function formatFileSize(bytes) {
  if (!bytes) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function AttachmentCard({ attachment }) {
  const isPdf = attachment.type === 'application/pdf' || attachment.name?.toLowerCase().endsWith('.pdf')
  const isImage = attachment.type?.startsWith('image/')
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 12,
      background: 'rgba(255,255,255,0.05)',
      border: '1px solid rgba(255,255,255,0.1)',
      borderRadius: 12, padding: '10px 14px', marginBottom: 6,
    }}>
      <div style={{
        width: 36, height: 36, borderRadius: 8,
        background: 'rgba(255,255,255,0.08)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
      }}>
        <span style={{
          fontSize: 10, fontWeight: 700, fontFamily: 'system-ui, sans-serif',
          color: isPdf ? '#f87171' : isImage ? '#60a5fa' : 'rgba(243,234,217,0.55)',
        }}>
          {isPdf ? 'PDF' : isImage ? 'IMG' : 'DOC'}
        </span>
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          color: 'rgba(243,234,217,0.9)', fontSize: 13,
          fontFamily: 'system-ui, sans-serif',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
          {attachment.name}
        </div>
        {attachment.size > 0 && (
          <div style={{ color: 'rgba(243,234,217,0.4)', fontSize: 11, fontFamily: 'system-ui, sans-serif' }}>
            {formatFileSize(attachment.size)}
          </div>
        )}
      </div>
    </div>
  )
}

function Message({ msg, isLatest, onRetry }) {
  // Artifact role — must be checked first; content is {html, title} object
  if (msg.role === 'artifact') {
    const htmlContent = typeof msg.content === 'object' ? msg.content?.html : null
    const titleContent = typeof msg.content === 'object' ? msg.content?.title : (msg.content || '')

    if (msg.loading || !htmlContent) {
      return (
        <div style={{
          margin: '16px 0', border: '1px solid rgba(243,234,217,0.1)',
          borderRadius: 12, height: 200,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: 'var(--ink-soft)', fontFamily: 'var(--sans)',
          fontSize: '0.75rem', letterSpacing: '0.1em',
        }}>
          Jarvis is creating...
        </div>
      )
    }
    return (
      <div style={{ margin: '16px 0', width: '100%' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
          <span style={{ fontFamily: 'var(--sans)', fontSize: '0.6rem', letterSpacing: '0.15em', textTransform: 'uppercase', color: 'var(--accent)' }}>
            Jarvis created
          </span>
          <button
            onClick={() => {
              const blob = new Blob([htmlContent], { type: 'text/html' })
              const url = URL.createObjectURL(blob)
              const a = document.createElement('a')
              a.href = url
              a.download = `${(titleContent || 'jarvis-creation').slice(0, 30)}.html`
              a.click()
              URL.revokeObjectURL(url)
            }}
            style={{
              background: 'none', border: '1px solid rgba(243,234,217,0.15)',
              borderRadius: 4, padding: '4px 10px', color: 'var(--ink-soft)',
              cursor: 'pointer', fontFamily: 'var(--sans)',
              fontSize: '0.6rem', letterSpacing: '0.1em', textTransform: 'uppercase',
            }}
          >
            Download
          </button>
        </div>
        <div style={{ border: '1px solid rgba(243,234,217,0.1)', borderRadius: 12, overflow: 'hidden', height: 500, width: '100%' }}>
          <iframe
            srcDoc={htmlContent}
            style={{ width: '100%', height: '100%', border: 'none', background: '#0a0a0a' }}
            sandbox="allow-scripts allow-same-origin"
            title={titleContent}
          />
        </div>
      </div>
    )
  }

  // Safe string coercion for all other roles — prevents React error #31
  const textContent = typeof msg.content === 'string' ? msg.content : JSON.stringify(msg.content)

  if (msg.role === 'user') {
    const dimmed = msg.pending || msg.failed || msg.orphaned
    return (
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 14, opacity: dimmed ? 0.55 : (isLatest ? 1 : 0.78), transition: 'opacity 600ms ease' }}>
        <div style={{ maxWidth: '72%', display: 'flex', flexDirection: 'column', alignItems: 'flex-end' }}>
          {msg.attachment && <AttachmentCard attachment={msg.attachment} />}
          {msg.imagePreview && (
            <img
              src={msg.imagePreview}
              alt="Pasted"
              style={{ maxHeight: 220, maxWidth: 280, borderRadius: 12, marginBottom: 6, objectFit: 'cover', border: '1px solid rgba(255,255,255,0.1)' }}
            />
          )}
          {textContent && (
            <div style={{
              padding: '12px 18px',
              borderRadius: '20px 20px 4px 20px',
              background: 'var(--user-bubble)',
              border: `1px solid ${msg.failed || msg.orphaned ? 'rgba(239,68,68,0.35)' : 'rgba(255,144,114,0.18)'}`,
              color: 'rgba(243,234,217,0.92)',
              fontSize: 15.5, lineHeight: 1.5, fontWeight: 300, letterSpacing: 0.1,
              backdropFilter: 'blur(8px)',
              fontFamily: 'var(--sans)',
            }}>
              {textContent}
            </div>
          )}
          {msg.pending && (
            <div style={{ fontSize: 11, color: 'rgba(243,234,217,0.3)', marginTop: 5, fontFamily: 'system-ui, sans-serif' }}>
              Sending...
            </div>
          )}
          {(msg.failed || msg.orphaned) && onRetry && (
            <button
              onClick={() => onRetry(msg)}
              style={{
                marginTop: 5, background: 'none', border: 'none', padding: 0, cursor: 'pointer',
                fontFamily: 'system-ui, sans-serif', fontSize: 11, color: 'rgba(239,68,68,0.75)',
              }}
            >
              {msg.failed ? 'Failed — tap to retry' : 'No response — tap to retry'}
            </button>
          )}
        </div>
      </div>
    )
  }

  return (
    <div style={{ marginBottom: 22, maxWidth: '78%', opacity: isLatest ? 1 : 0.72, transition: 'opacity 600ms ease' }}>
      {(msg.proactive || msg.fromVoice) && (
        <div style={{ fontFamily: 'var(--sans)', fontSize: 9, letterSpacing: '0.35em', textTransform: 'uppercase', color: 'var(--accent)', marginBottom: 8, fontWeight: 500, opacity: 0.7 }}>
          {msg.proactive ? 'Proactive · just now' : 'Voice'}
        </div>
      )}
      <div className="prose" style={{ fontFamily: 'var(--serif)', fontSize: 22, lineHeight: 1.35, fontWeight: 400, color: 'var(--ink)', letterSpacing: 0.2 }}>
        <ReactMarkdown>{textContent}</ReactMarkdown>
        {msg.streaming && <BlinkCaret />}
      </div>
    </div>
  )
}

function ThinkingIndicator() {
  return (
    <div style={{ marginBottom: 22, maxWidth: '78%' }}>
      <div style={{ display: 'flex', gap: 6, alignItems: 'center', paddingTop: 4 }}>
        <span className="thinking-dot" style={{ display: 'inline-block', width: 7, height: 7, borderRadius: '50%', background: 'var(--accent)' }} />
        <span className="thinking-dot" style={{ display: 'inline-block', width: 7, height: 7, borderRadius: '50%', background: 'var(--accent)' }} />
        <span className="thinking-dot" style={{ display: 'inline-block', width: 7, height: 7, borderRadius: '50%', background: 'var(--accent)' }} />
      </div>
    </div>
  )
}

function Toast({ message, onTap, onClose, duration = 6000 }) {
  useEffect(() => {
    const t = setTimeout(onClose, duration)
    return () => clearTimeout(t)
  }, [onClose, duration])
  return (
    <div
      onClick={onTap ?? undefined}
      style={{
        position: 'fixed', bottom: 100, left: '50%', transform: 'translateX(-50%)',
        padding: '12px 20px', borderRadius: 16, zIndex: 9999,
        background: 'rgba(30,8,8,0.92)', border: '1px solid rgba(239,68,68,0.4)',
        color: '#fca5a5', fontFamily: 'system-ui, sans-serif', fontSize: 13,
        cursor: onTap ? 'pointer' : 'default', whiteSpace: 'nowrap',
        backdropFilter: 'blur(12px)',
      }}
    >
      {message}
    </div>
  )
}

function Conversation({ messages, loading, onRetry }) {
  const scrollRef = useRef(null)

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
    }
  }, [messages, loading])

  return (
    <div ref={scrollRef} style={{
      flex: 1, overflowY: 'auto',
      padding: '24px 40px 32px',
      maskImage: 'linear-gradient(to bottom, transparent 0, #000 60px, #000 100%)',
      WebkitMaskImage: 'linear-gradient(to bottom, transparent 0, #000 60px, #000 100%)',
    }}>
      <div style={{ maxWidth: 720, margin: '0 auto' }}>
        {messages.map((m, i) => (
          <div key={m.id ?? i} className="msg-enter">
            <Message msg={m} isLatest={i === messages.length - 1 && !loading} onRetry={onRetry} />
          </div>
        ))}
        {loading && <ThinkingIndicator />}
      </div>
    </div>
  )
}

// ─── Input bar ────────────────────────────────────────────────────────────────

function InputBar({ orbState, input, setInput, onSend, onMicClick, voiceMode, voiceConnecting, loading, disabled, fileInputRef, uploadingFile, onFileSelect, pendingFiles, onRemoveFile, mobile, pastedImage, onPastedImageChange }) {
  const isListening = orbState === 'listening'
  const textareaRef = useRef(null)
  const hasContent = input.trim() || !!pastedImage || (pendingFiles || []).some(f => f.status === 'ready')

  // Reset height when message is sent (input cleared externally)
  useEffect(() => {
    if (input === '' && textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.overflowY = 'hidden'
    }
  }, [input])

  const triggerSend = () => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.overflowY = 'hidden'
    }
    onSend()
  }

  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      triggerSend()
    }
    // Shift+Enter inserts newline naturally via textarea
  }

  // Paste handler — capture images from clipboard
  useEffect(() => {
    const handlePaste = (e) => {
      const items = e.clipboardData?.items
      if (!items) return
      for (const item of items) {
        if (item.type.startsWith('image/')) {
          e.preventDefault()
          const file = item.getAsFile()
          if (!file) continue
          const reader = new FileReader()
          reader.onload = (ev) => {
            onPastedImageChange({ preview: ev.target.result, type: file.type, name: `pasted-${Date.now()}.png` })
          }
          reader.readAsDataURL(file)
          break
        }
      }
    }
    window.addEventListener('paste', handlePaste)
    return () => window.removeEventListener('paste', handlePaste)
  }, [onPastedImageChange])

  const micBg = voiceConnecting
    ? 'rgba(255,144,114,0.3)'
    : voiceMode
    ? 'var(--accent)'
    : 'rgba(243,234,217,0.07)'

  const micColor = voiceMode || voiceConnecting ? '#1a0e08' : 'var(--ink-soft)'
  const micShadow = voiceMode ? '0 0 24px rgba(255,144,114,0.6)' : 'none'

  let placeholder = 'Say something to Jarvis'
  if (voiceMode) placeholder = isListening ? 'Listening...' : 'Voice active — tap mic to stop'

  return (
    <div style={{ padding: mobile ? '12px 16px 20px' : '20px 40px 32px', display: 'flex', justifyContent: 'center', flexDirection: 'column', alignItems: 'center', gap: 8 }}>
      {(pendingFiles || []).length > 0 && (
        <div style={{
          width: '100%', maxWidth: 720,
          display: 'flex', gap: 8, overflowX: 'auto', paddingBottom: 2,
          scrollbarWidth: 'none',
        }}>
          {(pendingFiles || []).map(f => (
            <div key={f.id} style={{ position: 'relative', flexShrink: 0 }}>
              {f.type?.startsWith('image/') && f.preview ? (
                <img
                  src={f.preview}
                  alt={f.name}
                  style={{ width: 60, height: 60, objectFit: 'cover', borderRadius: 8, border: '1px solid var(--accent)', display: 'block' }}
                />
              ) : (
                <div style={{
                  width: 110, height: 60, borderRadius: 8,
                  border: `1px solid ${f.status === 'error' ? '#ef4444' : 'var(--accent)'}`,
                  background: 'rgba(200,75,49,0.08)',
                  display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                  padding: '4px 8px', gap: 2,
                }}>
                  {f.status === 'uploading' && (
                    <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--accent)', animation: 'inkPulse 0.8s ease-in-out infinite', display: 'inline-block' }} />
                  )}
                  <span style={{
                    color: 'var(--ink-soft)', fontSize: 9, fontFamily: 'var(--sans)',
                    textAlign: 'center', overflow: 'hidden', textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap', width: '100%',
                  }}>
                    {f.name}
                  </span>
                  {f.status === 'ready' && <span style={{ color: 'var(--accent)', fontSize: 9, fontFamily: 'var(--sans)' }}>Ready</span>}
                  {f.status === 'error' && (
                    <span title={f.errorMsg || 'Upload failed'} style={{ color: '#ef4444', fontSize: 9, fontFamily: 'var(--sans)', cursor: 'help', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', width: '100%', textAlign: 'center' }}>
                      Failed{f.errorMsg ? ` — ${f.errorMsg}` : ''}
                    </span>
                  )}
                </div>
              )}
              <button
                onClick={() => onRemoveFile?.(f.id)}
                style={{
                  position: 'absolute', top: -6, right: -6,
                  width: 18, height: 18, borderRadius: '50%',
                  background: '#1a0e08', border: '1px solid rgba(255,255,255,0.2)',
                  color: 'rgba(243,234,217,0.8)', cursor: 'pointer',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 12, lineHeight: 1, padding: 0,
                }}
                aria-label="remove attachment"
              >×</button>
            </div>
          ))}
        </div>
      )}
      {pastedImage && (
        <div style={{ width: '100%', maxWidth: 720, display: 'flex', alignItems: 'flex-start' }}>
          <div style={{ position: 'relative', display: 'inline-block' }}>
            <img
              src={pastedImage.preview}
              alt="Paste preview"
              style={{ maxHeight: 100, maxWidth: 160, borderRadius: 10, objectFit: 'cover', border: '1px solid rgba(255,255,255,0.15)', display: 'block' }}
            />
            <button
              onClick={() => onPastedImageChange(null)}
              style={{
                position: 'absolute', top: -7, right: -7,
                width: 20, height: 20, borderRadius: '50%',
                background: '#1a0e08', border: '1px solid rgba(255,255,255,0.25)',
                color: 'rgba(243,234,217,0.8)', cursor: 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 13, lineHeight: 1, padding: 0,
              }}
              aria-label="remove image"
            >
              ×
            </button>
          </div>
        </div>
      )}
      <div style={{
        width: '100%', maxWidth: 720,
        display: 'flex', alignItems: 'flex-end', gap: 14,
        padding: '14px 18px',
        background: voiceMode ? 'rgba(255,144,114,0.06)' : 'rgba(243,234,217,0.035)',
        border: `1px solid ${voiceMode ? 'rgba(255,144,114,0.45)' : 'var(--line)'}`,
        borderRadius: 999, backdropFilter: 'blur(10px)',
        transition: 'border-color 300ms ease, background 300ms ease',
      }}>
        <button
          onClick={onMicClick}
          disabled={voiceConnecting}
          aria-label={voiceMode ? 'stop voice' : 'start voice'}
          style={{
            width: 36, height: 36, borderRadius: 999, flexShrink: 0,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: micBg, border: '1px solid rgba(243,234,217,0.12)',
            color: micColor, cursor: voiceConnecting ? 'default' : 'pointer',
            transition: 'all 250ms ease', boxShadow: micShadow,
          }}
        >
          {voiceConnecting ? (
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--accent)', animation: 'inkPulse 0.8s ease-in-out infinite', display: 'inline-block' }} />
          ) : voiceMode ? (
            <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
              <rect x="4" y="4" width="16" height="16" rx="2" />
            </svg>
          ) : (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="9" y="3" width="6" height="12" rx="3" />
              <path d="M5 11a7 7 0 0 0 14 0" />
              <line x1="12" y1="18" x2="12" y2="22" />
            </svg>
          )}
        </button>
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={uploadingFile}
          aria-label="attach file"
          style={{
            width: 36, height: 36, borderRadius: 999, flexShrink: 0,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: 'rgba(243,234,217,0.07)', border: '1px solid rgba(243,234,217,0.12)',
            color: uploadingFile ? 'var(--accent)' : 'var(--ink-soft)',
            cursor: uploadingFile ? 'default' : 'pointer',
          }}
        >
          {uploadingFile ? (
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--accent)', animation: 'inkPulse 0.8s ease-in-out infinite', display: 'inline-block' }} />
          ) : (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48"/>
            </svg>
          )}
        </button>
        <input
          ref={fileInputRef}
          type="file"
          style={{ display: 'none' }}
          accept="image/*,application/pdf,.docx,.doc,.txt,.md,.csv,.xlsx"
          multiple
          onChange={onFileSelect}
        />
        <textarea
          ref={textareaRef}
          value={input}
          onChange={e => {
            setInput(e.target.value)
            const ta = e.target
            ta.style.height = 'auto'
            ta.style.height = Math.min(ta.scrollHeight, 144) + 'px'
            ta.style.overflowY = ta.scrollHeight > 144 ? 'auto' : 'hidden'
          }}
          onKeyDown={handleKey}
          placeholder={placeholder}
          disabled={disabled || loading}
          rows={1}
          style={{
            flex: 1, background: 'transparent', border: 0, outline: 'none',
            color: 'var(--ink)', fontFamily: 'var(--serif)', fontSize: 18,
            fontWeight: 300, letterSpacing: 0.2,
            resize: 'none', lineHeight: '24px',
            minHeight: 24, maxHeight: 144,
            overflowY: 'hidden', display: 'block',
            padding: '4px 0', margin: '0',
          }}
        />
        <button
          onClick={triggerSend}
          disabled={!hasContent || loading || disabled}
          aria-label="send"
          style={{
            width: 36, height: 36, borderRadius: 999, flexShrink: 0,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: hasContent && !loading ? 'var(--accent)' : 'rgba(243,234,217,0.07)',
            border: 0, color: hasContent && !loading ? '#1a0e08' : 'var(--ink-mute)',
            cursor: hasContent && !loading ? 'pointer' : 'default',
            transition: 'all 200ms ease',
          }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
            <path d="M5 12h14M13 6l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>
    </div>
  )
}

// ─── Intro splash ─────────────────────────────────────────────────────────────

function IntroSplash({ onDone }) {
  useEffect(() => {
    const t = setTimeout(onDone, 900)
    return () => clearTimeout(t)
  }, [onDone])

  return (
    <div className="intro-screen fixed inset-0 flex flex-col items-center justify-center z-50" style={{ backgroundColor: 'var(--bg)' }}>
      <div style={{ fontFamily: 'var(--display)', fontSize: '3rem', fontWeight: 400, letterSpacing: '0.55em', paddingLeft: '0.55em', color: 'var(--ink)', margin: 0 }}>
        JARVIS
      </div>
      <div style={{ fontFamily: 'var(--sans)', fontSize: '0.65rem', letterSpacing: '0.4em', paddingLeft: '0.4em', color: 'var(--ink-mute)', textTransform: 'uppercase', marginTop: '0.5rem' }}>
        by MG &amp; Co
      </div>
    </div>
  )
}

// ─── Google Connect Prompt ────────────────────────────────────────────────────

function GoogleConnectPrompt({ userId, onConnected }) {
  const [step, setStep] = useState(0)

  const steps = [
    {
      message: "Before we go further — I want to actually be useful to you. Not just talk. To do that, I need access to your world.",
    },
    {
      message: "Your calendar. Your email. The things that actually run your day. I won't touch anything without telling you first.",
    },
    {
      message: "Connect your Google account and I'll have eyes on what matters. You can disconnect anytime.",
    },
  ]

  const handleConnect = () => {
    window.location.href = `https://jarvis-backend-4oz6.onrender.com/api/google/auth/${userId}`
  }

  useEffect(() => {
    if (step < 2) {
      const timer = setTimeout(() => setStep(s => s + 1), 2500)
      return () => clearTimeout(timer)
    }
  }, [step])

  const current = steps[Math.min(step, steps.length - 1)]

  return (
    <div style={{
      position: 'fixed', inset: 0,
      background: 'var(--bg)',
      display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center',
      zIndex: 100, padding: '40px',
      gap: 40,
    }}>
      <div
        key={step}
        className="msg-enter"
        style={{
          fontFamily: 'var(--serif)',
          fontSize: 26, lineHeight: 1.4,
          color: 'var(--ink)', fontWeight: 300,
          maxWidth: 560, textAlign: 'center',
          letterSpacing: 0.2,
        }}
      >
        {current.message}
      </div>
      {step >= 2 && (
        <button
          onClick={handleConnect}
          className="msg-enter"
          style={{
            background: 'transparent',
            border: '1px solid var(--accent)',
            color: 'var(--accent)',
            fontFamily: 'var(--sans)',
            fontSize: 11, letterSpacing: '0.3em',
            textTransform: 'uppercase',
            padding: '14px 32px',
            borderRadius: 999,
            cursor: 'pointer',
          }}
        >
          Connect Google
        </button>
      )}
      <button
        onClick={onConnected}
        style={{
          background: 'transparent', border: 'none',
          color: 'var(--ink-mute)', cursor: 'pointer',
          fontFamily: 'var(--sans)', fontSize: 10,
          letterSpacing: '0.2em', textTransform: 'uppercase',
          marginTop: 8,
        }}
      >
        Skip for now
      </button>
    </div>
  )
}

// ─── Artifact triggers ────────────────────────────────────────────────────────

// Broad triggers for text chat
const ARTIFACT_TRIGGERS = [
  'create', 'make me', 'build me', 'generate me', 'design me', 'draft me',
  'give me a visual', 'presentation', 'slide deck', 'comparison chart',
  'dashboard', 'report', 'invoice', 'proposal', 'landing page', 'visual',
  'diagram', 'chart', 'infographic', 'template', 'brief', 'table',
]

// Stricter triggers for voice — must be an explicit creation command
const VOICE_ARTIFACT_TRIGGERS = [
  'create me', 'make me', 'build me', 'generate me', 'design me',
  'can you create', 'can you make', 'can you build',
  'give me a visual', 'give me a chart', 'give me a presentation', 'give me a report',
]

function isArtifactRequest(message) {
  const lower = message.toLowerCase()
  return ARTIFACT_TRIGGERS.some(t => lower.includes(t))
}

function isExplicitCreate(message) {
  const lower = message.toLowerCase()
  return VOICE_ARTIFACT_TRIGGERS.some(t => lower.includes(t))
}

function fireArtifactFetch(backend, userId, message, artifactMsgId, setMessages) {
  const timeout = setTimeout(() => {
    setMessages(prev => prev.filter(m => m.id !== artifactMsgId))
  }, 30000)

  fetch(`${backend}/api/chat/artifact`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: userId, message, conversation_history: [] }),
  })
    .then(r => r.json())
    .then(data => {
      clearTimeout(timeout)
      if (data.artifact && data.artifact.length > 100) {
        setMessages(prev => prev.map(m =>
          m.id === artifactMsgId
            ? { ...m, content: { html: data.artifact, title: message.slice(0, 50) }, loading: false }
            : m
        ))
      } else {
        setMessages(prev => prev.filter(m => m.id !== artifactMsgId))
      }
    })
    .catch(() => {
      clearTimeout(timeout)
      setMessages(prev => prev.filter(m => m.id !== artifactMsgId))
    })
}

// ─── Main ─────────────────────────────────────────────────────────────────────

function captionFor(s) {
  if (s === 'listening') return '“…I’m here. Take your time.”'
  if (s === 'speaking')  return ''
  if (s === 'thinking')  return '“Thinking.”'
  return '“I’ll be here when you need me.”'
}

export default function Home() {
  const router = useRouter()
  const [showIntro, setShowIntro]         = useState(true)
  const [messages, setMessages]           = useState([])
  const [input, setInput]                 = useState('')
  const [loading, setLoading]             = useState(false)
  const [userId, setUserId]               = useState(null)
  const [user, setUser]                   = useState(null)
  const [authLoading, setAuthLoading]     = useState(true)
  const [onboardingComplete, setOnboarding] = useState(null)
  const [showPanel, setShowPanel]         = useState(false)
  const [proactiveHint, setProactiveHint] = useState(null)
  const [voiceMode, setVoiceMode]         = useState(false)
  const [jarvisSpeaking, setJarvisSpeaking] = useState(false)
  const [voiceConnecting, setVoiceConnecting] = useState(false)
  const [voiceError, setVoiceError]       = useState(null)
  const [googleConnected, setGoogleConnected] = useState(null)
  const voiceManagerRef = useRef(null)
  const msgIdRef = useRef(1)
  const conversationBufferRef = useRef([])
  const reconnectAttemptsRef = useRef(0)
  const fileInputRef = useRef(null)
  const [uploadingFile, setUploadingFile] = useState(false)
  const [pastedImage, setPastedImage] = useState(null)
  const [pendingFiles, setPendingFiles] = useState([])
  const [isDragging, setIsDragging] = useState(false)
  const [timezoneConfirmed, setTimezoneConfirmed] = useState(null)
  const [toast, setToast] = useState(null)
  const [isMobile, setIsMobile] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const mobileScrollRef = useRef(null)
  const isVoiceEnabledRef = useRef(false)
  const MAX_RECONNECT = 5

  // Flush voice transcript every 30s so memory saves even on short sessions
  useEffect(() => {
    if (!userId) return
    const interval = setInterval(() => {
      if (conversationBufferRef.current.length > 0) {
        flushVoiceTranscript()
      }
    }, 30000)
    return () => clearInterval(interval)
  }, [userId])

  useEffect(() => {
    const check = () => setIsMobile(window.innerWidth < 768)
    check()
    window.addEventListener('resize', check)
    return () => window.removeEventListener('resize', check)
  }, [])

  useEffect(() => {
    if (isMobile && mobileScrollRef.current) {
      mobileScrollRef.current.scrollTo({ top: mobileScrollRef.current.scrollHeight, behavior: 'smooth' })
    }
  }, [messages, loading, isMobile])

  // ─── Onboard detection + preference routing ───────────────────────────────
  // Merged into ONE effect so the mode-write never races the mode-read.
  // When ?onboard=personal is in the URL we already know the choice — set mode
  // and return before running getJarvisMode (which would see null and redirect).
  useEffect(() => {
    if (!userId) return
    const params = new URLSearchParams(window.location.search)
    if (params.get('onboard') === 'personal') {
      setJarvisMode(userId, 'personal').catch(() => {})
      window.history.replaceState({}, '', '/')
      return  // stay at / — skip mode-check
    }
    getJarvisMode(userId).then(mode => {
      if (mode === 'business') {
        router.replace('/business/chat')
      } else if (!mode) {
        router.replace('/welcome')
      }
      // mode === 'personal' → stay here
    }).catch(() => {})
  }, [userId])

  // Detect ?calendar=connected after Google OAuth redirect
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    if (params.get('calendar') === 'connected') {
      setGoogleConnected(true)
      window.history.replaceState({}, '', '/')
      // Refresh session to ensure userId is current after OAuth redirect
      if (supabase) {
        supabase.auth.getSession().then(({ data: { session } }) => {
          if (session?.user) {
            const jarvisId = 'user_' + session.user.id.replace(/-/g, '')
            setUserId(prev => prev === jarvisId ? prev : jarvisId)
          }
        }).catch(() => {})
      }
    }
  }, [])

  // Check Google connection status once userId is known
  useEffect(() => {
    if (!userId) return
    fetch(`${BACKEND}/api/google/status/${userId}`)
      .then(r => r.json())
      .then(data => setGoogleConnected(data.connected))
      .catch(() => setGoogleConnected(false))
  }, [userId])

  // Silently capture browser timezone on auth so Jarvis uses user's local time
  useEffect(() => {
    if (!userId) return
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone
    if (!tz) return
    fetch(`${BACKEND}/api/user-preferences/timezone`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: userId, timezone: tz }),
    }).catch(() => {})
  }, [userId])

  // Check timezone confirmation once userId is known
  useEffect(() => {
    if (!userId) return
    fetch(`${BACKEND}/api/user-preferences/${userId}`)
      .then(r => r.json())
      .then(data => setTimezoneConfirmed(data.timezone_confirmed ?? false))
      .catch(() => setTimezoneConfirmed(true))
  }, [userId])

  // Fetch unread proactive messages (morning briefings) on login
  useEffect(() => {
    if (!userId) return
    fetch(`${BACKEND}/api/proactive/${userId}`)
      .then(r => r.json())
      .then(data => {
        if (data.messages?.length > 0) {
          data.messages.forEach(msg => {
            msgIdRef.current += 1
            setMessages(prev => [...prev, {
              id: msgIdRef.current,
              role: 'assistant',
              content: msg,
              proactive: true,
            }])
          })
        }
      })
      .catch(() => {})
  }, [userId])

  // ─── Auth ──────────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!supabase) {
      setAuthLoading(false)
      return
    }

    const getSession = async () => {
      try {
        const { data: { session }, error } = await supabase.auth.getSession()
        if (error) {
          console.error('Session error:', error)
          const { data: refreshData } = await supabase.auth.refreshSession()
          if (refreshData?.session?.user) {
            setUser(refreshData.session.user)
            setUserId('user_' + refreshData.session.user.id.replace(/-/g, ''))
            setAuthLoading(false)
            return
          }
          router.replace('/welcome')
          return
        }
        if (session?.user) {
          setUser(session.user)
          setUserId('user_' + session.user.id.replace(/-/g, ''))
        } else {
          router.replace('/welcome')
        }
      } catch (err) {
        console.error('Auth error:', err)
        router.replace('/welcome')
      } finally {
        setAuthLoading(false)
      }
    }
    getSession()

    const { data: { subscription } } = supabase.auth.onAuthStateChange((event, session) => {
      if (event === 'SIGNED_OUT') {
        setUser(null)
        setUserId(null)
        router.replace('/welcome')
        return
      }
      if (session?.user) {
        setUser(prev => {
          if (prev?.id === session.user.id) return prev
          return session.user
        })
        setUserId(prev => {
          const newId = 'user_' + session.user.id.replace(/-/g, '')
          if (prev === newId) return prev
          return newId
        })
      }
    })
    return () => subscription.unsubscribe()
  }, [])

  useEffect(() => {
    if (!userId) return
    Promise.all([
      fetch(`${BACKEND}/api/user/onboarding-status/${userId}`).then(r => r.json()),
      fetch(`${BACKEND}/api/history/${userId}`).then(r => r.json()),
    ]).then(([onboardingData, historyData]) => {
      setOnboarding(onboardingData.onboarding_complete)
      const history = historyData.messages || []
      if (history.length > 0) {
        msgIdRef.current = history.length + 1
        const mapped = history.map((m, i) => ({ id: i + 1, role: m.role, content: m.content }))
        // Mark orphaned: last message is user with no assistant response following
        const last = mapped[mapped.length - 1]
        if (last?.role === 'user') {
          mapped[mapped.length - 1] = { ...last, orphaned: true }
        }
        setMessages(mapped)
      } else if (!onboardingData.onboarding_complete) {
        setMessages([OPENING_MESSAGE])
      }
    }).catch(() => setOnboarding(true))
  }, [userId])

  // Proactive polling — every 5 min
  useEffect(() => {
    if (!userId || !onboardingComplete) return
    const poll = async () => {
      try {
        const res = await fetch(`${BACKEND}/api/proactive/check/${userId}`)
        if (!res.ok) return
        const data = await res.json()
        if (data.has_message && data.message) {
          msgIdRef.current += 1
          setMessages(prev => [...prev, { id: msgIdRef.current, role: 'assistant', content: data.message, proactive: true }])
          setProactiveHint(data.message)
          if (!document.hasFocus()) document.title = 'Jarvis has something for you'
        }
      } catch {}
    }
    const interval = setInterval(poll, 300000)
    return () => clearInterval(interval)
  }, [userId, onboardingComplete])

  useEffect(() => {
    const onFocus = () => { document.title = 'Jarvis — Your Personal AI' }
    window.addEventListener('focus', onFocus)
    return () => window.removeEventListener('focus', onFocus)
  }, [])

  // Keep voice enabled ref in sync for streaming closures
  useEffect(() => { isVoiceEnabledRef.current = voiceMode }, [voiceMode])

  // Voice cleanup on unmount — must be before any conditional return
  useEffect(() => () => voiceManagerRef.current?.destroy(), [])

  if (authLoading) {
    return (
      <div style={{ background: 'var(--bg)', height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ fontFamily: 'var(--display)', fontSize: '1.6rem', letterSpacing: '0.5em', paddingLeft: '0.5em', color: 'var(--ink)' }}>
          JARVIS
        </div>
      </div>
    )
  }

  if (userId && timezoneConfirmed === false) {
    return (
      <TimezoneStep
        onConfirm={async (tz) => {
          try {
            await fetch(`${BACKEND}/api/user-preferences/timezone`, {
              method: 'PATCH',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ user_id: userId, timezone: tz, timezone_confirmed: true }),
            })
            await fetch(`${BACKEND}/api/user-preferences/complete-onboarding`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ user_id: userId }),
            })
          } catch {}
          setTimezoneConfirmed(true)
        }}
      />
    )
  }

  // ─── Voice ──────────────────────────────────────────────────────────────────
  async function flushVoiceTranscript() {
    const buffer = conversationBufferRef.current
    if (!buffer.length || !userId) return
    conversationBufferRef.current = []
    try {
      await fetch(`${BACKEND}/api/voice/save-transcript`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, messages: buffer }),
      })
    } catch (err) {
      console.error('Failed to save voice transcript:', err)
    }
  }

  async function sendViaVoice(text) {
    await sendMessage({ apiText: text, displayText: text, voiceMode: true })
  }

  // ── Single-tap voice toggle ───────────────────────────────────────────────────

  async function toggleVoiceMode() {
    if (voiceMode) {
      // Stop
      voiceManagerRef.current?.stopHandsFree()
      voiceManagerRef.current = null
      setVoiceMode(false)
      setJarvisSpeaking(false)
      setVoiceError(null)
      return
    }

    // Start
    if (!userId) return
    setVoiceConnecting(true)
    setVoiceError(null)
    try {
      const jv = new JarvisVoice({
        userId,
        onSpeakingStart: () => setJarvisSpeaking(true),
        onSpeakingEnd: () => setJarvisSpeaking(false),
        onError: (msg) => setVoiceError(msg),
      })
      // Unlock AudioContext during user gesture (required by browser autoplay policy)
      await jv.resumeAudio()
      await jv.startHandsFree(sendViaVoice)
      voiceManagerRef.current = jv
      setVoiceMode(true)
    } catch (err) {
      console.error('Voice toggle: start failed', err)
      setVoiceError('Could not start voice. Check mic permissions.')
    } finally {
      setVoiceConnecting(false)
    }
  }

  function _inferMime(file) {
    if (file.type) return file.type
    const ext = (file.name || '').split('.').pop().toLowerCase()
    const map = { jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png', gif: 'image/gif', webp: 'image/webp', bmp: 'image/bmp', svg: 'image/svg+xml', pdf: 'application/pdf', docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', doc: 'application/msword', txt: 'text/plain', csv: 'text/csv', md: 'text/plain' }
    return map[ext] || 'application/octet-stream'
  }

  async function handleFileSelect(source) {
    const files = Array.isArray(source)
      ? source
      : source instanceof FileList
      ? Array.from(source)
      : source?.target?.files
      ? Array.from(source.target.files)
      : []
    if (!files.length || !userId) return
    if (source?.target) source.target.value = ''

    for (const file of files) {
      if (file.size > 25 * 1024 * 1024) {
        setToast({ message: `${file.name} is over the 25 MB limit` })
        continue
      }
      const id = Math.random().toString(36).slice(2, 10)
      const mime = _inferMime(file)
      console.log(`FILE_SELECT: name=${file.name} declared_type=${file.type || '(empty)'} resolved_mime=${mime}`)

      if (mime.startsWith('image/')) {
        const reader = new FileReader()
        reader.onload = (ev) => {
          const dataUrl = ev.target.result
          console.log(`FILE_SELECT: image ready name=${file.name} preview_length=${dataUrl?.length}`)
          setPendingFiles(prev => [...prev, {
            id, name: file.name, type: mime, size: file.size,
            preview: dataUrl, status: 'ready',
          }])
        }
        reader.onerror = (ev) => {
          console.error('FILE_SELECT: FileReader error', ev)
          setPendingFiles(prev => prev.filter(f => f.id !== id))
        }
        reader.readAsDataURL(file)
      } else {
        setPendingFiles(prev => [...prev, {
          id, name: file.name, type: file.type, size: file.size, status: 'uploading',
        }])
        setUploadingFile(true)
        try {
          const form = new FormData()
          form.append('file', file)
          form.append('user_id', userId)
          const res = await fetch(`${BACKEND}/api/documents/upload`, { method: 'POST', body: form })
          if (!res.ok) throw new Error(`Upload failed: ${res.status}`)
          const data = await res.json()
          setPendingFiles(prev => prev.map(f => f.id === id
            ? { ...f, docId: data.document_id, chunkCount: data.chunk_count, status: 'ready' }
            : f))
        } catch (err) {
          console.error('File upload error:', err)
          setPendingFiles(prev => prev.map(f => f.id === id ? { ...f, status: 'error', errorMsg: err.message } : f))
        } finally {
          setUploadingFile(false)
        }
      }
    }
  }

  const lastMsg = messages[messages.length - 1]
  const isStreaming = lastMsg?.streaming === true
  const orbState =
    voiceMode && jarvisSpeaking ? 'speaking' :
    voiceMode                   ? 'listening' :
    loading                     ? 'thinking' :
    isStreaming                  ? 'speaking' :
    'idle'

  function isPdfExportRequest(msg) {
    const lower = msg.toLowerCase()
    const hasPdf = lower.includes('pdf')
    const hasExportVerb = ['export', 'save', 'download', 'generate',
      'make', 'create', 'turn into', 'convert'].some(v => lower.includes(v))
    return hasPdf && hasExportVerb
  }

  async function handlePdfExport(userText) {
    // Find last substantial assistant message to export
    const lastAssistant = [...messages].reverse().find(
      m => m.role === 'assistant' && typeof m.content === 'string' && m.content.trim().length > 80
    )
    const content = lastAssistant?.content ?? messages
      .filter(m => m.role === 'assistant' && typeof m.content === 'string')
      .map(m => m.content).join('\n\n')

    if (!content.trim()) {
      msgIdRef.current += 1
      setMessages(prev => [...prev, {
        id: msgIdRef.current, role: 'assistant',
        content: "There's nothing to export yet — ask me something first.",
      }])
      return
    }

    // Show user message + loading state
    msgIdRef.current += 1
    const userMsgId = msgIdRef.current
    setMessages(prev => [...prev, { id: userMsgId, role: 'user', content: userText }])
    setLoading(true)

    try {
      const res = await fetch(`${BACKEND}/api/export/pdf`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content, title: '', user_id: userId ?? '' }),
      })
      if (!res.ok) throw new Error(`PDF export failed: ${res.status}`)

      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'jarvis-export.pdf'
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      setTimeout(() => URL.revokeObjectURL(url), 10000)

      msgIdRef.current += 1
      setMessages(prev => [...prev, {
        id: msgIdRef.current, role: 'assistant',
        content: 'Done. Your PDF is downloading now.',
      }])
    } catch (err) {
      console.error('PDF export error:', err)
      msgIdRef.current += 1
      setMessages(prev => [...prev, {
        id: msgIdRef.current, role: 'assistant',
        content: "Sorry — couldn't generate the PDF. Try again in a moment.",
      }])
    } finally {
      setLoading(false)
    }
  }

  async function sendMessage(override = null) {
    const apiText = (override?.apiText ?? input).trim()
    const displayText = (override?.displayText ?? apiText)

    // Collect pending file attachments (only when not an override call)
    const pendingImg = !override
      ? pendingFiles.find(f => f.type?.startsWith('image/') && f.preview && f.status === 'ready')
      : null
    const readyDocs = !override
      ? pendingFiles.filter(f => f.docId && f.status === 'ready')
      : []

    const imageB64 = override?.imageBase64 ?? (pendingImg?.preview ?? (pastedImage ? pastedImage.preview : null))
    const imageType = override?.imageType ?? (pendingImg?.type ?? (pastedImage ? pastedImage.type : null))
    const imagePreview = pendingImg?.preview ?? pastedImage?.preview ?? null
    const attachment = override?.attachment ?? (readyDocs.length > 0
      ? { name: readyDocs.map(f => f.name).join(', '), type: 'docs', size: 0 }
      : null)

    console.log('SEND: pendingFiles state', pendingFiles)
    console.log('SEND: pendingImg found', !!pendingImg, 'imageB64 present', !!imageB64, 'imageType', imageType)
    console.log('sendMessage called with:', apiText.slice(0, 80))
    if ((!apiText && !imageB64 && readyDocs.length === 0) || loading || isStreaming) return
    if (!override) {
      setInput('')
      setPastedImage(null)
      setPendingFiles([])
    }

    // Intercept PDF export requests before hitting the chat API
    console.log('PDF intent check:', JSON.stringify(apiText), '→', isPdfExportRequest(apiText))
    if (!override && apiText && isPdfExportRequest(apiText)) {
      await handlePdfExport(apiText)
      return
    }

    const historyForApi = messages
      .slice(1)
      .filter(m => m.role !== 'artifact' && typeof m.content === 'string' && m.content.trim().length > 0)
      .map(({ role, content }) => ({ role, content }))
    msgIdRef.current += 1
    const userMsgId = msgIdRef.current
    setMessages(prev => [...prev, { id: userMsgId, role: 'user', content: displayText, attachment, imagePreview, pending: true }])
    setLoading(true)

    // Inject doc references into the message so Jarvis knows to search them
    let messageText = apiText || ''
    if (readyDocs.length > 0 && messageText) {
      messageText += `\n\n[Attached docs: ${readyDocs.map(f => `${f.name} (${f.chunkCount} sections indexed)`).join(', ')}]`
    } else if (readyDocs.length > 0) {
      messageText = `[Attached docs: ${readyDocs.map(f => `${f.name} (${f.chunkCount} sections indexed)`).join(', ')}]`
    }

    const bodyPayload = { user_id: userId, message: messageText, conversation_history: historyForApi }
    if (imageB64) {
      bodyPayload.image_base64 = imageB64
      bodyPayload.image_type = imageType || 'image/png'
    }
    const isVoiceMessage = override?.voiceMode === true
    if (isVoiceMessage) {
      bodyPayload.voice_mode = true
    }
    // Also include all ready images as attachments (belt-and-suspenders for drag-drop)
    const readyImages = !override
      ? pendingFiles.filter(f => f.type?.startsWith('image/') && f.preview && f.status === 'ready')
      : []
    if (readyImages.length > 0) {
      bodyPayload.attachments = readyImages.map(f => ({ url: f.preview, file_type: f.type }))
    }
    console.log('SEND: payload keys', Object.keys(bodyPayload), 'image_base64 present', !!bodyPayload.image_base64, 'image_base64 length', bodyPayload.image_base64?.length ?? 0, 'attachments', bodyPayload.attachments?.length ?? 0)

    const MAX_RETRIES = 2
    let streamMsgId = null

    for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
      try {
        const controller = new AbortController()
        const timeoutId = setTimeout(() => controller.abort(), 60_000)

        const res = await fetch(`${BACKEND}/api/chat/stream`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(bodyPayload),
          signal: controller.signal,
        })
        clearTimeout(timeoutId)

        if (!res.ok) throw new Error(`${res.status}`)

        // Fetch succeeded — mark user message confirmed (no longer pending)
        setMessages(prev => prev.map(m => m.id === userMsgId ? { ...m, pending: false } : m))

        msgIdRef.current += 1
        streamMsgId = msgIdRef.current
        setMessages(prev => [...prev, { id: streamMsgId, role: 'assistant', content: '', streaming: true }])
        setLoading(false)

        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        let accumulated = ''
        let done = false
        let voiceFired = false   // true once TTS has been queued via early __voice event

        while (!done) {
          const { done: readerDone, value } = await reader.read()
          if (readerDone) break
          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() ?? ''
          for (const line of lines) {
            if (!line.startsWith('data: ')) continue
            const raw = line.slice(6)
            if (raw === '[DONE]') {
              setMessages(prev => {
                const updated = [...prev]
                const idx = updated.findIndex(m => m.id === streamMsgId)
                if (idx !== -1) updated[idx] = { id: streamMsgId, role: 'assistant', content: accumulated }
                return updated
              })
              // Speak the response only when sent via voice and not already fired
              if (isVoiceMessage && !voiceFired && accumulated?.trim()) {
                voiceManagerRef.current?.speak(accumulated)
              }
              done = true
              break
            }
            if (raw === '[ERROR]') {
              setMessages(prev => prev.filter(m => m.id !== streamMsgId))
              done = true
              break
            }
            if (raw.startsWith('[DEBUG:') && raw.endsWith(']')) {
              if (DEV_MODE) {
                const debugText = raw.slice(7, -1)
                setToast({ message: `🐛 ${debugText}`, retryMsgId: null, duration: 8000 })
              }
              continue
            }
            try {
              const chunk = JSON.parse(raw)
              // Early voice event — start TTS immediately, don't add to displayed text
              if (chunk && typeof chunk === 'object' && chunk.__voice) {
                if (isVoiceMessage && chunk.text?.trim()) {
                  voiceManagerRef.current?.speak(chunk.text)
                  voiceFired = true
                }
                continue
              }
              accumulated += chunk
              setMessages(prev => {
                const updated = [...prev]
                const idx = updated.findIndex(m => m.id === streamMsgId)
                if (idx !== -1) updated[idx] = { ...updated[idx], content: accumulated }
                return updated
              })
            } catch {}
          }
        }

        if (!onboardingComplete) {
          fetch(`${BACKEND}/api/user/onboarding-status/${userId}`)
            .then(r => r.json())
            .then(d => setOnboarding(d.onboarding_complete))
            .catch(() => {})
        }

        if (!override && isArtifactRequest(displayText) && userId) {
          msgIdRef.current += 1
          const artifactMsgId = msgIdRef.current
          setMessages(prev => [...prev, {
            id: artifactMsgId,
            role: 'artifact',
            content: { html: null, title: displayText.slice(0, 50) },
            loading: true,
          }])
          fireArtifactFetch(BACKEND, userId, displayText, artifactMsgId, setMessages)
        }

        setLoading(false)
        return // success — exit retry loop

      } catch (err) {
        console.error(`sendMessage attempt ${attempt + 1} failed:`, err)
        if (streamMsgId) {
          setMessages(prev => prev.filter(m => m.id !== streamMsgId))
          streamMsgId = null
        }
        setLoading(false)
        if (attempt < MAX_RETRIES) {
          await new Promise(r => setTimeout(r, 1000 * Math.pow(2, attempt)))
        }
      }
    }

    // All retries exhausted — mark message as failed
    setMessages(prev => prev.map(m => m.id === userMsgId ? { ...m, pending: false, failed: true } : m))
    setToast({ message: 'Message failed — tap to retry', retryMsgId: userMsgId })
    setLoading(false)
  }

  function handleRetry(msgOrId) {
    const targetId = typeof msgOrId === 'object' ? msgOrId.id : msgOrId
    setMessages(prev => {
      const msg = prev.find(m => m.id === targetId)
      if (!msg) return prev
      // Remove failed/orphaned message — sendMessage will add a fresh pending one
      return prev.filter(m => m.id !== targetId)
    })
    setToast(null)
    const msg = messages.find(m => m.id === targetId)
    if (msg) {
      sendMessage({ apiText: msg.content, displayText: msg.content, attachment: msg.attachment ?? null })
    }
  }

  return (
    <>
      {showIntro && <IntroSplash onDone={() => setShowIntro(false)} />}
      {showPanel && userId && <KnowledgePanel userId={userId} onClose={() => setShowPanel(false)} />}
      <SignOutDrawer isOpen={drawerOpen} onClose={() => setDrawerOpen(false)} user={user} userId={userId} />
      {toast && (
        <Toast
          message={toast.message}
          onTap={toast.retryMsgId ? () => handleRetry(toast.retryMsgId) : null}
          onClose={() => setToast(null)}
          duration={toast.duration ?? 6000}
        />
      )}
      {googleConnected === false && !showIntro && userId && (
        <GoogleConnectPrompt
          userId={userId}
          onConnected={() => setGoogleConnected(true)}
        />
      )}

      {/* Film grain */}
      <svg style={{ position: 'fixed', top: 0, left: 0, width: 0, height: 0, overflow: 'hidden' }}>
        <defs>
          <filter id="jarvis-grain">
            <feTurbulence type="fractalNoise" baseFrequency="0.75" numOctaves="4" stitchTiles="stitch" />
            <feColorMatrix type="saturate" values="0" />
          </filter>
        </defs>
      </svg>
      <div style={{
        position: 'fixed', inset: 0, pointerEvents: 'none', zIndex: 9999,
        opacity: 0.028, filter: 'url(#jarvis-grain)', background: '#888',
      }} />

      {/* Warm vignette */}
      <div style={{
        position: 'fixed', inset: 0, pointerEvents: 'none', zIndex: 1,
        background: 'radial-gradient(ellipse 90% 85% at 50% 45%, transparent 35%, rgba(8,6,4,0.72) 100%)',
      }} />

      {/* Drag-and-drop overlay */}
      {isDragging && (
        <div style={{
          position: 'fixed', inset: 0, zIndex: 1001,
          background: 'rgba(200, 75, 49, 0.08)',
          backdropFilter: 'blur(4px)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          border: '2px dashed rgba(200, 75, 49, 0.5)',
          pointerEvents: 'none',
        }}>
          <span style={{
            color: 'var(--accent)', fontFamily: 'var(--sans)',
            fontSize: '1rem', letterSpacing: '0.25em', textTransform: 'uppercase',
          }}>
            Drop to attach
          </span>
        </div>
      )}

      {/* Layout — mobile / desktop */}
      <div
        onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); setIsDragging(true) }}
        onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget)) setIsDragging(false) }}
        onDrop={(e) => {
          e.preventDefault()
          e.stopPropagation()
          setIsDragging(false)
          const droppedFiles = Array.from(e.dataTransfer.files)
          if (droppedFiles.length) handleFileSelect(droppedFiles)
        }}
      >
      {isMobile ? (

        /* ── MOBILE LAYOUT ─────────────────────────────────────────────── */
        <div style={{ position: 'relative', height: '100dvh', zIndex: 2, overflowX: 'hidden', background: '#000' }}>

          {/* Orb — fixed behind scrolling content; two divs to avoid transform/animation conflict */}
          <div
            style={{
              position: 'fixed', left: 'calc(50% - 100px)', top: '22vh',
              width: 200, height: 200,
              zIndex: 1, opacity: 0.45, pointerEvents: 'none',
            }}
          >
            <div
              style={{ animation: 'softFloat 6s ease-in-out infinite', width: '100%', height: '100%', borderRadius: '50%' }}
              className={jarvisSpeaking ? 'orb-speaking' : voiceMode ? 'orb-listening' : ''}
            >
              <Orb state={orbState} orbStyle="aurora" accent="#ff9072" size={200} />
            </div>
          </div>

          {/* Header — fixed at top, z:20 */}
          <div style={{
            position: 'fixed', top: 0, left: 0, right: 0, zIndex: 20,
            height: 56, display: 'flex', alignItems: 'center',
            justifyContent: 'space-between', padding: '0 20px',
            background: 'rgba(0,0,0,0.72)', backdropFilter: 'blur(12px)',
          }}>
            <button
              onClick={() => setDrawerOpen(true)}
              aria-label="menu"
              style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 6, display: 'flex', flexDirection: 'column', gap: 4.5, alignItems: 'center' }}
            >
              <span style={{ display: 'block', width: 18, height: 1.5, background: 'var(--ink-soft)', borderRadius: 1 }} />
              <span style={{ display: 'block', width: 18, height: 1.5, background: 'var(--ink-soft)', borderRadius: 1 }} />
              <span style={{ display: 'block', width: 18, height: 1.5, background: 'var(--ink-soft)', borderRadius: 1 }} />
            </button>
            <Wordmark />
            <StatusPill state={orbState} />
          </div>

          {/* Scrollable content — scrolls over the fixed orb, z:10 */}
          <div
            ref={mobileScrollRef}
            style={{
              position: 'absolute', inset: 0,
              overflowY: 'auto', overflowX: 'hidden',
              paddingTop: 56, paddingBottom: 110,
              zIndex: 10,
            }}
          >
            {/* Proactive banner */}
            {proactiveHint && (
              <div style={{
                margin: '12px 16px 0',
                padding: '14px 16px 14px 18px',
                background: 'rgba(90,0,0,0.2)',
                border: '1px solid rgba(239,68,68,0.35)',
                borderRadius: 16, animation: 'fadeUp 500ms ease both',
                backdropFilter: 'blur(8px)', fontFamily: 'var(--sans)',
              }}>
                <div style={{ fontSize: 9, letterSpacing: '0.25em', textTransform: 'uppercase', color: '#f87171', marginBottom: 8, fontWeight: 500 }}>
                  Proactive · just now
                </div>
                <div style={{ fontSize: 14, color: 'rgba(243,234,217,0.9)', lineHeight: 1.5, fontWeight: 300, marginBottom: 12, wordBreak: 'break-word', overflowWrap: 'anywhere' }}>
                  {proactiveHint}
                </div>
                <div style={{ display: 'flex', gap: 14 }}>
                  <button onClick={() => setProactiveHint(null)} style={{ background: 'transparent', border: 0, padding: 0, cursor: 'pointer', fontFamily: 'var(--sans)', fontSize: 11, letterSpacing: '0.2em', textTransform: 'uppercase', color: '#f87171', fontWeight: 500 }}>Handle it</button>
                  <button onClick={() => setProactiveHint(null)} style={{ background: 'transparent', border: 0, padding: 0, cursor: 'pointer', fontFamily: 'var(--sans)', fontSize: 11, letterSpacing: '0.2em', textTransform: 'uppercase', color: 'var(--ink-mute)', fontWeight: 500 }}>Dismiss</button>
                </div>
              </div>
            )}

            {/* Idle state — caption + memory text float below the orb */}
            {messages.length === 0 && !loading && (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', paddingTop: 'calc(22vh + 240px)', gap: 12, paddingLeft: 24, paddingRight: 24, paddingBottom: 32 }}>
                {!voiceMode && (
                  <div style={{ fontFamily: 'var(--serif)', fontStyle: 'italic', fontSize: 14, color: 'var(--ink-soft)', fontWeight: 300, textAlign: 'center', lineHeight: 1.45, wordBreak: 'break-word', overflowWrap: 'anywhere' }}>
                    {captionFor(orbState)}
                  </div>
                )}
                {voiceMode && (
                  <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--accent)', animation: 'inkPulse 1.4s ease-in-out infinite', display: 'inline-block' }} />
                    <span style={{ fontFamily: 'var(--sans)', fontSize: 10, color: 'var(--accent)', letterSpacing: '0.2em', textTransform: 'uppercase' }}>{jarvisSpeaking ? 'Speaking' : 'Listening'}</span>
                  </span>
                )}
                <div style={{ fontFamily: 'var(--sans)', fontSize: 10, letterSpacing: '0.25em', textTransform: 'uppercase', color: 'var(--ink-mute)' }}>
                  memory · present
                </div>
                {voiceError && (
                  <div style={{ fontFamily: 'var(--sans)', fontSize: 9, color: '#ef4444', textAlign: 'center', wordBreak: 'break-word', overflowWrap: 'anywhere' }}>
                    {voiceError}
                  </div>
                )}
                {onboardingComplete === false && (
                  <div className="onboarding-pulse" style={{ fontFamily: 'var(--sans)', fontSize: 9, letterSpacing: '0.2em', textTransform: 'uppercase', color: 'var(--accent)', opacity: 0.6 }}>
                    Getting to know you…
                  </div>
                )}
              </div>
            )}

            {/* Conversation messages — start below the orb area */}
            {(messages.length > 0 || loading) && (
              <div
                className="mobile-chat-messages"
                style={{
                  paddingTop: 'calc(22vh + 240px)',
                  paddingLeft: 20, paddingRight: 20, paddingBottom: 16,
                  wordBreak: 'break-word', overflowWrap: 'anywhere',
                }}
              >
                {messages.map((m, i) => (
                  <div key={m.id ?? i} className="msg-enter">
                    <Message msg={m} isLatest={i === messages.length - 1 && !loading} onRetry={handleRetry} />
                  </div>
                ))}
                {loading && <ThinkingIndicator />}
              </div>
            )}
          </div>

          {/* Input bar — fixed at bottom with gradient, z:20 */}
          <div style={{
            position: 'fixed', bottom: 0, left: 0, right: 0, zIndex: 20,
            background: 'linear-gradient(to top, #000000 55%, rgba(0,0,0,0.9) 80%, transparent 100%)',
          }}>
            <InputBar
              orbState={orbState}
              input={input}
              setInput={setInput}
              onSend={sendMessage}
              onMicClick={toggleVoiceMode}
              voiceMode={voiceMode}
              voiceConnecting={voiceConnecting}
              loading={loading || isStreaming}
              disabled={!userId}
              fileInputRef={fileInputRef}
              uploadingFile={uploadingFile}
              onFileSelect={handleFileSelect}
              pendingFiles={pendingFiles}
              onRemoveFile={(id) => setPendingFiles(prev => prev.filter(f => f.id !== id))}
              pastedImage={pastedImage}
              onPastedImageChange={setPastedImage}
              mobile
            />
          </div>
        </div>

      ) : (

        /* ── DESKTOP LAYOUT (unchanged) ────────────────────────────────── */
        <div style={{
          position: 'relative', height: '100vh', zIndex: 2,
          display: 'grid',
          gridTemplateColumns: '420px 1fr',
          gridTemplateRows: '64px 1fr auto',
          gridTemplateAreas: `
            "topL topR"
            "orb  conv"
            "orb  input"
          `,
        }}>
          {/* top-left: wordmark */}
          <div style={{ gridArea: 'topL', padding: '20px 40px', display: 'flex', alignItems: 'center' }}>
            <Wordmark />
          </div>

          {/* top-right: status + chips */}
          <div style={{ gridArea: 'topR', padding: '20px 32px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
            <StatusPill state={orbState} />
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end', alignItems: 'center' }}>
              <PermissionChip icon="◉" label="Screen"   granted />
              <PermissionChip icon="⌖" label="Cursor"   granted />
              <PermissionChip icon="✦" label="Calendar" granted />
              <PermissionChip icon="◍" label="Audio"    granted />
              {userId && (
                <button
                  onClick={() => setShowPanel(true)}
                  title="What Jarvis knows"
                  style={{
                    background: 'none', border: '1px solid var(--line)', borderRadius: '6px',
                    color: 'var(--accent)', fontSize: '0.8rem', padding: '0.35rem 0.55rem',
                    cursor: 'pointer', opacity: 0.6, letterSpacing: '0.05em',
                    transition: 'opacity 0.2s', fontFamily: 'var(--sans)',
                  }}
                  onMouseEnter={e => e.currentTarget.style.opacity = '1'}
                  onMouseLeave={e => e.currentTarget.style.opacity = '0.6'}
                >◉</button>
              )}


              {/* Mode toggle */}
              {userId && (
                <ModeToggle userId={userId} currentMode="personal" />
              )}

              {/* Avatar + sign out */}
              {user && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginLeft: 4 }}>
                  {user.user_metadata?.avatar_url && (
                    <img
                      src={user.user_metadata.avatar_url}
                      alt="avatar"
                      referrerPolicy="no-referrer"
                      style={{ width: 24, height: 24, borderRadius: '50%', opacity: 0.8, border: '1px solid var(--line)' }}
                    />
                  )}
                  <button
                    onClick={async () => {
                      await supabase.auth.signOut()
                      router.replace('/welcome')
                    }}
                    style={{
                      background: 'none', border: 'none', padding: 0, cursor: 'pointer',
                      fontFamily: 'var(--sans)', fontSize: '0.65rem', letterSpacing: '0.1em',
                      color: 'var(--ink-mute)', textTransform: 'uppercase', opacity: 0.55,
                      transition: 'opacity 0.2s',
                    }}
                    onMouseEnter={e => e.currentTarget.style.opacity = '1'}
                    onMouseLeave={e => e.currentTarget.style.opacity = '0.55'}
                  >
                    Sign out
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* left: orb panel */}
          <div style={{
            gridArea: 'orb', position: 'relative',
            display: 'flex', flexDirection: 'column',
            alignItems: 'center', justifyContent: 'center',
            gap: 28, padding: '0 20px 40px',
          }}>
            <div
              style={{ animation: 'softFloat 6s ease-in-out infinite', borderRadius: '50%' }}
              className={jarvisSpeaking ? 'orb-speaking' : voiceMode ? 'orb-listening' : ''}
            >
              <Orb state={orbState} orbStyle="aurora" accent="#ff9072" size={340} />
            </div>
            <div style={{
              fontFamily: 'var(--serif)', fontStyle: 'italic', fontSize: 17,
              color: 'var(--ink-soft)', fontWeight: 300, textAlign: 'center',
              maxWidth: 320, lineHeight: 1.45, minHeight: 48,
            }}>
              {voiceMode ? '' : captionFor(orbState)}
            </div>
            <div style={{ fontFamily: 'var(--sans)', fontSize: 9, letterSpacing: '0.38em', textTransform: 'uppercase', color: 'var(--ink-mute)' }}>
              {voiceMode ? (
                <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{
                    width: 6, height: 6, borderRadius: '50%', background: 'var(--accent)',
                    animation: 'inkPulse 1.4s ease-in-out infinite', display: 'inline-block',
                  }} />
                  <span style={{ color: 'var(--accent)', letterSpacing: '0.2em' }}>
                    {jarvisSpeaking ? 'Speaking' : 'Listening'}
                  </span>
                </span>
              ) : 'memory · present'}
            </div>
            {voiceError && (
              <div style={{ fontFamily: 'var(--sans)', fontSize: 9, color: '#ef4444', textAlign: 'center', maxWidth: 280, letterSpacing: '0.05em' }}>
                {voiceError}
              </div>
            )}
            {onboardingComplete === false && !voiceMode && (
              <div className="onboarding-pulse" style={{ fontFamily: 'var(--sans)', fontSize: 9, letterSpacing: '0.2em', textTransform: 'uppercase', color: 'var(--accent)', opacity: 0.6 }}>
                Getting to know you…
              </div>
            )}
            <ProactiveBanner
              hint={proactiveHint}
              onAct={() => setProactiveHint(null)}
              onDismiss={() => setProactiveHint(null)}
            />
          </div>

          {/* right: conversation */}
          <div style={{ gridArea: 'conv', display: 'flex', flexDirection: 'column', minHeight: 0, borderLeft: '1px solid var(--line)' }}>
            <Conversation messages={messages} loading={loading} onRetry={handleRetry} />
          </div>

          {/* input */}
          <div style={{ gridArea: 'input', borderLeft: '1px solid var(--line)', borderTop: '1px solid var(--line)' }}>
            <InputBar
              orbState={orbState}
              input={input}
              setInput={setInput}
              onSend={sendMessage}
              onMicClick={toggleVoiceMode}
              voiceMode={voiceMode}
              voiceConnecting={voiceConnecting}
              loading={loading || isStreaming}
              disabled={!userId}
              fileInputRef={fileInputRef}
              uploadingFile={uploadingFile}
              onFileSelect={handleFileSelect}
              pendingFiles={pendingFiles}
              onRemoveFile={(id) => setPendingFiles(prev => prev.filter(f => f.id !== id))}
              pastedImage={pastedImage}
              onPastedImageChange={setPastedImage}
            />
          </div>
        </div>

      )}
      </div>
    </>
  )
}
