'use client'
import { motion } from 'framer-motion'

export function Section2Difference() {
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
          letterSpacing: '-0.01em',
          textAlign: 'center',
          maxWidth: 900,
          margin: '0 0 80px 0',
        }}
      >
        It doesn't wait to be asked.
      </motion.h2>

      <div style={{
        display: 'flex',
        gap: 32,
        flexWrap: 'wrap',
        maxWidth: 1100,
        width: '100%',
        justifyContent: 'center',
        alignItems: 'flex-start',
      }}>
        <motion.div
          initial={{ opacity: 0, x: -20 }}
          whileInView={{ opacity: 1, x: 0 }}
          viewport={{ once: true, margin: '-50px' }}
          transition={{ duration: 0.8, delay: 0.2 }}
          style={{ flex: 1, minWidth: 280, maxWidth: 480 }}
        >
          <p style={{
            fontFamily: 'system-ui, -apple-system, sans-serif',
            fontSize: 11,
            letterSpacing: '0.3em',
            textTransform: 'uppercase',
            color: 'rgba(243,234,217,0.4)',
            margin: '0 0 16px 0',
          }}>
            Other AI tools
          </p>
          <div style={{
            padding: '20px 24px',
            borderRadius: '4px 20px 20px 20px',
            background: 'rgba(255,255,255,0.04)',
            border: '1px solid rgba(255,255,255,0.06)',
            color: 'rgba(243,234,217,0.55)',
            fontFamily: 'system-ui, sans-serif',
            fontSize: 16,
            lineHeight: 1.5,
          }}>
            "How can I help you today?"
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, x: 20 }}
          whileInView={{ opacity: 1, x: 0 }}
          viewport={{ once: true, margin: '-50px' }}
          transition={{ duration: 0.8, delay: 0.5 }}
          style={{ flex: 1, minWidth: 280, maxWidth: 480 }}
        >
          <p style={{
            fontFamily: 'system-ui, -apple-system, sans-serif',
            fontSize: 11,
            letterSpacing: '0.3em',
            textTransform: 'uppercase',
            color: '#c84b31',
            margin: '0 0 16px 0',
          }}>
            Jarvis
          </p>
          <div style={{
            padding: '20px 24px',
            borderRadius: '4px 20px 20px 20px',
            background: 'rgba(200,75,49,0.08)',
            border: '1px solid rgba(200,75,49,0.22)',
            color: '#f3ead9',
            fontFamily: 'system-ui, sans-serif',
            fontSize: 16,
            lineHeight: 1.5,
            boxShadow: '0 0 40px rgba(200,75,49,0.08)',
          }}>
            "Hey Mikey — that investor pitch is in 3 hours. You said yesterday you wanted to rehearse the open. Want to run it now or push to 2 PM after lunch?"
          </div>
        </motion.div>
      </div>
    </section>
  )
}
