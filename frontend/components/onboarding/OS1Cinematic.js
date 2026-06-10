'use client'
import { useState, useEffect, useMemo } from 'react'
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion'
import ParticleField from './ParticleField'
import CRTOverlay from './CRTOverlay'

const SCENE_ORDER = ['genesis', 'name', 'promise', 'capabilities', 'lockup']

const SCENE_DURATIONS = {
  genesis: 3000,
  name: 3000,
  promise: 8000,
  capabilities: 4900,
  lockup: 3400,
}

const TOTAL_DURATION = Object.values(SCENE_DURATIONS).reduce((a, b) => a + b, 0)

const PROMISE_LINES = [
  'It learns your business.',
  'It remembers everything.',
  'It acts before you ask.',
  'Meet your operator.',
]

const CAPABILITIES = [
  'DRAFTS YOUR OUTREACH',
  'WATCHES YOUR NUMBERS',
  'BOOKS YOUR CALENDAR',
  'BUILDS & SHIPS YOUR WEBSITE',
  'FILLS YOUR PIPELINE',
]

// Tempo accelerates across the cuts: 1.2s -> 0.9s -> 0.7s
const CAPABILITY_DURATIONS = [1200, 1100, 950, 900, 750]

const BOOT_LINES = ['initializing OS1 shell…', 'mounting memory core…', 'ready.']

function RingPulse() {
  return (
    <motion.div
      initial={{ width: 20, height: 20, opacity: 0.8 }}
      animate={{ width: 520, height: 520, opacity: 0 }}
      transition={{ duration: 1, ease: 'easeOut' }}
      style={{
        position: 'absolute', left: '50%', top: '50%', translateX: '-50%', translateY: '-50%',
        border: '1px solid #2d7ff9', borderRadius: '50%', pointerEvents: 'none',
      }}
    />
  )
}

function FlashFrame({ color = '#fff', opacity = 0.04, duration = 0.06 }) {
  return (
    <motion.div
      initial={{ opacity }}
      animate={{ opacity: 0 }}
      transition={{ duration }}
      style={{ position: 'fixed', inset: 0, background: color, zIndex: 50, pointerEvents: 'none' }}
    />
  )
}

function GenesisScene() {
  const [locked, setLocked] = useState(false)

  useEffect(() => {
    const t = setTimeout(() => setLocked(true), 2500)
    return () => clearTimeout(t)
  }, [])

  return (
    <motion.div
      key="genesis"
      exit={{ opacity: 0 }}
      transition={{ duration: 0.4 }}
      style={{ position: 'absolute', inset: 0, zIndex: 1, pointerEvents: 'none' }}
    >
      {locked && <RingPulse />}
      {locked && <FlashFrame color="#fff" opacity={0.04} duration={0.06} />}
    </motion.div>
  )
}

// Chromatic-aberration impact: red/cyan offset copies flash for ~2 frames,
// then settle into the white letter.
function GlitchLetter({ char }) {
  const [impact, setImpact] = useState(true)

  useEffect(() => {
    const t = setTimeout(() => setImpact(false), 90)
    return () => clearTimeout(t)
  }, [])

  return (
    <span style={{ position: 'relative', display: 'inline-block' }}>
      {impact && (
        <>
          <span aria-hidden style={{ position: 'absolute', left: -2, top: 0, color: '#ff3b3b', opacity: 0.7 }}>{char}</span>
          <span aria-hidden style={{ position: 'absolute', left: 2, top: 0, color: '#3bf0ff', opacity: 0.7 }}>{char}</span>
        </>
      )}
      <span style={{ position: 'relative', color: '#e8e8e8' }}>{char}</span>
    </span>
  )
}

// "OS1" slams in with x-jitter plus a one-frame horizontal slice displacement.
function GlitchOS1() {
  return (
    <motion.span
      className="font-pixel"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1, x: [0, -4, 4, -2, 0] }}
      transition={{ opacity: { duration: 0.05 }, x: { duration: 0.12, times: [0, 0.25, 0.5, 0.75, 1] } }}
      style={{ position: 'relative', fontSize: 'clamp(28px, 5vw, 44px)', color: '#2d7ff9', letterSpacing: '0.08em', display: 'inline-block' }}
    >
      <span style={{ visibility: 'hidden' }}>OS1</span>
      <span style={{ position: 'absolute', inset: 0, clipPath: 'inset(0 0 50% 0)' }}>
        <motion.span initial={{ x: 3 }} animate={{ x: 0 }} transition={{ duration: 0.04 }} style={{ display: 'block' }}>OS1</motion.span>
      </span>
      <span style={{ position: 'absolute', inset: 0, clipPath: 'inset(50% 0 0 0)' }}>
        <motion.span initial={{ x: -3 }} animate={{ x: 0 }} transition={{ duration: 0.04 }} style={{ display: 'block' }}>OS1</motion.span>
      </span>
    </motion.span>
  )
}

function NameScene() {
  const word = 'JARVIS'
  const [typed, setTyped] = useState(0)
  const [showOS1, setShowOS1] = useState(false)

  useEffect(() => {
    if (typed < word.length) {
      const t = setTimeout(() => setTyped(typed + 1), 110)
      return () => clearTimeout(t)
    }
    const t = setTimeout(() => setShowOS1(true), 300)
    return () => clearTimeout(t)
  }, [typed])

  return (
    <motion.div
      key="name"
      exit={{ opacity: 0 }}
      transition={{ duration: 0.4 }}
      style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 18, zIndex: 1 }}
    >
      <span className="font-pixel" style={{ fontSize: 'clamp(56px, 10vw, 88px)', color: '#e8e8e8', letterSpacing: '0.08em', display: 'inline-flex' }}>
        {word.slice(0, typed).split('').map((ch, i) => <GlitchLetter key={i} char={ch} />)}
        {typed < word.length && <span className="os1-cursor" />}
      </span>
      {showOS1 && <GlitchOS1 />}
    </motion.div>
  )
}

// Three fading, blurring copies of the line that just exited — a motion-blur trail.
function GhostTrail({ text }) {
  return (
    <>
      {[0, 1, 2].map(g => (
        <motion.p
          key={g}
          className="font-pixel"
          initial={{ opacity: 0.3 / (g + 1), filter: 'blur(0px)', x: 0 }}
          animate={{ opacity: 0, filter: 'blur(14px)', x: (g + 1) * 6 }}
          transition={{ duration: 0.5, delay: g * 0.05, ease: 'easeOut' }}
          style={{ position: 'absolute', inset: 0, margin: 0, textAlign: 'center', fontSize: 'clamp(28px, 4vw, 36px)', color: '#e8e8e8', whiteSpace: 'nowrap', pointerEvents: 'none' }}
        >
          {text}
        </motion.p>
      ))}
    </>
  )
}

// Each word eases in: letter-spacing 0.3em -> 0.02em, blur(6px) -> 0.
function PromiseLine({ text }) {
  const words = text.split(' ')
  return (
    <p className="font-pixel" style={{
      position: 'relative', margin: 0, display: 'flex', flexWrap: 'wrap', gap: '0.35em',
      justifyContent: 'center', fontSize: 'clamp(28px, 4vw, 36px)', color: '#e8e8e8', padding: '0 24px',
    }}>
      {words.map((w, i) => (
        <motion.span
          key={i}
          initial={{ letterSpacing: '0.3em', filter: 'blur(6px)', opacity: 0 }}
          animate={{ letterSpacing: '0.02em', filter: 'blur(0px)', opacity: 1 }}
          transition={{ duration: 0.5, delay: i * 0.08, ease: 'easeOut' }}
        >
          {w}
        </motion.span>
      ))}
    </p>
  )
}

function PromiseScene() {
  const [idx, setIdx] = useState(0)
  const [prevText, setPrevText] = useState(null)

  useEffect(() => {
    if (idx >= PROMISE_LINES.length - 1) return
    const t = setTimeout(() => {
      setPrevText(PROMISE_LINES[idx])
      setIdx(i => i + 1)
    }, 2000)
    return () => clearTimeout(t)
  }, [idx])

  return (
    <motion.div
      key="promise"
      exit={{ opacity: 0 }}
      transition={{ duration: 0.4 }}
      style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1 }}
    >
      <div style={{ position: 'relative', width: '100%', display: 'flex', justifyContent: 'center' }}>
        {prevText && <GhostTrail key={`ghost-${idx}`} text={prevText} />}
        <PromiseLine key={idx} text={PROMISE_LINES[idx]} />
      </div>
    </motion.div>
  )
}

function CapabilityCut({ index, text, flash }) {
  const onRight = index % 2 === 0
  return (
    <motion.div
      initial={{ x: -2 }}
      animate={{ x: [-2, 2, 0] }}
      transition={{ duration: 0.12 }}
      style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden' }}
    >
      <span className="font-pixel" style={{
        position: 'absolute', fontSize: '200px', fontWeight: 700, color: '#e8e8e8', opacity: 0.06,
        right: onRight ? '4%' : 'auto', left: onRight ? 'auto' : '4%',
        top: '8%', lineHeight: 1, userSelect: 'none', whiteSpace: 'nowrap',
      }}>
        {String(index + 1).padStart(2, '0')}
      </span>
      <div className="os1-card" style={{ padding: '28px 44px', display: 'flex', alignItems: 'center', gap: 14, borderColor: '#3d3d3d', position: 'relative' }}>
        <motion.span
          animate={{ opacity: [0.3, 1, 0.3] }}
          transition={{ duration: 1.1, repeat: Infinity }}
          style={{ width: 8, height: 8, background: '#2d7ff9', flexShrink: 0 }}
        />
        <span className="font-pixel" style={{ fontSize: 'clamp(16px, 3vw, 24px)', color: '#e8e8e8', letterSpacing: '0.06em', whiteSpace: 'nowrap' }}>
          {text}
        </span>
      </div>
      {flash && <FlashFrame color="#e8e8e8" opacity={1} duration={0.05} />}
    </motion.div>
  )
}

function CapabilitiesScene() {
  const [idx, setIdx] = useState(0)

  useEffect(() => {
    if (idx >= CAPABILITIES.length - 1) return
    const t = setTimeout(() => setIdx(i => i + 1), CAPABILITY_DURATIONS[idx])
    return () => clearTimeout(t)
  }, [idx])

  return (
    <motion.div
      key="capabilities"
      exit={{ opacity: 0 }}
      transition={{ duration: 0.4 }}
      style={{ position: 'absolute', inset: 0, zIndex: 1 }}
    >
      <CapabilityCut key={idx} index={idx} text={CAPABILITIES[idx]} flash={idx === 2 || idx === 4} />
    </motion.div>
  )
}

function BootLines() {
  const [count, setCount] = useState(0)

  useEffect(() => {
    if (count >= BOOT_LINES.length) return
    const t = setTimeout(() => setCount(c => c + 1), 220)
    return () => clearTimeout(t)
  }, [count])

  return (
    <div style={{ position: 'absolute', bottom: '6%', left: 0, right: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
      {BOOT_LINES.slice(0, count).map((l, i) => (
        <motion.div
          key={i}
          initial={{ opacity: 0, x: -6 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.2 }}
          className="font-pixel"
          style={{ fontSize: 12, color: 'var(--os1-text-dim)' }}
        >
          <span style={{ color: '#2d7ff9', marginRight: 8 }}>▸</span>{l}
        </motion.div>
      ))}
    </div>
  )
}

function LockupScene({ skipSweep, onClick }) {
  const [phase, setPhase] = useState(skipSweep ? 'lockup' : 'burst')

  useEffect(() => {
    if (skipSweep) return
    const timers = [
      setTimeout(() => setPhase('reassemble'), 700),
      setTimeout(() => setPhase('lockup'), 1700),
      setTimeout(() => setPhase('boot'), 2400),
    ]
    return () => timers.forEach(clearTimeout)
  }, [skipSweep])

  return (
    <motion.div
      key="lockup"
      exit={{ opacity: 0 }}
      transition={{ duration: 0.4 }}
      onClick={onClick}
      style={{ position: 'absolute', inset: 0, zIndex: 1, cursor: 'pointer' }}
    >
      {(phase === 'lockup' || phase === 'boot') && (
        <>
          <RingPulse />
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            style={{ position: 'absolute', bottom: '18%', left: 0, right: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10 }}
          >
            <div className="font-pixel" style={{ fontSize: 'clamp(24px, 4vw, 32px)', color: '#e8e8e8', letterSpacing: '0.1em' }}>
              JARVIS <span style={{ color: '#2d7ff9' }}>OS1</span>
            </div>
            <div className="font-pixel" style={{ fontSize: 14, color: '#a3a3a3' }}>Let&apos;s build yours.</div>
          </motion.div>
        </>
      )}
      {phase === 'boot' && <BootLines />}
    </motion.div>
  )
}

function FilmScrubber({ scene }) {
  const elapsedBefore = useMemo(() => {
    const idx = SCENE_ORDER.indexOf(scene)
    return SCENE_ORDER.slice(0, idx).reduce((sum, s) => sum + SCENE_DURATIONS[s], 0)
  }, [scene])

  return (
    <div style={{ position: 'fixed', bottom: 0, left: 0, right: 0, height: 1, background: 'rgba(255,255,255,0.06)', zIndex: 10 }}>
      <motion.div
        key={scene}
        initial={{ width: `${(elapsedBefore / TOTAL_DURATION) * 100}%` }}
        animate={{ width: `${((elapsedBefore + SCENE_DURATIONS[scene]) / TOTAL_DURATION) * 100}%` }}
        transition={{ duration: SCENE_DURATIONS[scene] / 1000, ease: 'linear' }}
        style={{ height: 1, background: '#2d7ff9' }}
      />
    </div>
  )
}

export default function OS1Cinematic({ onComplete }) {
  const reducedMotion = useReducedMotion()
  const [scene, setScene] = useState('genesis')
  const [showSkip, setShowSkip] = useState(false)
  const [particleState, setParticleState] = useState('assemble')
  const [mobile, setMobile] = useState(false)

  useEffect(() => {
    setMobile(window.innerWidth < 768)
  }, [])

  useEffect(() => {
    if (reducedMotion) setScene('lockup')
  }, [reducedMotion])

  useEffect(() => {
    const t = setTimeout(() => setShowSkip(true), 2500)
    return () => clearTimeout(t)
  }, [])

  // Particle state machine driven by scene — particles persist across the
  // whole cinematic, never destroyed/recreated.
  useEffect(() => {
    if (reducedMotion) return undefined
    if (scene === 'genesis') {
      setParticleState('assemble')
      const t = setTimeout(() => setParticleState('hold'), 2500)
      return () => clearTimeout(t)
    }
    if (scene === 'lockup') {
      setParticleState('burst')
      const t = setTimeout(() => setParticleState('reassemble'), 700)
      return () => clearTimeout(t)
    }
    return undefined
  }, [scene, reducedMotion])

  useEffect(() => {
    const idx = SCENE_ORDER.indexOf(scene)
    if (idx === -1) return undefined
    const duration = reducedMotion && scene === 'lockup' ? 1500 : SCENE_DURATIONS[scene]
    const t = setTimeout(() => {
      if (idx === SCENE_ORDER.length - 1) {
        onComplete?.()
      } else {
        setScene(SCENE_ORDER[idx + 1])
      }
    }, duration)
    return () => clearTimeout(t)
  }, [scene, reducedMotion]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div style={{ position: 'fixed', inset: 0, background: '#131313', overflow: 'hidden', zIndex: 100 }}>
      <ParticleField state={particleState} reducedMotion={reducedMotion} mobile={mobile} />

      <AnimatePresence mode="wait">
        {scene === 'genesis' && <GenesisScene key="genesis" />}
        {scene === 'name' && <NameScene key="name" />}
        {scene === 'promise' && <PromiseScene key="promise" />}
        {scene === 'capabilities' && <CapabilitiesScene key="capabilities" />}
        {scene === 'lockup' && <LockupScene key="lockup" skipSweep={reducedMotion} onClick={onComplete} />}
      </AnimatePresence>

      <CRTOverlay reducedMotion={reducedMotion} zIndex={5} />
      {!reducedMotion && <FilmScrubber scene={scene} />}

      {showSkip && (
        <button
          onClick={onComplete}
          className="font-pixel"
          style={{
            position: 'fixed', bottom: 24, right: 28, zIndex: 20,
            background: 'transparent', border: 'none', cursor: 'pointer',
            color: 'var(--os1-text-faint)', fontSize: 13, letterSpacing: '0.04em',
          }}
        >
          Skip ▸
        </button>
      )}
    </div>
  )
}
