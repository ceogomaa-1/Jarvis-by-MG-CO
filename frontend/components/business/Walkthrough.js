'use client'
import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { sanitizeSvg } from '@/lib/sanitizeSvg'

// ─── Typewriter ───────────────────────────────────────────────────────────────

function TypewriterText({ text, onDone, speed = 14 }) {
  const [displayed, setDisplayed] = useState('')

  useEffect(() => {
    if (!text) { onDone?.(); return }
    let i = 0
    setDisplayed('')
    const iv = setInterval(() => {
      i++
      setDisplayed(text.slice(0, i))
      if (i >= text.length) { clearInterval(iv); onDone?.() }
    }, speed)
    return () => clearInterval(iv)
  }, [text])

  return (
    <span>
      {displayed}
      <span style={{ opacity: displayed.length < (text?.length ?? 0) ? 1 : 0 }}>▊</span>
    </span>
  )
}

// ─── Single step ──────────────────────────────────────────────────────────────

function WalkthroughStep({ step, stepIndex }) {
  const [textDone, setTextDone] = useState(false)
  const hasSvg = step.needs_visual && step.visual?.svg_content

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28, delay: stepIndex * 0.04 }}
      style={{ marginBottom: 28 }}
    >
      {/* Step number + instruction */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, marginBottom: 10 }}>
        <motion.div
          initial={{ scale: 0.5, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ duration: 0.22 }}
          style={{
            width: 28, height: 28, borderRadius: '50%', flexShrink: 0,
            background: 'rgba(45,127,249,0.14)', border: '1px solid rgba(45,127,249,0.4)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 11, fontWeight: 700, color: '#2d7ff9',
            fontFamily: 'system-ui, sans-serif',
          }}
        >
          {step.step_number}
        </motion.div>

        <div style={{ flex: 1 }}>
          <p style={{
            margin: 0, fontSize: 14, color: '#e8e8e8',
            lineHeight: 1.6, fontFamily: 'system-ui, sans-serif', minHeight: 22,
          }}>
            <TypewriterText
              text={step.instruction || ''}
              onDone={() => setTextDone(true)}
              speed={13}
            />
          </p>
          {step.detail && textDone && (
            <motion.p
              initial={{ opacity: 0 }} animate={{ opacity: 1 }}
              transition={{ delay: 0.15 }}
              style={{
                margin: '5px 0 0', fontSize: 12,
                color: 'rgba(232,232,232,0.45)',
                fontFamily: 'system-ui, sans-serif',
                fontStyle: 'italic', lineHeight: 1.45,
              }}
            >
              {step.detail}
            </motion.p>
          )}
        </div>
      </div>

      {/* SVG illustration — renders only after typewriter completes */}
      {hasSvg && textDone && (
        <motion.div
          initial={{ opacity: 0, scaleY: 0.96 }}
          animate={{ opacity: 1, scaleY: 1 }}
          transition={{ duration: 0.35, ease: 'easeOut' }}
          style={{ marginLeft: 40 }}
        >
          <div
            dangerouslySetInnerHTML={{ __html: sanitizeSvg(step.visual.svg_content) }}
            style={{
              width: '100%', borderRadius: 8, overflow: 'hidden',
              border: '1px solid rgba(232,232,232,0.08)',
              lineHeight: 0, // prevents whitespace gap below SVG
            }}
          />
          {step.visual.caption && (
            <p style={{
              margin: '5px 0 0', fontSize: 11,
              color: 'rgba(232,232,232,0.35)',
              fontFamily: 'system-ui, sans-serif',
              fontStyle: 'italic',
            }}>
              {step.visual.caption}
            </p>
          )}
        </motion.div>
      )}
    </motion.div>
  )
}

// ─── Sources ──────────────────────────────────────────────────────────────────

function Sources({ sources }) {
  if (!sources?.length) return null
  return (
    <motion.div
      initial={{ opacity: 0 }} animate={{ opacity: 1 }}
      transition={{ delay: 0.3 }}
      style={{ marginTop: 20, paddingTop: 14, borderTop: '1px solid rgba(232,232,232,0.07)' }}
    >
      <div style={{
        fontSize: 9, letterSpacing: '0.18em', textTransform: 'uppercase',
        color: 'rgba(232,232,232,0.3)', fontFamily: 'system-ui, sans-serif', marginBottom: 8,
      }}>
        Sources
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {sources.slice(0, 4).map((s, i) => {
          let hostname = ''
          try { hostname = new URL(s.url).hostname } catch {}
          return (
            <a key={i} href={s.url} target="_blank" rel="noopener noreferrer"
              style={{
                display: 'flex', alignItems: 'center', gap: 6,
                fontSize: 11, color: 'rgba(232,232,232,0.45)',
                textDecoration: 'none', fontFamily: 'system-ui, sans-serif',
              }}
              onMouseEnter={e => e.currentTarget.style.color = 'rgba(232,232,232,0.75)'}
              onMouseLeave={e => e.currentTarget.style.color = 'rgba(232,232,232,0.45)'}
            >
              {hostname && (
                <img
                  src={`https://www.google.com/s2/favicons?domain=${hostname}&sz=14`}
                  alt="" width={12} height={12}
                  style={{ borderRadius: 2, flexShrink: 0, opacity: 0.7 }}
                  onError={e => { e.target.style.display = 'none' }}
                />
              )}
              {s.title}
            </a>
          )
        })}
      </div>
    </motion.div>
  )
}

// ─── Main export ─────────────────────────────────────────────────────────────

export default function Walkthrough({ title, intro, steps, loading, sources }) {
  return (
    <div style={{ marginTop: 4 }}>
      {title && (
        <motion.div
          initial={{ opacity: 0 }} animate={{ opacity: 1 }}
          style={{
            fontSize: 10, letterSpacing: '0.15em', textTransform: 'uppercase',
            color: '#2d7ff9', marginBottom: 8, fontWeight: 600,
            fontFamily: 'system-ui, sans-serif',
          }}
        >
          Walkthrough
        </motion.div>
      )}

      {intro && (
        <motion.p
          initial={{ opacity: 0, y: 5 }} animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25 }}
          style={{
            fontSize: 13, color: 'rgba(232,232,232,0.65)',
            marginBottom: 18, lineHeight: 1.65,
            fontFamily: 'system-ui, sans-serif',
          }}
        >
          {intro}
        </motion.p>
      )}

      <AnimatePresence>
        {steps.map((step, i) => (
          <WalkthroughStep key={step.step_number ?? i} step={step} stepIndex={i} />
        ))}
      </AnimatePresence>

      {loading && (
        <div style={{ display: 'flex', gap: 5, padding: '8px 0', alignItems: 'center' }}>
          {[0, 1, 2].map(i => (
            <motion.div key={i}
              style={{ width: 6, height: 6, borderRadius: '50%', background: '#2d7ff9' }}
              animate={{ scale: [0.8, 1.2, 0.8], opacity: [0.3, 1, 0.3] }}
              transition={{ duration: 1.1, delay: i * 0.18, repeat: Infinity }}
            />
          ))}
          <span style={{
            fontSize: 11, color: 'rgba(232,232,232,0.35)',
            marginLeft: 6, fontFamily: 'system-ui, sans-serif',
          }}>
            generating steps…
          </span>
        </div>
      )}

      {!loading && sources?.length > 0 && <Sources sources={sources} />}
    </div>
  )
}
