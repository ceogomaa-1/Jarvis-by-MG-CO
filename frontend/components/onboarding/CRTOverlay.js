'use client'
import { useEffect, useRef } from 'react'

const GRAIN_DIM = 64

// Scanlines + animated film grain + vignette, layered over a scene.
// Pure visual texture — pointer-events: none throughout.
export default function CRTOverlay({ reducedMotion, zIndex = 5 }) {
  const grainRef = useRef(null)

  useEffect(() => {
    if (reducedMotion) return undefined
    const canvas = grainRef.current
    const ctx = canvas.getContext('2d')
    canvas.width = GRAIN_DIM
    canvas.height = GRAIN_DIM
    const imageData = ctx.createImageData(GRAIN_DIM, GRAIN_DIM)

    let cancelled = false
    let timer = null

    function draw() {
      if (cancelled) return
      const buf = imageData.data
      for (let i = 0; i < buf.length; i += 4) {
        const v = Math.random() * 255
        buf[i] = v
        buf[i + 1] = v
        buf[i + 2] = v
        buf[i + 3] = 255
      }
      ctx.putImageData(imageData, 0, 0)
      timer = setTimeout(draw, 80)
    }
    draw()

    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
  }, [reducedMotion])

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex, pointerEvents: 'none' }}>
      {/* Scanlines */}
      <div
        style={{
          position: 'absolute', inset: 0,
          backgroundImage: 'repeating-linear-gradient(to bottom, rgba(255,255,255,0.03) 0px, rgba(255,255,255,0.03) 1px, transparent 1px, transparent 3px)',
        }}
      />
      {/* Vignette */}
      <div
        style={{
          position: 'absolute', inset: 0,
          background: 'radial-gradient(ellipse at center, transparent 55%, rgba(0,0,0,0.4) 100%)',
          opacity: 0.4,
        }}
      />
      {/* Animated grain */}
      {!reducedMotion && (
        <canvas
          ref={grainRef}
          style={{
            position: 'absolute', inset: 0, width: '100%', height: '100%',
            imageRendering: 'pixelated', opacity: 0.04, mixBlendMode: 'overlay',
          }}
        />
      )}
    </div>
  )
}
