'use client'

import React, { memo, useCallback, useRef, useState, useEffect } from 'react'

// ---------------------------------------------------------------------------
// Rue chat bar effects — port of 21st.dev "prompt-input-dynamic-grow" visual
// layers (glow border, cursor-following gradient, click ripples), recolored
// from purple/pink/blue to the Rue warm palette (coral --accent + cream ink).
// The bar chrome itself lives in app/page.js (InputBar); these are the
// decorative layers + the interaction hook that drives them.
// ---------------------------------------------------------------------------

let stylesInjected = false

const RUE_GLOW_KEYFRAMES = `
  @keyframes rueRipple {
    0%   { transform: scale(0);   opacity: 0.55; }
    100% { transform: scale(2.4); opacity: 0; }
  }
`

function injectKeyframes() {
  if (typeof window === 'undefined' || stylesInjected) return
  stylesInjected = true
  const style = document.createElement('style')
  style.innerHTML = RUE_GLOW_KEYFRAMES
  document.head.appendChild(style)
}

// Tracks hover position (throttled) and click ripples for the bar container.
export function useRueBarFx() {
  const containerRef = useRef(null)
  const throttleRef = useRef(null)
  const [mouse, setMouse] = useState({ x: 50, y: 50 })
  const [ripples, setRipples] = useState([])

  useEffect(() => {
    injectKeyframes()
    return () => {
      if (throttleRef.current) clearTimeout(throttleRef.current)
    }
  }, [])

  const handleMouseMove = useCallback((e) => {
    if (containerRef.current && !throttleRef.current) {
      const { clientX, clientY } = e
      throttleRef.current = window.setTimeout(() => {
        const rect = containerRef.current?.getBoundingClientRect()
        if (rect) {
          setMouse({
            x: ((clientX - rect.left) / rect.width) * 100,
            y: ((clientY - rect.top) / rect.height) * 100,
          })
        }
        throttleRef.current = null
      }, 50)
    }
  }, [])

  const handleClick = useCallback((e) => {
    const rect = containerRef.current?.getBoundingClientRect()
    if (!rect) return
    const ripple = { x: e.clientX - rect.left, y: e.clientY - rect.top, id: Date.now() }
    setRipples((prev) => (prev.length < 5 ? [...prev, ripple] : prev))
    setTimeout(() => {
      setRipples((prev) => prev.filter((r) => r.id !== ripple.id))
    }, 600)
  }, [])

  return { containerRef, mouse, ripples, handleMouseMove, handleClick }
}

export const RueGlowEffects = memo(function RueGlowEffects({ active, mouse, intensity = 0.5 }) {
  return (
    <>
      {/* liquid-glass sheen */}
      <div
        style={{
          position: 'absolute', inset: 0, borderRadius: 24, pointerEvents: 'none',
          background:
            'linear-gradient(90deg, rgba(243,234,217,0.02) 0%, rgba(243,234,217,0.05) 50%, rgba(243,234,217,0.02) 100%)',
        }}
      />
      {/* outside border glow (hover / focus) */}
      <div
        style={{
          position: 'absolute', inset: 0, borderRadius: 24, pointerEvents: 'none',
          opacity: active ? 1 : 0,
          transition: 'opacity 500ms ease',
          boxShadow: `
            0 0 0 1px rgba(255,144,114,${0.22 * intensity}),
            0 0 10px rgba(255,144,114,${0.3 * intensity}),
            0 0 22px rgba(255,144,114,${0.16 * intensity}),
            0 0 36px rgba(243,234,217,${0.08 * intensity})
          `,
          filter: 'blur(0.5px)',
        }}
      />
      {/* cursor-following warm gradient */}
      <div
        style={{
          position: 'absolute', inset: 0, borderRadius: 24, pointerEvents: 'none',
          opacity: active ? 0.35 : 0,
          transition: 'opacity 300ms ease',
          filter: 'blur(2px)',
          background: `radial-gradient(circle 140px at ${mouse.x}% ${mouse.y}%, rgba(255,144,114,0.12) 0%, rgba(255,196,150,0.06) 40%, rgba(243,234,217,0.04) 70%, transparent 100%)`,
        }}
      />
    </>
  )
})

export const RueRipples = memo(function RueRipples({ ripples }) {
  if (!ripples || ripples.length === 0) return null
  return (
    <div
      style={{
        position: 'absolute', inset: 0, borderRadius: 24,
        overflow: 'hidden', pointerEvents: 'none',
      }}
    >
      {ripples.map((r) => (
        <div
          key={r.id}
          style={{
            position: 'absolute',
            left: r.x - 25, top: r.y - 25,
            width: 50, height: 50, borderRadius: '50%',
            background:
              'radial-gradient(circle, rgba(255,144,114,0.18) 0%, rgba(255,196,150,0.10) 50%, rgba(243,234,217,0.06) 100%)',
            filter: 'blur(3px)',
            animation: 'rueRipple 600ms ease-out forwards',
          }}
        />
      ))}
    </div>
  )
})
