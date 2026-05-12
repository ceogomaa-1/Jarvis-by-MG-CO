'use client'

import { useState, useEffect, useRef } from 'react'

const BACKEND = 'https://jarvis-backend-4oz6.onrender.com'

const OPENING_MESSAGE = {
  id: 0,
  role: 'assistant',
  content:
    "I'm Jarvis. Before I'm actually useful to you, I need to know you — not through a form, through a conversation. What's the one thing taking up the most space in your head right now?",
}

function getUserId() {
  let id = localStorage.getItem('jarvis_user_id')
  if (!id) {
    id = 'user_' + crypto.randomUUID().replace(/-/g, '').slice(0, 8)
    localStorage.setItem('jarvis_user_id', id)
  }
  return id
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
      <div style={{ fontFamily: 'var(--display)', fontSize: 22, letterSpacing: '0.55em', paddingLeft: '0.55em', color: 'var(--ink)', fontWeight: 400 }}>
        JARVIS
      </div>
      <div style={{ fontFamily: 'var(--sans)', fontSize: 9, letterSpacing: '0.4em', paddingLeft: '0.4em', color: 'var(--ink-mute)', textTransform: 'uppercase', fontWeight: 400 }}>
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

  const Section = ({ title, items }) => {
    if (!items || items.length === 0) return null
    return (
      <div style={{ marginBottom: '1.25rem' }}>
        <p style={{ fontFamily: 'var(--sans)', color: 'var(--accent)', fontSize: '0.6rem', letterSpacing: '0.15em', textTransform: 'uppercase', opacity: 0.6, margin: '0 0 0.5rem' }}>{title}</p>
        {items.map((item, i) => (
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
    id.name && `Name: ${id.name}`,
    id.preferred_name && id.preferred_name !== id.name && `Goes by: ${id.preferred_name}`,
    id.role && `Role: ${id.role}`,
    id.company && `Company: ${id.company}`,
    id.location && `Based in: ${id.location}`,
  ].filter(Boolean)

  const trustLabel = relationship.trust_level
    ? `${relationship.trust_level} (${relationship.interaction_count || 0} interactions)`
    : null

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

function Message({ msg, isLatest }) {
  if (msg.role === 'user') {
    return (
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 14, opacity: isLatest ? 1 : 0.78, transition: 'opacity 600ms ease' }}>
        <div style={{
          maxWidth: '72%', padding: '12px 18px',
          borderRadius: '20px 20px 4px 20px',
          background: 'var(--user-bubble)',
          border: '1px solid rgba(255,144,114,0.18)',
          color: 'rgba(243,234,217,0.92)',
          fontSize: 15.5, lineHeight: 1.5, fontWeight: 300, letterSpacing: 0.1,
          backdropFilter: 'blur(8px)',
          fontFamily: 'var(--sans)',
        }}>
          {msg.content}
        </div>
      </div>
    )
  }

  return (
    <div style={{ marginBottom: 22, maxWidth: '78%', opacity: isLatest ? 1 : 0.72, transition: 'opacity 600ms ease' }}>
      {msg.proactive && (
        <div style={{ fontFamily: 'var(--sans)', fontSize: 9, letterSpacing: '0.35em', textTransform: 'uppercase', color: 'var(--accent)', marginBottom: 8, fontWeight: 500 }}>
          Proactive · just now
        </div>
      )}
      <div style={{ fontFamily: 'var(--serif)', fontSize: 22, lineHeight: 1.35, fontWeight: 400, color: 'var(--ink)', letterSpacing: 0.2 }}>
        {msg.content}
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

function Conversation({ messages, loading }) {
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
            <Message msg={m} isLatest={i === messages.length - 1 && !loading} />
          </div>
        ))}
        {loading && <ThinkingIndicator />}
      </div>
    </div>
  )
}

// ─── Input bar ────────────────────────────────────────────────────────────────

function InputBar({ orbState, input, setInput, onSend, onMic, loading, disabled }) {
  const isListening = orbState === 'listening'

  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      onSend()
    }
  }

  return (
    <div style={{ padding: '20px 40px 32px', display: 'flex', justifyContent: 'center' }}>
      <div style={{
        width: '100%', maxWidth: 720,
        display: 'flex', alignItems: 'center', gap: 14,
        padding: '14px 18px',
        background: isListening ? 'rgba(255,144,114,0.06)' : 'rgba(243,234,217,0.035)',
        border: `1px solid ${isListening ? 'rgba(255,144,114,0.45)' : 'var(--line)'}`,
        borderRadius: 999, backdropFilter: 'blur(10px)',
        transition: 'border-color 300ms ease, background 300ms ease',
      }}>
        <button onClick={onMic} aria-label="microphone" style={{
          width: 36, height: 36, borderRadius: 999, flexShrink: 0,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: isListening ? 'var(--accent)' : 'rgba(243,234,217,0.07)',
          border: '1px solid rgba(243,234,217,0.12)',
          color: isListening ? '#1a0e08' : 'var(--ink-soft)',
          cursor: 'pointer', transition: 'all 250ms ease',
          boxShadow: isListening ? '0 0 24px rgba(255,144,114,0.6)' : 'none',
        }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="9" y="3" width="6" height="12" rx="3" />
            <path d="M5 11a7 7 0 0 0 14 0" />
            <line x1="12" y1="18" x2="12" y2="22" />
          </svg>
        </button>
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKey}
          placeholder={isListening ? 'Listening…' : 'Say something to Jarvis'}
          disabled={disabled || loading}
          style={{
            flex: 1, background: 'transparent', border: 0, outline: 'none',
            color: 'var(--ink)', fontFamily: 'var(--serif)', fontSize: 18,
            fontWeight: 300, letterSpacing: 0.2,
          }}
        />
        <button
          onClick={onSend}
          disabled={!input.trim() || loading || disabled}
          aria-label="send"
          style={{
            width: 36, height: 36, borderRadius: 999, flexShrink: 0,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: input.trim() && !loading ? 'var(--accent)' : 'rgba(243,234,217,0.07)',
            border: 0, color: input.trim() && !loading ? '#1a0e08' : 'var(--ink-mute)',
            cursor: input.trim() && !loading ? 'pointer' : 'default',
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

// ─── Main ─────────────────────────────────────────────────────────────────────

function captionFor(s) {
  if (s === 'listening') return '“…I’m here. Take your time.”'
  if (s === 'speaking')  return ''
  if (s === 'thinking')  return '“Thinking.”'
  return '“I’ll be here when you need me.”'
}

export default function Home() {
  const [showIntro, setShowIntro]         = useState(true)
  const [messages, setMessages]           = useState([OPENING_MESSAGE])
  const [input, setInput]                 = useState('')
  const [loading, setLoading]             = useState(false)
  const [userId, setUserId]               = useState(null)
  const [onboardingComplete, setOnboarding] = useState(null)
  const [showPanel, setShowPanel]         = useState(false)
  const [micOn, setMicOn]                 = useState(false)
  const [proactiveHint, setProactiveHint] = useState(null)
  const msgIdRef = useRef(1)

  useEffect(() => { setUserId(getUserId()) }, [])

  useEffect(() => {
    if (!userId) return
    fetch(`${BACKEND}/api/user/onboarding-status/${userId}`)
      .then(r => r.json())
      .then(d => setOnboarding(d.onboarding_complete))
      .catch(() => setOnboarding(true))
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

  const lastMsg = messages[messages.length - 1]
  const isStreaming = lastMsg?.streaming === true
  const orbState =
    micOn && !loading && !isStreaming ? 'listening' :
    loading     ? 'thinking' :
    isStreaming  ? 'speaking' :
    'idle'

  async function sendMessage() {
    const text = input.trim()
    if (!text || loading || isStreaming) return
    setInput('')
    setMicOn(false)

    const historyForApi = messages.slice(1).map(({ role, content }) => ({ role, content }))
    msgIdRef.current += 1
    const userMsgId = msgIdRef.current
    setMessages(prev => [...prev, { id: userMsgId, role: 'user', content: text }])
    setLoading(true)

    let streamMsgId = null
    try {
      const res = await fetch(`${BACKEND}/api/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, message: text, conversation_history: historyForApi }),
      })
      if (!res.ok) throw new Error(`${res.status}`)

      msgIdRef.current += 1
      streamMsgId = msgIdRef.current
      setMessages(prev => [...prev, { id: streamMsgId, role: 'assistant', content: '', streaming: true }])
      setLoading(false)

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let accumulated = ''
      let done = false

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
            done = true
            break
          }
          if (raw === '[ERROR]') {
            setMessages(prev => prev.filter(m => m.id !== streamMsgId))
            done = true
            break
          }
          try {
            const chunk = JSON.parse(raw)
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
    } catch {
      setMessages(prev => {
        let msgs = prev.filter(m => m.id !== userMsgId)
        if (streamMsgId) msgs = msgs.filter(m => m.id !== streamMsgId)
        return msgs
      })
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      {showIntro && <IntroSplash onDone={() => setShowIntro(false)} />}
      {showPanel && userId && <KnowledgePanel userId={userId} onClose={() => setShowPanel(false)} />}

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

      {/* Layout */}
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
          </div>
        </div>

        {/* left: orb panel */}
        <div style={{
          gridArea: 'orb', position: 'relative',
          display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center',
          gap: 28, padding: '0 20px 40px',
        }}>
          <div style={{ animation: 'softFloat 6s ease-in-out infinite' }}>
            <Orb state={orbState} orbStyle="aurora" accent="#ff9072" size={340} />
          </div>
          <div style={{
            fontFamily: 'var(--serif)', fontStyle: 'italic', fontSize: 17,
            color: 'var(--ink-soft)', fontWeight: 300, textAlign: 'center',
            maxWidth: 320, lineHeight: 1.45, minHeight: 48,
          }}>
            {captionFor(orbState)}
          </div>
          <div style={{ fontFamily: 'var(--sans)', fontSize: 9, letterSpacing: '0.38em', textTransform: 'uppercase', color: 'var(--ink-mute)' }}>
            memory · present
          </div>
          {onboardingComplete === false && (
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
          <Conversation messages={messages} loading={loading} />
        </div>

        {/* input */}
        <div style={{ gridArea: 'input', borderLeft: '1px solid var(--line)', borderTop: '1px solid var(--line)' }}>
          <InputBar
            orbState={orbState}
            input={input}
            setInput={setInput}
            onSend={sendMessage}
            onMic={() => setMicOn(v => !v)}
            loading={loading || isStreaming}
            disabled={!userId}
          />
        </div>
      </div>
    </>
  )
}
