'use client'
import { motion } from 'framer-motion'
import { Orb } from './Orb'

const INTEGRATIONS = [
  { label: 'Calendar', angle: 270 },
  { label: 'Email', angle: 342 },
  { label: 'Files', angle: 54 },
  { label: 'Screen', angle: 126 },
  { label: 'Web', angle: 198 },
]

export function Section4Connected() {
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
          textAlign: 'center',
          margin: '0 0 24px 0',
        }}
      >
        It sees what you see.
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
          maxWidth: 600,
          textAlign: 'center',
          margin: '0 0 80px 0',
          lineHeight: 1.6,
        }}
      >
        Your calendar. Your inbox. Your files. Your conversations. Jarvis pulls from the context you already live in — so you stop explaining yourself.
      </motion.p>

      <div style={{
        position: 'relative',
        width: 'min(400px, 90vw)',
        height: 'min(400px, 90vw)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}>
        <motion.div
          initial={{ opacity: 0, scale: 0.8 }}
          whileInView={{ opacity: 1, scale: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 1.2, delay: 0.5 }}
        >
          <Orb size={220} />
        </motion.div>

        {INTEGRATIONS.map((item, i) => {
          const radians = (item.angle * Math.PI) / 180
          const radius = 200
          const x = Math.cos(radians) * radius
          const y = Math.sin(radians) * radius

          return (
            <motion.div
              key={item.label}
              initial={{ opacity: 0, scale: 0.5 }}
              whileInView={{ opacity: 1, scale: 1 }}
              viewport={{ once: true }}
              transition={{ duration: 0.7, delay: 1 + i * 0.15, ease: 'easeOut' }}
              style={{
                position: 'absolute',
                left: `calc(50% + ${x}px)`,
                top: `calc(50% + ${y}px)`,
                transform: 'translate(-50%, -50%)',
                fontFamily: 'system-ui, -apple-system, sans-serif',
                fontSize: 10,
                fontWeight: 500,
                letterSpacing: '0.28em',
                textTransform: 'uppercase',
                color: 'rgba(243,234,217,0.75)',
                padding: '8px 16px',
                border: '1px solid rgba(243,234,217,0.18)',
                borderRadius: 999,
                background: 'rgba(0,0,0,0.5)',
                backdropFilter: 'blur(8px)',
                whiteSpace: 'nowrap',
              }}
            >
              {item.label}
            </motion.div>
          )
        })}
      </div>
    </section>
  )
}
