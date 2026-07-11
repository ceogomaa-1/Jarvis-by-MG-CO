'use client'
import { motion } from 'framer-motion'
import { GooeyFilter } from './GooeyFilter'
import { PixelTrail } from './PixelTrail'
import { useScreenSize } from './useScreenSize'

const HEADING_LINES = [
  ['Not', 'a', 'tool.'],
  ['A', 'presence.'],
]

export function Hero({ onBegin }) {
  const screenSize = useScreenSize()

  return (
    <section
      style={{
        position: 'relative',
        width: '100vw',
        height: '100vh',
        minHeight: 700,
        overflow: 'hidden',
        background: '#0a0a0a',
      }}
    >
      {/* Background — impressionist painting */}
      <img
        src="https://images.aiscribbles.com/34fe5695dbc942628e3cad9744e8ae13.png?v=60d084"
        alt=""
        style={{
          position: 'absolute',
          inset: 0,
          width: '100%',
          height: '100%',
          objectFit: 'cover',
          opacity: 0.7,
          zIndex: 0,
          pointerEvents: 'none',
        }}
      />

      {/* Gooey pixel trail overlay */}
      <GooeyFilter id="hero-gooey" strength={5} />
      <div
        style={{
          position: 'absolute',
          inset: 0,
          zIndex: 1,
          filter: 'url(#hero-gooey)',
        }}
      >
        <PixelTrail
          pixelSize={screenSize.lessThan('md') ? 24 : 32}
          fadeDuration={0}
          delay={500}
          pixelClassName="bg-white"
        />
      </div>

      {/* Content */}
      <div
        style={{
          position: 'relative',
          zIndex: 2,
          width: '100%',
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '48px 24px 32px',
          fontFamily: 'Georgia, "Times New Roman", serif',
          pointerEvents: 'none',
        }}
      >
        {/* Top wordmark */}
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 1, delay: 0.2 }}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 16,
            color: 'rgba(243,234,217,0.85)',
          }}
        >
          <div style={{ width: 32, height: 1, background: 'rgba(243,234,217,0.3)' }} />
          <span style={{
            fontFamily: 'Georgia, serif',
            fontSize: 13,
            letterSpacing: '0.5em',
            fontWeight: 400,
            textTransform: 'uppercase',
          }}>RUE</span>
          <div style={{ width: 32, height: 1, background: 'rgba(243,234,217,0.3)' }} />
        </motion.div>

        {/* Center: heading + sub + CTA */}
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: 28,
            textAlign: 'center',
            maxWidth: 900,
          }}
        >
          {/* Word-by-word headline */}
          <h1
            style={{
              fontSize: 'clamp(48px, 7vw, 88px)',
              fontWeight: 400,
              lineHeight: 1.05,
              letterSpacing: '-0.02em',
              color: '#f3ead9',
              margin: 0,
              padding: '0 16px',
            }}
          >
            {HEADING_LINES.map((line, lineIdx) => (
              <div key={lineIdx} style={{ display: 'block' }}>
                {line.map((word, wordIdx) => {
                  const flatIdx = HEADING_LINES.slice(0, lineIdx).flat().length + wordIdx
                  return (
                    <motion.span
                      key={wordIdx}
                      initial={{ opacity: 0, y: 24 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{
                        duration: 0.8,
                        delay: 1.2 + flatIdx * 0.18,
                        ease: [0.2, 0.65, 0.3, 1],
                      }}
                      style={{ display: 'inline-block', marginRight: '0.25em' }}
                    >
                      {word}
                    </motion.span>
                  )
                })}
              </div>
            ))}
          </h1>

          <motion.p
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 1, delay: 2.4 }}
            style={{
              fontFamily: 'system-ui, -apple-system, sans-serif',
              fontSize: 17,
              fontWeight: 300,
              lineHeight: 1.6,
              color: 'rgba(243,234,217,0.7)',
              maxWidth: 540,
              margin: 0,
              padding: '0 16px',
              letterSpacing: '0.01em',
            }}
          >
            Rue remembers. Anticipates. Acts.<br />
            Across everything you do.
          </motion.p>

          <motion.button
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 1, delay: 2.8 }}
            whileHover={{ scale: 1.03, color: '#c84b31' }}
            whileTap={{ scale: 0.97 }}
            onClick={onBegin}
            style={{
              pointerEvents: 'auto',
              fontFamily: 'system-ui, -apple-system, sans-serif',
              fontSize: 15,
              fontWeight: 500,
              letterSpacing: '0.15em',
              textTransform: 'uppercase',
              color: 'rgba(243,234,217,0.9)',
              background: 'transparent',
              border: '1px solid rgba(243,234,217,0.18)',
              borderRadius: 999,
              padding: '14px 32px',
              cursor: 'pointer',
              transition: 'border-color 300ms ease',
            }}
            onMouseEnter={(e) => e.currentTarget.style.borderColor = 'rgba(200,75,49,0.5)'}
            onMouseLeave={(e) => e.currentTarget.style.borderColor = 'rgba(243,234,217,0.18)'}
          >
            Begin <span style={{ marginLeft: 8 }}>→</span>
          </motion.button>
        </div>

        {/* Bottom scroll hint */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 3.4, duration: 1 }}
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: 8,
            color: 'rgba(243,234,217,0.4)',
            fontFamily: 'system-ui, sans-serif',
            fontSize: 10,
            letterSpacing: '0.3em',
            textTransform: 'uppercase',
          }}
        >
          <span>Scroll</span>
          <motion.div
            animate={{ y: [0, 6, 0] }}
            transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
            style={{ width: 1, height: 24, background: 'rgba(243,234,217,0.3)' }}
          />
        </motion.div>
      </div>
    </section>
  )
}
