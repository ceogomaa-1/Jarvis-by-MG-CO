'use client'
import { motion, AnimatePresence } from 'framer-motion'
import Image from 'next/image'

export default function JarvisAvatar({ size = 80, isStreaming = false }) {
  return (
    <div style={{ position: 'relative', width: size, height: size, overflow: 'visible', flexShrink: 0 }}>
      {/* Warm glow */}
      <motion.div
        style={{
          position: 'absolute', inset: 0,
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(200,75,49,0.15) 0%, transparent 70%)',
          filter: 'blur(20px)',
          transform: 'scale(2.5)',
          zIndex: 0, pointerEvents: 'none',
        }}
        animate={{ opacity: isStreaming ? [0.5, 1.0, 0.5] : [0.4, 0.7, 0.4] }}
        transition={{ duration: isStreaming ? 1.5 : 4, repeat: Infinity, ease: 'easeInOut' }}
      />

      {/* Expanding ripple — streaming only */}
      <AnimatePresence>
        {isStreaming && (
          <motion.div
            key="ripple"
            initial={{ scale: 1, opacity: 0.4 }}
            animate={{ scale: 2.5, opacity: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 2, repeat: Infinity, ease: 'easeOut' }}
            style={{
              position: 'absolute', inset: 0,
              borderRadius: '50%',
              border: '1px solid rgba(200,75,49,0.2)',
              zIndex: 0, pointerEvents: 'none',
            }}
          />
        )}
      </AnimatePresence>

      {/* Orbital dot ring */}
      <svg
        style={{
          position: 'absolute', inset: 0,
          width: '100%', height: '100%',
          overflow: 'visible',
          transform: 'scale(2.2)', transformOrigin: 'center',
          zIndex: 0, pointerEvents: 'none',
        }}
        viewBox="0 0 120 120"
      >
        <motion.g
          animate={{ rotate: 360 }}
          transition={{ duration: isStreaming ? 6 : 20, repeat: Infinity, ease: 'linear' }}
          style={{ transformOrigin: '60px 60px' }}
        >
          {[...Array(8)].map((_, i) => {
            const angle = (Math.PI * 2 * i) / 8
            const cx = 60 + Math.cos(angle) * 50
            const cy = 60 + Math.sin(angle) * 50
            return (
              <circle
                key={i}
                cx={cx} cy={cy} r={1.2}
                fill="#f3ead9"
                opacity={0.15 + (i % 3) * 0.05}
              />
            )
          })}
        </motion.g>
      </svg>

      {/* Logo — breathes with the glow */}
      <motion.div
        style={{ position: 'relative', zIndex: 1 }}
        animate={{ scale: isStreaming ? [1, 1.06, 1] : [1, 1.03, 1] }}
        transition={{ duration: isStreaming ? 1.5 : 4, repeat: Infinity, ease: 'easeInOut' }}
      >
        <Image
          src="/logo-transparent.png"
          width={size}
          height={size}
          alt="Jarvis"
          style={{ objectFit: 'contain' }}
          priority
        />
      </motion.div>
    </div>
  )
}
