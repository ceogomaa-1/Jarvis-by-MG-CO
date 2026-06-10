'use client'
import { useEffect, useRef } from 'react'

// Single full-screen canvas particle engine for the OS1 cinematic.
// State machine: assemble -> hold -> burst -> reassemble. Particles persist
// across all transitions (never destroyed/recreated) so the cinematic reads
// as one continuous shot.

const PARTICLE_COLOR = '#9a9a9a'
const ACCENT_COLOR = '#2d7ff9'
const ACCENT_FRACTION = 0.08
const SAMPLE_DIM = 256
const SAMPLE_GRID = 4
const DESKTOP_TARGET = 1800
const MOBILE_TARGET = 600
const SPRING = 0.06
const ROT_SPEED = (5 * Math.PI / 180) / (8 * 60) // ~5deg drift over ~8s @60fps

const STAR_LAYERS = [
  { count: 60, speed: 0.04, opacity: 0.08, parallax: 2 },
  { count: 40, speed: 0.09, opacity: 0.15, parallax: 4 },
  { count: 20, speed: 0.16, opacity: 0.25, parallax: 6 },
]

function shuffle(arr) {
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[arr[i], arr[j]] = [arr[j], arr[i]]
  }
  return arr
}

export default function ParticleField({ state, reducedMotion, mobile }) {
  const canvasRef = useRef(null)
  const stateRef = useRef(state)

  useEffect(() => { stateRef.current = state }, [state])

  useEffect(() => {
    if (reducedMotion) return undefined

    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')

    let width = 0
    let height = 0
    let dpr = 1
    let centerX = 0
    let centerY = 0
    let logoSize = 0
    let particles = []
    let stars = STAR_LAYERS.map(l => ({
      ...l,
      dots: Array.from({ length: l.count }, () => ({ x: Math.random(), y: Math.random() })),
    }))
    const mouse = { x: 0, y: 0 }
    const angle = { current: 0 }
    let prevState = state
    let rafId = null
    let cancelled = false

    function applyTargets() {
      logoSize = Math.max(160, Math.min(320, Math.min(width, height) * 0.42))
      for (const p of particles) {
        p.targetX = centerX + p.nx * logoSize
        p.targetY = centerY + p.ny * logoSize
      }
    }

    function resize() {
      dpr = Math.min(window.devicePixelRatio || 1, 2)
      width = window.innerWidth
      height = window.innerHeight
      canvas.width = width * dpr
      canvas.height = height * dpr
      canvas.style.width = width + 'px'
      canvas.style.height = height + 'px'
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      centerX = width / 2
      centerY = height / 2
      if (particles.length) applyTargets()
    }

    function spawnFromEdge() {
      const edge = Math.floor(Math.random() * 4)
      if (edge === 0) return { x: Math.random() * width, y: -10 }
      if (edge === 1) return { x: width + 10, y: Math.random() * height }
      if (edge === 2) return { x: Math.random() * width, y: height + 10 }
      return { x: -10, y: Math.random() * height }
    }

    function buildParticles(samples) {
      particles = samples.map(s => {
        const start = spawnFromEdge()
        return {
          nx: s.nx,
          ny: s.ny,
          x: start.x,
          y: start.y,
          vx: 0,
          vy: 0,
          targetX: 0,
          targetY: 0,
          isAccent: Math.random() < ACCENT_FRACTION,
          jitterPhase: Math.random() * Math.PI * 2,
          jitterFreq: 0.5 + Math.random() * 1.5,
        }
      })
      applyTargets()
    }

    function drawStars() {
      for (const layer of stars) {
        ctx.fillStyle = `rgba(163,163,163,${layer.opacity})`
        const px = mouse.x * layer.parallax
        const py = mouse.y * layer.parallax
        for (const d of layer.dots) {
          d.y += layer.speed / height
          if (d.y > 1) d.y -= 1
          ctx.fillRect(d.x * width + px, d.y * height + py, 1, 1)
        }
      }
    }

    function frame(now) {
      if (cancelled) return
      const t = now / 1000
      const st = stateRef.current

      if (st === 'burst' && prevState !== 'burst') {
        for (const p of particles) {
          const dx = p.x - centerX
          const dy = p.y - centerY
          const dist = Math.hypot(dx, dy) || 1
          const speed = 2 + Math.random() * 5
          p.vx = (dx / dist) * speed + (Math.random() - 0.5)
          p.vy = (dy / dist) * speed + (Math.random() - 0.5)
        }
      }
      prevState = st

      if (st === 'hold') angle.current += ROT_SPEED
      else if (st === 'reassemble') angle.current *= 0.98

      ctx.clearRect(0, 0, width, height)
      drawStars()

      const cos = Math.cos(angle.current)
      const sin = Math.sin(angle.current)

      for (const p of particles) {
        if (st === 'burst') {
          p.x += p.vx
          p.y += p.vy
          p.vx *= 0.985
          p.vy *= 0.985
          continue
        }

        let tx = p.targetX
        let ty = p.targetY
        if (angle.current !== 0) {
          const dx = tx - centerX
          const dy = ty - centerY
          tx = centerX + dx * cos - dy * sin
          ty = centerY + dx * sin + dy * cos
        }
        if (st === 'hold') {
          tx += Math.sin(t * p.jitterFreq + p.jitterPhase) * 1
          ty += Math.cos(t * p.jitterFreq * 1.3 + p.jitterPhase) * 1
        }
        p.x += (tx - p.x) * SPRING
        p.y += (ty - p.y) * SPRING
        if (st === 'assemble') {
          p.x += Math.sin(t * 3 + p.jitterPhase) * 0.3
          p.y += Math.cos(t * 3 + p.jitterPhase) * 0.3
        }
      }

      ctx.fillStyle = PARTICLE_COLOR
      for (const p of particles) {
        if (!p.isAccent) ctx.fillRect(p.x - 1, p.y - 1, 2, 2)
      }
      ctx.fillStyle = ACCENT_COLOR
      for (const p of particles) {
        if (p.isAccent) ctx.fillRect(p.x - 1, p.y - 1, 2, 2)
      }

      rafId = requestAnimationFrame(frame)
    }

    function onMouseMove(e) {
      mouse.x = (e.clientX / window.innerWidth - 0.5) * 2
      mouse.y = (e.clientY / window.innerHeight - 0.5) * 2
    }

    resize()
    window.addEventListener('resize', resize)
    if (!mobile) window.addEventListener('mousemove', onMouseMove)

    const target = mobile ? MOBILE_TARGET : DESKTOP_TARGET
    const img = new Image()
    img.onload = () => {
      if (cancelled) return
      const off = document.createElement('canvas')
      off.width = SAMPLE_DIM
      off.height = SAMPLE_DIM
      const offCtx = off.getContext('2d')
      offCtx.drawImage(img, 0, 0, SAMPLE_DIM, SAMPLE_DIM)
      const data = offCtx.getImageData(0, 0, SAMPLE_DIM, SAMPLE_DIM).data
      const candidates = []
      for (let y = 0; y < SAMPLE_DIM; y += SAMPLE_GRID) {
        for (let x = 0; x < SAMPLE_DIM; x += SAMPLE_GRID) {
          const idx = (y * SAMPLE_DIM + x) * 4
          if (data[idx + 3] > 128) {
            candidates.push({ nx: (x - SAMPLE_DIM / 2) / SAMPLE_DIM, ny: (y - SAMPLE_DIM / 2) / SAMPLE_DIM })
          }
        }
      }
      shuffle(candidates)
      buildParticles(candidates.slice(0, Math.min(candidates.length, target)))
    }
    img.src = '/jarvis-logo-mono.png'

    rafId = requestAnimationFrame(frame)

    return () => {
      cancelled = true
      if (rafId) cancelAnimationFrame(rafId)
      window.removeEventListener('resize', resize)
      if (!mobile) window.removeEventListener('mousemove', onMouseMove)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reducedMotion, mobile])

  if (reducedMotion) return null

  return (
    <canvas
      ref={canvasRef}
      style={{ position: 'absolute', inset: 0, zIndex: 0, pointerEvents: 'none' }}
    />
  )
}
