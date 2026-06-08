'use client'
import Image from 'next/image'
import { motion } from 'framer-motion'

function getGreeting() {
  const h = new Date().getHours()
  if (h >= 5 && h < 12) return 'Good Morning'
  if (h >= 12 && h < 18) return 'Good Afternoon'
  return 'Good Evening'
}

export default function WelcomeState({ isStreaming = false }) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0, scale: 0.98 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="os1-welcome"
    >
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45, ease: 'easeOut' }}
        className={isStreaming ? 'os1-welcome-logo is-thinking' : 'os1-welcome-logo'}
      >
        <Image src="/jarvis-logo-mono.png" alt="Jarvis OS1" width={110} height={110} priority />
      </motion.div>

      <motion.h1
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45, ease: 'easeOut', delay: 0.1 }}
      >
        {getGreeting()}
      </motion.h1>

      <motion.p
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45, ease: 'easeOut', delay: 0.18 }}
      >
        What should we work on?
      </motion.p>
    </motion.div>
  )
}
