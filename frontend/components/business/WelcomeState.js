'use client'
import { motion } from 'framer-motion'
import JarvisAvatar from './JarvisAvatar'

function getGreeting() {
  const h = new Date().getHours()
  if (h >= 5 && h < 12) return 'Good Morning'
  if (h >= 12 && h < 18) return 'Good Afternoon'
  if (h >= 18 && h < 22) return 'Good Evening'
  return 'Working Late'
}

export default function WelcomeState({ onSuggestion, isStreaming = false }) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0, scale: 0.98 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      style={{
        display: 'flex', flexDirection: 'column', alignItems: 'center',
        justifyContent: 'center', height: '100%', padding: '0 24px 80px',
        textAlign: 'center',
      }}
    >
      {/* Pixel globe logo */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.6, ease: 'easeOut', delay: 0 }}
        style={{ marginBottom: 28 }}
      >
        <JarvisAvatar size={96} isStreaming={isStreaming} />
      </motion.div>

      <motion.h1
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: 'easeOut', delay: 0.15 }}
        className="font-pixel"
        style={{
          margin: 0, lineHeight: 1.1,
          fontSize: 'clamp(40px, 6vw, 62px)',
          fontWeight: 600,
          color: '#f2f2f2',
          letterSpacing: '0.01em',
        }}
      >
        {getGreeting()}
      </motion.h1>

      <motion.p
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: 'easeOut', delay: 0.3 }}
        className="font-pixel"
        style={{
          marginTop: 14, marginBottom: 0,
          fontSize: 17,
          color: 'var(--os1-text-dim)',
          letterSpacing: '0.02em',
        }}
      >
        What should we work on?
      </motion.p>
    </motion.div>
  )
}
