'use client'
import { motion } from 'framer-motion'

const BAR_COUNT = 48

export function Section3Voice() {
  return (
    <section style={{
      minHeight: '90vh',
      background: '#0a0a0a',
      color: '#f3ead9',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '120px 24px',
      fontFamily: 'Georgia, "Times New Roman", serif',
      borderTop: '1px solid rgba(243,234,217,0.04)',
    }}>
      <motion.h2
        initial={{ opacity: 0, y: 24 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: '-100px' }}
        transition={{ duration: 1, ease: [0.2, 0.65, 0.3, 1] }}
        style={{
          fontSize: 'clamp(36px, 5vw, 60px)',
          fontWeight: 400,
          lineHeight: 1.1,
          textAlign: 'center',
          maxWidth: 900,
          margin: '0 0 24px 0',
        }}
      >
        Talk to it like a person.
      </motion.h2>

      <motion.p
        initial={{ opacity: 0 }}
        whileInView={{ opacity: 1 }}
        viewport={{ once: true, margin: '-100px' }}
        transition={{ duration: 1, delay: 0.3 }}
        style={{
          fontFamily: 'system-ui, -apple-system, sans-serif',
          fontSize: 17,
          fontWeight: 300,
          color: 'rgba(243,234,217,0.6)',
          maxWidth: 560,
          textAlign: 'center',
          margin: '0 0 80px 0',
          lineHeight: 1.6,
        }}
      >
        Voice in. Voice back. Real-time. No wake words. No hold-to-talk. Just speak.
      </motion.p>

      <motion.div
        initial={{ opacity: 0 }}
        whileInView={{ opacity: 1 }}
        viewport={{ once: true }}
        transition={{ duration: 0.8, delay: 0.6 }}
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 4,
          width: '100%',
          maxWidth: 640,
          height: 120,
        }}
      >
        {Array.from({ length: BAR_COUNT }).map((_, i) => {
          const heights = ['18%', '60%', '38%', '85%', '28%', '70%', '45%', '20%']
          return (
            <motion.div
              key={i}
              animate={{ height: heights }}
              transition={{
                duration: 2.2 + (i % 5) * 0.3,
                repeat: Infinity,
                ease: 'easeInOut',
                delay: i * 0.04,
              }}
              style={{
                width: 3,
                background: 'linear-gradient(to top, rgba(200,75,49,0.9), rgba(200,75,49,0.25))',
                borderRadius: 2,
                minHeight: 4,
              }}
            />
          )
        })}
      </motion.div>
    </section>
  )
}
