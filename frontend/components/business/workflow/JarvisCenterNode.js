'use client'
import Image from 'next/image'
import { Handle, Position } from '@xyflow/react'

export default function JarvisCenterNode() {
  return (
    <div style={{ position: 'relative', width: 180, height: 180, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      {/* Hidden handles for edge connections */}
      <Handle type="source" position={Position.Top}    style={{ opacity: 0, pointerEvents: 'none' }} />
      <Handle type="source" position={Position.Right}  style={{ opacity: 0, pointerEvents: 'none' }} />
      <Handle type="source" position={Position.Bottom} style={{ opacity: 0, pointerEvents: 'none' }} />
      <Handle type="source" position={Position.Left}   style={{ opacity: 0, pointerEvents: 'none' }} />

      {/* Glow halo */}
      <div style={{
        position: 'absolute',
        width: 280, height: 280,
        borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(207,138,91,0.55) 0%, transparent 70%)',
        animation: 'centerGlowPulse 3s ease-in-out infinite',
        pointerEvents: 'none',
        zIndex: 0,
      }} />

      {/* Particle ring SVG */}
      <svg
        width={240}
        height={240}
        style={{ position: 'absolute', top: -30, left: -30, zIndex: 1, pointerEvents: 'none' }}
      >
        <style>{`
          @keyframes spinCW  { from { transform: rotate(0deg); transform-origin: 120px 120px; } to { transform: rotate(360deg); transform-origin: 120px 120px; } }
          @keyframes spinCCW { from { transform: rotate(0deg); transform-origin: 120px 120px; } to { transform: rotate(-360deg); transform-origin: 120px 120px; } }
          @keyframes centerGlowPulse { 0%,100% { opacity:0.35; } 50% { opacity:0.75; } }
          .ring-cw  { animation: spinCW  18s linear infinite; }
          .ring-ccw { animation: spinCCW 24s linear infinite; }
        `}</style>
        <g className="ring-cw">
          {Array.from({ length: 24 }).map((_, i) => {
            const angle = (2 * Math.PI * i) / 24
            return (
              <circle
                key={i}
                cx={120 + 110 * Math.cos(angle)}
                cy={120 + 110 * Math.sin(angle)}
                r={1.5}
                fill="rgba(236,230,217,0.6)"
              />
            )
          })}
        </g>
        <g className="ring-ccw">
          {Array.from({ length: 16 }).map((_, i) => {
            const angle = (2 * Math.PI * i) / 16
            return (
              <circle
                key={i}
                cx={120 + 95 * Math.cos(angle)}
                cy={120 + 95 * Math.sin(angle)}
                r={1.5}
                fill="rgba(236,230,217,0.4)"
              />
            )
          })}
        </g>
      </svg>

      {/* Logo + wordmark */}
      <div style={{ position: 'relative', zIndex: 2, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8 }}>
        <div style={{
          width: 140, height: 140, borderRadius: '50%',
          background: 'rgba(10,9,8,0.85)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          border: '1px solid rgba(236,230,217,0.1)',
          overflow: 'hidden',
        }}>
          <Image
            src="/logo-os1-mono.png"
            width={110}
            height={110}
            alt="Jarvis OS1"
            priority
            style={{ objectFit: 'contain' }}
          />
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 5 }}>
          <span style={{
            fontFamily: 'var(--pixel)',
            fontSize: 16, color: '#ece6d9',
          }}>
            Jarvis
          </span>
          <span style={{
            fontFamily: 'var(--pixel)',
            fontSize: 11, color: '#cf8a5b',
            letterSpacing: '0.1em',
          }}>
            OS1
          </span>
        </div>
      </div>
    </div>
  )
}
