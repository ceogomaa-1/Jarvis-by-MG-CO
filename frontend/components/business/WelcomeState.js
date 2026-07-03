'use client'
import { motion } from 'framer-motion'
import JarvisAvatar from './JarvisAvatar'

function getGreeting() {
  const h = new Date().getHours()
  if (h >= 5 && h < 12) return 'Good morning.'
  if (h >= 12 && h < 18) return 'Good afternoon.'
  if (h >= 18 && h < 22) return 'Good evening.'
  return 'Working late.'
}

function getDateline() {
  return new Date()
    .toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })
    .toUpperCase()
    .replace(/,/g, '  ·')
}

const reveal = (delay) => ({
  initial: { opacity: 0, y: 18, filter: 'blur(8px)' },
  animate: { opacity: 1, y: 0, filter: 'blur(0px)' },
  transition: { duration: 1.1, ease: [0.16, 1, 0.3, 1], delay },
})

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
      {/* The presence */}
      <motion.div {...reveal(0)} style={{ marginBottom: 40 }}>
        <JarvisAvatar size={88} isStreaming={isStreaming} />
      </motion.div>

      {/* Dateline — machine label */}
      <motion.div {...reveal(0.25)} className="os1-label" style={{ marginBottom: 18 }}>
        {getDateline()}
      </motion.div>

      {/* The greeting — editorial serif, the one focal point */}
      <motion.h1
        {...reveal(0.4)}
        className="os1-display"
        style={{
          margin: 0, lineHeight: 1.04,
          fontSize: 'clamp(46px, 6.5vw, 76px)',
          color: 'var(--os1-text)',
        }}
      >
        {getGreeting()}
      </motion.h1>

      <motion.p
        {...reveal(0.6)}
        style={{
          marginTop: 20, marginBottom: 0,
          fontSize: 15.5,
          color: 'var(--os1-text-dim)',
          letterSpacing: '0.01em',
          fontFamily: 'var(--pixel)',
        }}
      >
        What should we work on?
      </motion.p>

      {/* Hairline grounding the composition */}
      <motion.div
        initial={{ opacity: 0, scaleX: 0 }}
        animate={{ opacity: 1, scaleX: 1 }}
        transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1], delay: 0.85 }}
        style={{
          marginTop: 36, width: 200, height: 1,
          background: 'linear-gradient(to right, transparent, var(--os1-border) 30%, var(--os1-border) 70%, transparent)',
        }}
      />
    </motion.div>
  )
}
