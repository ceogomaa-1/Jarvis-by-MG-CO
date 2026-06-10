'use client'
import { useState, useEffect, useMemo } from 'react'
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion'

const SCENE_ORDER = ['genesis', 'name', 'promise', 'capabilities', 'lockup']

const SCENE_DURATIONS = {
  genesis: 3000,
  name: 3000,
  promise: 8000,
  capabilities: 5000,
  lockup: 3000,
}

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

function Starfield() {
  const dots = useMemo(() => Array.from({ length: 18 }, (_, i) => ({
    id: i,
    x: Math.random() * 100,
    y: Math.random() * 100,
    drift: 10 + Math.random() * 18,
    duration: 18 + Math.random() * 18,
  })), [])

  return (
    <div style={{ position: 'absolute', inset: 0, zIndex: 0, pointerEvents: 'none' }}>
      {dots.map(d => (
        <motion.div
          key={d.id}
          initial={{ top: `${d.y}%` }}
          animate={{ top: [`${d.y}%`, `${(d.y + d.drift) % 100}%`, `${d.y}%`] }}
          transition={{ duration: d.duration, repeat: Infinity, ease: 'linear' }}
          style={{ position: 'absolute', left: `${d.x}%`, width: 1, height: 1, background: '#a3a3a3', opacity: 0.15 }}
        />
      ))}
    </div>
  )
}

const squareContainerVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.05, delayChildren: 0.1 } },
}

const squareVariants = {
  hidden: ({ startX, startY }) => ({ x: startX, y: startY, opacity: 0 }),
  visible: ({ targetX, targetY }) => ({
    x: targetX, y: targetY, opacity: 1,
    transition: { duration: 1, ease: [0.16, 1, 0.3, 1] },
  }),
}

function GenesisScene() {
  const squares = useMemo(() => {
    const positions = [
      [-1, -1], [0, -1], [1, -1],
      [-1.3, 0], [1.3, 0],
      [-1, 1], [0, 1], [1, 1],
      [-0.5, -1.7], [0.5, -1.7],
      [-0.5, 1.7], [0.5, 1.7],
    ]
    return positions.map(([dx, dy], i) => ({
      id: i,
      targetX: dx * 18,
      targetY: dy * 18,
      startX: dx * 18 + (Math.random() - 0.5) * 420,
      startY: dy * 18 + (Math.random() - 0.5) * 420,
    }))
  }, [])

  return (
    <motion.div
      key="genesis"
      exit={{ opacity: 0 }}
      transition={{ duration: 0.4 }}
      style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1 }}
    >
      <motion.div
        variants={squareContainerVariants}
        initial="hidden"
        animate="visible"
        style={{ position: 'relative', width: 96, height: 96 }}
      >
        {squares.map(sq => (
          <motion.div
            key={sq.id}
            custom={sq}
            variants={squareVariants}
            style={{
              position: 'absolute', left: '50%', top: '50%', marginLeft: -4, marginTop: -4,
              width: 8, height: 8, background: '#6e6e6e',
            }}
          />
        ))}
        <motion.img
          src="/jarvis-logo-mono.png"
          alt=""
          className="os1-logo-pixel"
          initial={{ opacity: 0, scale: 0.85 }}
          animate={{
            opacity: 1,
            scale: [0.85, 1.05, 1],
            filter: [
              'grayscale(1) brightness(0.85) drop-shadow(0 0 0px rgba(45,127,249,0))',
              'grayscale(1) brightness(1) drop-shadow(0 0 18px rgba(45,127,249,0.5))',
              'grayscale(1) brightness(0.9) drop-shadow(0 0 8px rgba(45,127,249,0.25))',
            ],
          }}
          transition={{ delay: 1.6, duration: 1.2, ease: 'easeOut' }}
          style={{ position: 'absolute', inset: 0, width: 96, height: 96, objectFit: 'contain' }}
        />
      </motion.div>
    </motion.div>
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
      <span className="font-pixel" style={{ fontSize: 'clamp(56px, 10vw, 88px)', color: '#e8e8e8', letterSpacing: '0.08em' }}>
        {word.slice(0, typed)}
        {typed < word.length && <span className="os1-cursor" />}
      </span>
      {showOS1 && (
        <motion.span
          className="font-pixel"
          initial={{ opacity: 0, x: 0 }}
          animate={{ opacity: 1, x: [0, -3, 3, -3, 0] }}
          transition={{ opacity: { duration: 0.05 }, x: { duration: 0.25, times: [0, 0.25, 0.5, 0.75, 1] } }}
          style={{ fontSize: 'clamp(28px, 5vw, 44px)', color: '#2d7ff9', letterSpacing: '0.08em' }}
        >
          OS1
        </motion.span>
      )}
    </motion.div>
  )
}

function PromiseScene() {
  const [idx, setIdx] = useState(0)

  useEffect(() => {
    if (idx >= PROMISE_LINES.length - 1) return
    const t = setTimeout(() => setIdx(i => i + 1), 2000)
    return () => clearTimeout(t)
  }, [idx])

  return (
    <motion.div
      key="promise"
      exit={{ opacity: 0 }}
      transition={{ duration: 0.4 }}
      style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1 }}
    >
      <AnimatePresence mode="wait">
        <motion.p
          key={idx}
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -16 }}
          transition={{ duration: 0.6, ease: 'easeOut' }}
          className="font-pixel"
          style={{ fontSize: 'clamp(28px, 4vw, 36px)', color: '#e8e8e8', textAlign: 'center', padding: '0 24px', margin: 0 }}
        >
          {PROMISE_LINES[idx]}
        </motion.p>
      </AnimatePresence>
    </motion.div>
  )
}

function CapabilitiesScene() {
  const [idx, setIdx] = useState(0)

  useEffect(() => {
    if (idx >= CAPABILITIES.length - 1) return
    const t = setTimeout(() => setIdx(i => i + 1), 1100)
    return () => clearTimeout(t)
  }, [idx])

  return (
    <motion.div
      key="capabilities"
      exit={{ opacity: 0 }}
      transition={{ duration: 0.4 }}
      style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1 }}
    >
      <AnimatePresence mode="wait">
        <motion.div
          key={idx}
          initial={{ opacity: 0, scale: 0.92 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 1.02 }}
          transition={{ duration: 0.35, ease: 'easeOut' }}
          className="os1-card"
          style={{ padding: '28px 44px', display: 'flex', alignItems: 'center', gap: 14, borderColor: '#3d3d3d' }}
        >
          <motion.span
            animate={{ opacity: [0.3, 1, 0.3] }}
            transition={{ duration: 1.1, repeat: Infinity }}
            style={{ width: 8, height: 8, background: '#2d7ff9', flexShrink: 0 }}
          />
          <span className="font-pixel" style={{ fontSize: 'clamp(16px, 3vw, 24px)', color: '#e8e8e8', letterSpacing: '0.06em', whiteSpace: 'nowrap' }}>
            {CAPABILITIES[idx]}
          </span>
        </motion.div>
      </AnimatePresence>
    </motion.div>
  )
}

function LockupScene({ skipSweep, onClick }) {
  const [showLockup, setShowLockup] = useState(skipSweep)

  useEffect(() => {
    if (skipSweep) return
    const t = setTimeout(() => setShowLockup(true), 900)
    return () => clearTimeout(t)
  }, [skipSweep])

  return (
    <motion.div
      key="lockup"
      exit={{ opacity: 0 }}
      transition={{ duration: 0.4 }}
      onClick={onClick}
      style={{
        position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center', gap: 18, zIndex: 1, cursor: 'pointer',
      }}
    >
      {!showLockup ? (
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: '60%' }}
          transition={{ duration: 0.9, ease: 'easeInOut' }}
          style={{ height: 2, background: '#2d7ff9', boxShadow: '0 0 10px rgba(45,127,249,0.6)' }}
        />
      ) : (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 14 }}
        >
          <img src="/jarvis-logo-mono.png" alt="" className="os1-logo-pixel" style={{ width: 64, height: 64 }} />
          <div className="font-pixel" style={{ fontSize: 'clamp(24px, 4vw, 32px)', color: '#e8e8e8', letterSpacing: '0.1em' }}>
            JARVIS <span style={{ color: '#2d7ff9' }}>OS1</span>
          </div>
          <div className="font-pixel" style={{ fontSize: 14, color: '#a3a3a3' }}>Let&apos;s build yours.</div>
        </motion.div>
      )}
    </motion.div>
  )
}

export default function OS1Cinematic({ onComplete }) {
  const reducedMotion = useReducedMotion()
  const [scene, setScene] = useState('genesis')
  const [showSkip, setShowSkip] = useState(false)

  useEffect(() => {
    if (reducedMotion) setScene('lockup')
  }, [reducedMotion])

  useEffect(() => {
    const t = setTimeout(() => setShowSkip(true), 2500)
    return () => clearTimeout(t)
  }, [])

  useEffect(() => {
    const idx = SCENE_ORDER.indexOf(scene)
    if (idx === -1) return
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
      <Starfield />
      <AnimatePresence mode="wait">
        {scene === 'genesis' && <GenesisScene key="genesis" />}
        {scene === 'name' && <NameScene key="name" />}
        {scene === 'promise' && <PromiseScene key="promise" />}
        {scene === 'capabilities' && <CapabilitiesScene key="capabilities" />}
        {scene === 'lockup' && <LockupScene key="lockup" skipSweep={reducedMotion} onClick={onComplete} />}
      </AnimatePresence>

      {showSkip && (
        <button
          onClick={onComplete}
          className="font-pixel"
          style={{
            position: 'fixed', bottom: 24, right: 28, zIndex: 2,
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
