'use client'
import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'

const BACKEND = 'https://jarvis-backend-4oz6.onrender.com'
const CANVAS_W = 600
const CANVAS_H = 380

// Route external images through the backend proxy to avoid CORS
function proxied(url) {
  if (!url || url.startsWith('data:')) return url
  return `${BACKEND}/api/business/proxy-image?url=${encodeURIComponent(url)}`
}

// ─── Typewriter ───────────────────────────────────────────────────────────────

function TypewriterText({ text, onDone, speed = 18 }) {
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

  return <span>{displayed}<span style={{ opacity: displayed.length < text?.length ? 1 : 0 }}>▊</span></span>
}

// ─── SVG annotation layer ─────────────────────────────────────────────────────

function AnnotationLayer({ annotations, visible }) {
  if (!annotations?.length || !visible) return null

  return (
    <svg
      viewBox={`0 0 ${CANVAS_W} ${CANVAS_H}`}
      preserveAspectRatio="none"
      style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none' }}
    >
      {annotations.map((ann, i) => {
        const delay = i * 0.15
        if (ann.type === 'circle') {
          const r = ann.radius || 28
          const circ = 2 * Math.PI * r
          return (
            <g key={i}>
              {/* Fill pulse */}
              <motion.circle
                cx={ann.x} cy={ann.y} r={r}
                fill={ann.color || '#f59e0b'}
                fillOpacity={0}
                animate={{ fillOpacity: [0, 0.18, 0.12] }}
                transition={{ delay, duration: 0.5 }}
              />
              {/* Stroke draw-on */}
              <motion.circle
                cx={ann.x} cy={ann.y} r={r}
                fill="none"
                stroke={ann.color || '#f59e0b'}
                strokeWidth={2.5}
                strokeLinecap="round"
                style={{ strokeDasharray: circ, strokeDashoffset: circ }}
                animate={{ strokeDashoffset: 0 }}
                transition={{ delay, duration: 0.6, ease: 'easeOut' }}
              />
              {/* Outer ring pulse */}
              <motion.circle
                cx={ann.x} cy={ann.y} r={r + 10}
                fill="none"
                stroke={ann.color || '#f59e0b'}
                strokeWidth={0.8}
                initial={{ opacity: 0, scale: 0.7 }}
                animate={{ opacity: [0, 0.5, 0], scale: [0.7, 1.2, 1.4] }}
                transition={{ delay: delay + 0.4, duration: 0.8 }}
              />
              {ann.label && (
                <motion.text
                  x={ann.x + r + 6} y={ann.y + 4}
                  fontSize={10} fill={ann.color || '#f59e0b'}
                  fontFamily="system-ui,sans-serif" fontWeight="600"
                  initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                  transition={{ delay: delay + 0.5 }}
                >
                  {ann.label}
                </motion.text>
              )}
            </g>
          )
        }

        if (ann.type === 'arrow') {
          const x1 = ann.x || 50, y1 = ann.y || 50
          const x2 = ann.x2 || x1 + 60, y2 = ann.y2 || y1 + 40
          const len = Math.hypot(x2 - x1, y2 - y1)
          return (
            <g key={i}>
              <motion.line
                x1={x1} y1={y1} x2={x2} y2={y2}
                stroke={ann.color || '#f59e0b'} strokeWidth={2.5}
                strokeLinecap="round"
                style={{ strokeDasharray: len, strokeDashoffset: len }}
                animate={{ strokeDashoffset: 0 }}
                transition={{ delay, duration: 0.5, ease: 'easeOut' }}
                markerEnd="url(#arrowhead)"
              />
              <defs>
                <marker id="arrowhead" markerWidth="8" markerHeight="6"
                  refX="7" refY="3" orient="auto">
                  <polygon points="0 0,8 3,0 6"
                    fill={ann.color || '#f59e0b'} />
                </marker>
              </defs>
            </g>
          )
        }

        if (ann.type === 'highlight') {
          const w = ann.width || 120, h = ann.height || 24
          return (
            <motion.rect key={i}
              x={(ann.x || 100) - w / 2} y={(ann.y || 100) - h / 2}
              width={w} height={h} rx={4}
              fill={ann.color || '#f59e0b'} fillOpacity={0}
              stroke={ann.color || '#f59e0b'} strokeWidth={1.5}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1, fillOpacity: 0.2 }}
              transition={{ delay, duration: 0.4 }}
            />
          )
        }

        return null
      })}
    </svg>
  )
}

// ─── Single step ──────────────────────────────────────────────────────────────

function WalkthroughStep({ step, stepIndex }) {
  const [textDone, setTextDone] = useState(false)
  const [imgLoaded, setImgLoaded] = useState(false)
  const [showAnnotations, setShowAnnotations] = useState(false)

  // Show annotations 400ms after image loads
  useEffect(() => {
    if (imgLoaded) {
      const t = setTimeout(() => setShowAnnotations(true), 400)
      return () => clearTimeout(t)
    }
  }, [imgLoaded])

  // If no image, show annotations after text finishes
  useEffect(() => {
    if (textDone && !step.screenshot_url && !step.screenshot_fallback) {
      setShowAnnotations(true)
    }
  }, [textDone])

  const imgSrc = proxied(step.screenshot_url) || step.screenshot_fallback

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: stepIndex * 0.05 }}
      style={{ marginBottom: 28 }}
    >
      {/* Step number + instruction */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, marginBottom: 10 }}>
        <motion.div
          initial={{ scale: 0.5, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ duration: 0.25 }}
          style={{
            width: 28, height: 28, borderRadius: '50%', flexShrink: 0,
            background: 'rgba(200,75,49,0.14)', border: '1px solid rgba(200,75,49,0.4)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 11, fontWeight: 700, color: '#c84b31',
            fontFamily: 'system-ui, sans-serif',
          }}
        >
          {step.step_number}
        </motion.div>

        <div style={{ flex: 1 }}>
          <p style={{
            margin: 0, fontSize: 14, color: '#f3ead9',
            lineHeight: 1.6, fontFamily: 'system-ui, sans-serif',
            minHeight: 22,
          }}>
            <TypewriterText
              text={step.instruction || ''}
              onDone={() => setTextDone(true)}
              speed={16}
            />
          </p>
          {step.detail && textDone && (
            <motion.p
              initial={{ opacity: 0 }} animate={{ opacity: 1 }}
              transition={{ delay: 0.2 }}
              style={{
                margin: '5px 0 0', fontSize: 12,
                color: 'rgba(243,234,217,0.45)',
                fontFamily: 'system-ui, sans-serif',
                fontStyle: 'italic', lineHeight: 1.45,
              }}
            >
              {step.detail}
            </motion.p>
          )}
        </div>
      </div>

      {/* Image + annotation overlay */}
      {imgSrc && textDone && (
        <motion.div
          initial={{ opacity: 0, scaleY: 0.95 }}
          animate={{ opacity: 1, scaleY: 1 }}
          transition={{ duration: 0.35, ease: 'easeOut' }}
          style={{
            position: 'relative', marginLeft: 40,
            borderRadius: 8, overflow: 'hidden',
            border: '1px solid rgba(243,234,217,0.08)',
            background: '#111',
            aspectRatio: `${CANVAS_W} / ${CANVAS_H}`,
          }}
        >
          <img
            src={imgSrc}
            alt={`Step ${step.step_number}`}
            style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
            onLoad={() => setImgLoaded(true)}
            onError={() => setImgLoaded(true)}
          />
          <AnnotationLayer
            annotations={step.annotations}
            visible={showAnnotations}
          />
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
      style={{
        marginTop: 20, paddingTop: 16,
        borderTop: '1px solid rgba(243,234,217,0.07)',
      }}
    >
      <div style={{
        fontSize: 9, letterSpacing: '0.18em', textTransform: 'uppercase',
        color: 'rgba(243,234,217,0.3)', fontFamily: 'system-ui, sans-serif',
        marginBottom: 8,
      }}>
        Sources
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {sources.slice(0, 4).map((s, i) => (
          <a
            key={i}
            href={s.url}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              fontSize: 11, color: 'rgba(243,234,217,0.45)',
              textDecoration: 'none', fontFamily: 'system-ui, sans-serif',
              lineHeight: 1.4,
            }}
            onMouseEnter={e => e.currentTarget.style.color = 'rgba(243,234,217,0.75)'}
            onMouseLeave={e => e.currentTarget.style.color = 'rgba(243,234,217,0.45)'}
          >
            <img
              src={`https://www.google.com/s2/favicons?domain=${new URL(s.url).hostname}&sz=14`}
              alt=""
              width={12} height={12}
              style={{ borderRadius: 2, flexShrink: 0, opacity: 0.7 }}
              onError={e => e.target.style.display = 'none'}
            />
            {s.title}
          </a>
        ))}
      </div>
    </motion.div>
  )
}

// ─── Main component ───────────────────────────────────────────────────────────

export default function Walkthrough({ title, intro, steps, loading, sources }) {
  return (
    <div style={{ marginTop: 4 }}>
      {title && (
        <motion.div
          initial={{ opacity: 0 }} animate={{ opacity: 1 }}
          style={{
            fontSize: 10, letterSpacing: '0.15em', textTransform: 'uppercase',
            color: '#c84b31', marginBottom: 8, fontWeight: 600,
            fontFamily: 'system-ui, sans-serif',
          }}
        >
          Walkthrough
        </motion.div>
      )}

      {intro && (
        <motion.p
          initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3 }}
          style={{
            fontSize: 13, color: 'rgba(243,234,217,0.65)',
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
              style={{ width: 6, height: 6, borderRadius: '50%', background: '#c84b31' }}
              animate={{ scale: [0.8, 1.2, 0.8], opacity: [0.3, 1, 0.3] }}
              transition={{ duration: 1.1, delay: i * 0.18, repeat: Infinity }}
            />
          ))}
          <span style={{
            fontSize: 11, color: 'rgba(243,234,217,0.35)',
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
