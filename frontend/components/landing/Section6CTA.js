'use client'
import { motion } from 'framer-motion'
import { useRouter } from 'next/navigation'
import { Orb } from './Orb'

export function Section6CTA() {
  const router = useRouter()

  return (
    <section style={{
      minHeight: '100vh',
      background: '#050505',
      color: '#f3ead9',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '120px 24px',
      fontFamily: 'Georgia, "Times New Roman", serif',
      borderTop: '1px solid rgba(243,234,217,0.04)',
    }}>
      <motion.div
        initial={{ opacity: 0, scale: 0.85 }}
        whileInView={{ opacity: 1, scale: 1 }}
        viewport={{ once: true, margin: '-100px' }}
        transition={{ duration: 1.5, ease: 'easeOut' }}
        style={{ marginBottom: 64 }}
      >
        <Orb size={280} />
      </motion.div>

      <motion.h2
        initial={{ opacity: 0, y: 24 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: '-100px' }}
        transition={{ duration: 1, delay: 0.4, ease: [0.2, 0.65, 0.3, 1] }}
        style={{
          fontSize: 'clamp(40px, 6vw, 72px)',
          fontWeight: 400,
          lineHeight: 1.1,
          textAlign: 'center',
          maxWidth: 800,
          margin: '0 0 56px 0',
        }}
      >
        You don't sign up for Jarvis.<br />
        You meet it.
      </motion.h2>

      <motion.button
        initial={{ opacity: 0, y: 12 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: '-100px' }}
        transition={{ duration: 1, delay: 0.7 }}
        whileHover={{ scale: 1.03 }}
        whileTap={{ scale: 0.97 }}
        onClick={() => router.push('/welcome/start')}
        style={{
          fontFamily: 'system-ui, -apple-system, sans-serif',
          fontSize: 15,
          fontWeight: 500,
          letterSpacing: '0.15em',
          textTransform: 'uppercase',
          color: 'rgba(243,234,217,0.9)',
          background: 'transparent',
          border: '1px solid rgba(243,234,217,0.22)',
          borderRadius: 999,
          padding: '16px 36px',
          cursor: 'pointer',
          transition: 'border-color 300ms ease',
        }}
        onMouseEnter={(e) => e.currentTarget.style.borderColor = 'rgba(200,75,49,0.6)'}
        onMouseLeave={(e) => e.currentTarget.style.borderColor = 'rgba(243,234,217,0.22)'}
      >
        Begin <span style={{ marginLeft: 8 }}>→</span>
      </motion.button>
    </section>
  )
}
