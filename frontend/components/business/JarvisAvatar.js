'use client'
import { motion, AnimatePresence } from 'framer-motion'

// Batch 72 "Private Office" — the presence. The pixel globe image is replaced
// by a pure-CSS aura: a warm copper-lit sphere inside a slowly turning hairline
// ring. Same props (size / isStreaming) so every call site upgrades in place.
export default function JarvisAvatar({ size = 80, isStreaming = false }) {
  return (
    <div style={{ position: 'relative', width: size, height: size, overflow: 'visible', flexShrink: 0 }}>
      {/* Wide ambient glow */}
      <motion.div
        style={{
          position: 'absolute', inset: 0,
          borderRadius: '50%',
          background: 'radial-gradient(circle, var(--os1-glow, rgba(207,138,91,0.25)) 0%, transparent 68%)',
          filter: 'blur(16px)',
          transform: 'scale(2.1)',
          zIndex: 0, pointerEvents: 'none',
        }}
        animate={{ opacity: isStreaming ? [0.45, 0.9, 0.45] : [0.22, 0.42, 0.22] }}
        transition={{ duration: isStreaming ? 1.6 : 5, repeat: Infinity, ease: 'easeInOut' }}
      />

      {/* Expanding ripple — streaming only */}
      <AnimatePresence>
        {isStreaming && (
          <motion.div
            key="ripple"
            initial={{ scale: 1, opacity: 0.4 }}
            animate={{ scale: 2.3, opacity: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 2, repeat: Infinity, ease: 'easeOut' }}
            style={{
              position: 'absolute', inset: 0,
              borderRadius: '50%',
              border: '1px solid rgba(207,138,91,0.35)',
              zIndex: 0, pointerEvents: 'none',
            }}
          />
        )}
      </AnimatePresence>

      {/* Orbiting hairline ring with a single bright point */}
      <div
        style={{
          position: 'absolute', inset: -Math.max(4, size * 0.09),
          borderRadius: '50%',
          border: '1px solid rgba(237,230,216,0.1)',
          zIndex: 1, pointerEvents: 'none',
          animation: `os1ArcSpin ${isStreaming ? '3.5s' : '14s'} linear infinite`,
        }}
      >
        <div style={{
          position: 'absolute', top: -1.5, left: '50%', marginLeft: -1.5,
          width: 3, height: 3, borderRadius: '50%',
          background: 'var(--os1-accent, #cf8a5b)',
          boxShadow: '0 0 8px var(--os1-glow, rgba(207,138,91,0.25))',
        }} />
      </div>

      {/* The sphere — warm-lit from the upper left, breathing gently */}
      <motion.div
        style={{
          position: 'absolute', inset: size * 0.08,
          borderRadius: '50%',
          background: `
            radial-gradient(circle at 32% 28%, rgba(255, 214, 178, 0.32), transparent 46%),
            radial-gradient(circle at 68% 78%, rgba(207, 138, 91, 0.22), transparent 52%),
            radial-gradient(circle at 50% 50%, #241e18 0%, #14100c 78%)
          `,
          border: '1px solid rgba(237,230,216,0.12)',
          boxShadow: 'inset 0 1px 1px rgba(255,255,255,0.09), 0 10px 30px -12px rgba(0,0,0,0.8)',
          zIndex: 2,
        }}
        animate={{ scale: isStreaming ? [1, 1.05, 1] : [1, 1.02, 1] }}
        transition={{ duration: isStreaming ? 1.6 : 5, repeat: Infinity, ease: 'easeInOut' }}
      />
    </div>
  )
}
