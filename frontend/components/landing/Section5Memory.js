'use client'
import { motion } from 'framer-motion'

const MEMORIES = [
  'Stressed about the launch.',
  'Loves cold brew, hates oat milk.',
  "Daughter's name is Lily, age 4.",
  'Hates being interrupted before 10am.',
  'Investor pitch is on the 14th.',
  'Allergic to peanuts.',
  'Reads non-fiction on Sundays.',
  'Talks to mom every Wednesday.',
]

export function Section5Memory() {
  return (
    <section style={{
      minHeight: '100vh',
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
          textAlign: 'center',
          margin: '0 0 24px 0',
        }}
      >
        It builds with you.
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
          maxWidth: 620,
          textAlign: 'center',
          margin: '0 0 80px 0',
          lineHeight: 1.6,
        }}
      >
        Most AI starts from zero every conversation. Rue doesn't. The longer you use it, the less you have to say.
      </motion.p>

      <div style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 14,
        alignItems: 'stretch',
        maxWidth: 620,
        width: '100%',
      }}>
        {MEMORIES.map((memory, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, x: i % 2 === 0 ? -24 : 24 }}
            whileInView={{ opacity: 0.78, x: 0 }}
            viewport={{ once: true, margin: '-50px' }}
            transition={{ duration: 0.8, delay: 0.4 + i * 0.13 }}
            style={{
              fontFamily: 'Georgia, "Times New Roman", serif',
              fontSize: 18,
              fontStyle: 'italic',
              color: 'rgba(243,234,217,0.72)',
              padding: '10px 22px',
              borderLeft: '1px solid rgba(200,75,49,0.45)',
              alignSelf: i % 2 === 0 ? 'flex-start' : 'flex-end',
              maxWidth: '85%',
            }}
          >
            "{memory}"
          </motion.div>
        ))}
      </div>
    </section>
  )
}
