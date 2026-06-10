'use client'
import { motion, AnimatePresence } from 'framer-motion'
import Image from 'next/image'

// OS1 v2 — monochrome pixel globe. Subtle white glow, no color.
export default function JarvisAvatar({ size = 80, isStreaming = false }) {
  return (
    <div style={{ position: 'relative', width: size, height: size, overflow: 'visible', flexShrink: 0 }}>
      {/* Soft monochrome glow */}
      <motion.div
        style={{
          position: 'absolute', inset: 0,
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(255,255,255,0.07) 0%, transparent 70%)',
          filter: 'blur(18px)',
          transform: 'scale(2.2)',
          zIndex: 0, pointerEvents: 'none',
        }}
        animate={{ opacity: isStreaming ? [0.5, 1.0, 0.5] : [0.3, 0.55, 0.3] }}
        transition={{ duration: isStreaming ? 1.5 : 4, repeat: Infinity, ease: 'easeInOut' }}
      />

      {/* Expanding ripple — streaming only */}
      <AnimatePresence>
        {isStreaming && (
          <motion.div
            key="ripple"
            initial={{ scale: 1, opacity: 0.35 }}
            animate={{ scale: 2.4, opacity: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 2, repeat: Infinity, ease: 'easeOut' }}
            style={{
              position: 'absolute', inset: 0,
              borderRadius: '50%',
              border: '1px solid rgba(255,255,255,0.18)',
              zIndex: 0, pointerEvents: 'none',
            }}
          />
        )}
      </AnimatePresence>

      {/* Logo — breathes gently */}
      <motion.div
        style={{ position: 'relative', zIndex: 1 }}
        animate={{ scale: isStreaming ? [1, 1.05, 1] : [1, 1.02, 1] }}
        transition={{ duration: isStreaming ? 1.5 : 4, repeat: Infinity, ease: 'easeInOut' }}
      >
        <Image
          src="/jarvis-logo-mono.png"
          width={size}
          height={size}
          alt="Jarvis"
          className="os1-logo-pixel"
          style={{ objectFit: 'contain', opacity: 0.62 }}
          priority
        />
      </motion.div>
    </div>
  )
}
