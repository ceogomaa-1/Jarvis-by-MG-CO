'use client'
import { motion, AnimatePresence } from 'framer-motion'
import Image from 'next/image'

// Batch 72 "Crimson Terminal" — the presence is the BRAND PLANET itself
// (public/logo-transparent.png), floating in the void with its neon halo.
// Same props (size / isStreaming) so every call site upgrades in place.
export default function JarvisAvatar({ size = 80, isStreaming = false }) {
  return (
    <div style={{ position: 'relative', width: size, height: size, overflow: 'visible', flexShrink: 0 }}>
      {/* Wide neon halo */}
      <motion.div
        style={{
          position: 'absolute', inset: 0,
          borderRadius: '50%',
          background: 'radial-gradient(circle, var(--os1-glow, rgba(255,46,81,0.35)) 0%, transparent 66%)',
          filter: 'blur(18px)',
          transform: 'scale(2.05)',
          zIndex: 0, pointerEvents: 'none',
        }}
        animate={{ opacity: isStreaming ? [0.55, 1, 0.55] : [0.3, 0.55, 0.3] }}
        transition={{ duration: isStreaming ? 1.6 : 4.5, repeat: Infinity, ease: 'easeInOut' }}
      />

      {/* Expanding ripple — streaming only */}
      <AnimatePresence>
        {isStreaming && (
          <motion.div
            key="ripple"
            initial={{ scale: 1, opacity: 0.45 }}
            animate={{ scale: 2.3, opacity: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 2, repeat: Infinity, ease: 'easeOut' }}
            style={{
              position: 'absolute', inset: 0,
              borderRadius: '50%',
              border: '1px solid rgba(255,46,81,0.45)',
              zIndex: 0, pointerEvents: 'none',
            }}
          />
        )}
      </AnimatePresence>

      {/* Orbiting hairline ring with a single bright point */}
      <div
        style={{
          position: 'absolute', inset: -Math.max(4, size * 0.1),
          borderRadius: '50%',
          border: '1px solid rgba(255,255,255,0.1)',
          zIndex: 1, pointerEvents: 'none',
          animation: `os1ArcSpin ${isStreaming ? '3.5s' : '14s'} linear infinite`,
        }}
      >
        <div style={{
          position: 'absolute', top: -1.5, left: '50%', marginLeft: -1.5,
          width: 3, height: 3, borderRadius: '50%',
          background: 'var(--os1-accent, #ff2e51)',
          boxShadow: '0 0 8px var(--os1-glow, rgba(255,46,81,0.35))',
        }} />
      </div>

      {/* The brand planet — breathing, softly lit by its own glow */}
      <motion.div
        style={{ position: 'relative', zIndex: 2, width: '100%', height: '100%' }}
        animate={{ scale: isStreaming ? [1, 1.05, 1] : [1, 1.02, 1] }}
        transition={{ duration: isStreaming ? 1.6 : 4.5, repeat: Infinity, ease: 'easeInOut' }}
      >
        <Image
          src="/logo-transparent.png"
          width={size}
          height={size}
          alt="Jarvis"
          style={{
            objectFit: 'contain',
            filter: 'drop-shadow(0 0 14px rgba(255,46,81,0.35)) saturate(1.15) brightness(1.05)',
          }}
          priority
        />
      </motion.div>
    </div>
  )
}
