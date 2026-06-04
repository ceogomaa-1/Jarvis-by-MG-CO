'use client'
import { useState } from 'react'
import { motion } from 'framer-motion'
import { PenTool, BarChart3, Lightbulb, Shield } from 'lucide-react'
import JarvisAvatar from './JarvisAvatar'

function getGreeting() {
  const h = new Date().getHours()
  if (h >= 5 && h < 12) return 'Good morning.'
  if (h >= 12 && h < 18) return 'Good afternoon.'
  if (h >= 18 && h < 22) return 'Good evening.'
  return 'Working late.'
}

const SUGGESTIONS = [
  { icon: PenTool, text: 'Draft a sales outreach' },
  { icon: BarChart3, text: 'Analyze my business metrics' },
  { icon: Lightbulb, text: 'Create a marketing strategy' },
  { icon: Shield, text: 'Review my risk flags' },
]

function SuggestionCard({ icon: Icon, text, onClick }) {
  const [hovered, setHovered] = useState(false)
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        background: hovered ? 'rgba(243,234,217,0.06)' : 'rgba(243,234,217,0.03)',
        border: `1px solid ${hovered ? 'rgba(243,234,217,0.1)' : 'rgba(243,234,217,0.06)'}`,
        borderRadius: 16, padding: '18px 16px',
        display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: 8,
        cursor: 'pointer', textAlign: 'left', width: '100%',
        transform: hovered ? 'translateY(-1px)' : 'translateY(0)',
        transition: 'all 300ms cubic-bezier(0.4,0,0.2,1)',
      }}
    >
      <Icon size={20} color="rgba(243,234,217,0.3)" />
      <span className="font-arcade text-[7px] tracking-wider text-[rgba(243,234,217,0.6)]" style={{ lineHeight: 1.6 }}>
        {text}
      </span>
    </button>
  )
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
        justifyContent: 'center', height: '100%', padding: '0 24px 60px',
        textAlign: 'center',
      }}
    >
      {/* Animated logo */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.6, ease: 'easeOut', delay: 0 }}
        style={{ marginBottom: 36 }}
      >
        <JarvisAvatar size={80} isStreaming={isStreaming} />
      </motion.div>

      <motion.h1
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: 'easeOut', delay: 0.2 }}
        className="font-arcade text-2xl md:text-3xl text-[#f3ead9]"
        style={{ margin: 0, lineHeight: 1.4 }}
      >
        {getGreeting()}
      </motion.h1>

      <motion.p
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: 'easeOut', delay: 0.35 }}
        className="font-arcade text-[9px] tracking-wider text-[rgba(243,234,217,0.4)]"
        style={{ marginTop: 16, marginBottom: 0 }}
      >
        What should we work on?
      </motion.p>

      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: 'easeOut', delay: 0.5 }}
        style={{
          display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)',
          gap: 10, marginTop: 40, maxWidth: 400, width: '100%',
        }}
      >
        {SUGGESTIONS.map(({ icon, text }) => (
          <SuggestionCard key={text} icon={icon} text={text} onClick={() => onSuggestion(text)} />
        ))}
      </motion.div>
    </motion.div>
  )
}
