'use client'
import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion, useMotionValue, useTransform } from 'framer-motion'

// ─────────────────────────────────────────────────────────────────────
// Batch 71 — CO-FOUNDER MODE: the lever.
//
// The moment a user lifts this lever, Jarvis stops being a chat assistant
// and starts operating the business: it immediately runs a full scan →
// strategy → creation cycle and lands executable initiatives on their desk.
// This modal owns that whole moment: disclaimer → lever → live takeover
// progress → "N initiatives ready".
// ─────────────────────────────────────────────────────────────────────

const TRACK_H = 170        // lever track height (px)
const KNOB_H = 52          // knob height (px)
const TRAVEL = TRACK_H - KNOB_H - 12  // px of drag travel
const ENGAGE_AT = 0.72     // fraction of travel that commits the flip

const STEPS = [
  { id: 'scan',       label: 'Scanning your business',        sub: 'CRM · leads · inbox · calendar · revenue · socials' },
  { id: 'strategist', label: "Choosing this week's moves",    sub: 'highest leverage, grounded in your real numbers' },
  { id: 'researcher', label: 'Backing them with live data',   sub: 'web research on every move' },
  { id: 'creator',    label: 'Doing the work',                sub: 'drafts, campaigns, sequences — execution-ready' },
  { id: 'packager',   label: 'Preparing your approvals',      sub: 'each card = exactly what Jarvis will do' },
]

const STAGE_TO_STEP = {
  'operator-strategist': 1,
  'operator-researcher': 2,
  'operator-creator': 3,
  'operator-packager': 4,
}

const OVERLAY = {
  position: 'fixed', inset: 0, zIndex: 1200,
  background: 'rgba(0,0,0,0.72)',
  backdropFilter: 'blur(10px)',
  WebkitBackdropFilter: 'blur(10px)',
  display: 'flex', alignItems: 'center', justifyContent: 'center',
}

const PANEL = {
  width: '100%', maxWidth: 520, margin: '0 20px',
  background: 'rgba(15, 15, 18, 0.6)',
  backdropFilter: 'blur(30px) saturate(180%)',
  WebkitBackdropFilter: 'blur(30px) saturate(180%)',
  border: '1px solid rgba(232,232,232,0.14)',
  borderRadius: 24,
  padding: '34px 36px 30px',
  boxShadow: '0 30px 80px rgba(0,0,0,0.6), 0 0 120px rgba(45,127,249,0.07), inset 0 1px 0 rgba(232,232,232,0.07)',
  position: 'relative', overflow: 'hidden',
}

const PIXEL = { fontFamily: 'var(--font-pixel), monospace' }

function Lever({ armed, onEngage }) {
  const y = useMotionValue(0) // 0 = bottom (off) … -TRAVEL = top (on)
  const progress = useTransform(y, [0, -TRAVEL], [0, 1])
  const glow = useTransform(progress, p => `0 0 ${8 + p * 26}px rgba(45,127,249,${0.25 + p * 0.55})`)
  const trackGlow = useTransform(progress, p => `rgba(45,127,249,${0.06 + p * 0.22})`)
  const [committing, setCommitting] = useState(false)

  function handleDragEnd() {
    if (committing) return
    const lifted = -y.get() / TRAVEL
    if (lifted >= ENGAGE_AT && armed) {
      setCommitting(true)
      // Snap home and hand over — the panel transitions to the engage sequence.
      onEngage()
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10 }}>
      <span style={{ ...PIXEL, fontSize: 9, letterSpacing: '0.18em', color: '#2d7ff9' }}>ON</span>
      <motion.div
        style={{
          width: 64, height: TRACK_H, borderRadius: 32,
          border: '1px solid rgba(232,232,232,0.14)',
          background: trackGlow,
          position: 'relative',
          boxShadow: 'inset 0 2px 12px rgba(0,0,0,0.5)',
        }}
      >
        {/* Track notches */}
        {[0.25, 0.5, 0.75].map(f => (
          <div key={f} style={{
            position: 'absolute', left: 12, right: 12, top: `${f * 100}%`,
            height: 1, background: 'rgba(232,232,232,0.07)',
          }} />
        ))}
        <motion.div
          drag={armed && !committing ? 'y' : false}
          dragConstraints={{ top: -TRAVEL, bottom: 0 }}
          dragElastic={0.04}
          dragMomentum={false}
          onDragEnd={handleDragEnd}
          animate={committing ? { y: -TRAVEL } : undefined}
          style={{
            y,
            position: 'absolute', left: 5, bottom: 6,
            width: 52, height: KNOB_H, borderRadius: 26,
            background: 'linear-gradient(180deg, #3a3a3e 0%, #232326 100%)',
            border: '1px solid rgba(232,232,232,0.22)',
            boxShadow: glow,
            cursor: armed ? 'grab' : 'not-allowed',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            touchAction: 'none',
          }}
          whileDrag={{ cursor: 'grabbing', scale: 1.04 }}
        >
          <div style={{ width: 18, height: 3, borderRadius: 2, background: 'rgba(232,232,232,0.4)' }} />
        </motion.div>
      </motion.div>
      <span style={{ ...PIXEL, fontSize: 9, letterSpacing: '0.18em', color: 'rgba(232,232,232,0.35)' }}>OFF</span>
      <span style={{ ...PIXEL, fontSize: 10, color: 'rgba(232,232,232,0.45)', marginTop: 2 }}>
        {armed ? 'drag the lever up' : 'locked'}
      </span>
    </div>
  )
}

export default function CoFounderLever({
  open,
  onClose,
  userId,
  apiUrl,
  isReady,
  enabled,
  onEngaged,      // (firstRunId) => void — flag flipped on the backend
  onDisengaged,   // () => void
  onOpenInitiatives, // () => void — jump to the approvals board
}) {
  // phase: 'lever' | 'engaging' | 'ready' | 'error' | 'manage'
  const [phase, setPhase] = useState('lever')
  const [activeStep, setActiveStep] = useState(0)
  const [pendingCount, setPendingCount] = useState(null)
  const [errorNote, setErrorNote] = useState('')
  const esRef = useRef(null)

  useEffect(() => {
    if (!open) return
    setPhase(enabled ? 'manage' : 'lever')
    setActiveStep(0)
    setPendingCount(null)
    setErrorNote('')
    return () => { if (esRef.current) { esRef.current.close(); esRef.current = null } }
  }, [open, enabled])

  if (!open) return null

  async function engage() {
    setPhase('engaging')
    try {
      const res = await fetch(`${apiUrl}/api/business/autonomous/toggle`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, enabled: true }),
      })
      const data = await res.json()
      onEngaged?.(data.first_run_id || null)
      if (data.first_run_id) {
        watchRun(data.first_run_id)
      } else {
        // Flag is on but the immediate run couldn't launch — still a win, be honest.
        setErrorNote('Co-Founder Mode is ON. The first full run kicks off on the nightly cycle.')
        setPhase('error')
      }
    } catch (e) {
      console.error('engage failed', e)
      setErrorNote('Could not reach Jarvis. Check your connection and try again.')
      setPhase('lever')
    }
  }

  function watchRun(runId) {
    const es = new EventSource(
      `${apiUrl}/api/business/operator/status/stream?run_id=${encodeURIComponent(runId)}`
    )
    esRef.current = es
    // Step 0 ("scanning") shows immediately; stages bump it forward.
    es.onmessage = async (ev) => {
      try {
        const d = JSON.parse(ev.data)
        if (d.stage && STAGE_TO_STEP[d.stage] != null && d.status === 'running') {
          setActiveStep(STAGE_TO_STEP[d.stage])
        }
        if (['complete', 'failed', 'budget_capped', 'timeout'].includes(d.status)) {
          es.close(); esRef.current = null
          if (d.status === 'complete') {
            setActiveStep(STEPS.length)
            try {
              const r = await fetch(`${apiUrl}/api/business/operator/pending?user_id=${encodeURIComponent(userId)}`)
              const pd = await r.json()
              setPendingCount((pd.actions || []).length)
            } catch { setPendingCount(null) }
            setPhase('ready')
          } else {
            setErrorNote(
              d.status === 'budget_capped'
                ? "Today's operator budget is spent — the full run fires tonight at 2AM."
                : 'The first run hit a snag. Co-Founder Mode is still ON — Jarvis retries tonight at 2AM.'
            )
            setPhase('error')
          }
        }
      } catch {}
    }
    es.onerror = () => {
      // Stream dropped — the run continues server-side. Say so, don't fake it.
      es.close(); esRef.current = null
      setErrorNote('Lost the live feed, but Jarvis is still working. Your initiatives land in the Boardroom shortly.')
      setPhase('error')
    }
  }

  async function disengage() {
    try {
      await fetch(`${apiUrl}/api/business/autonomous/toggle`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, enabled: false }),
      })
      onDisengaged?.()
      onClose()
    } catch (e) { console.error('disengage failed', e) }
  }

  const canClose = phase !== 'engaging'

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        style={OVERLAY}
        onClick={() => canClose && onClose()}
      >
        <motion.div
          initial={{ scale: 0.95, y: 12, opacity: 0 }}
          animate={{ scale: 1, y: 0, opacity: 1 }}
          transition={{ type: 'spring', stiffness: 320, damping: 28 }}
          style={PANEL}
          onClick={e => e.stopPropagation()}
        >
          {/* Ambient glow sweep */}
          <div style={{
            position: 'absolute', top: -120, left: '50%', transform: 'translateX(-50%)',
            width: 380, height: 200, borderRadius: '50%',
            background: 'radial-gradient(closest-side, rgba(45,127,249,0.14), transparent)',
            pointerEvents: 'none',
          }} />

          {/* ── PHASE: LEVER ── */}
          {phase === 'lever' && (
            <div style={{ display: 'flex', gap: 30, alignItems: 'center' }}>
              <div style={{ flex: 1 }}>
                <div style={{ ...PIXEL, fontSize: 10, letterSpacing: '0.16em', color: '#2d7ff9', marginBottom: 10 }}>
                  CO-FOUNDER MODE
                </div>
                <div style={{ ...PIXEL, fontSize: 19, color: '#e8e8e8', lineHeight: 1.35, marginBottom: 14 }}>
                  Hand Jarvis the keys.
                </div>
                <div style={{ fontSize: 12.5, color: 'rgba(232,232,232,0.62)', lineHeight: 1.75, marginBottom: 14 }}>
                  From this moment, Jarvis handles every aspect of your business like a
                  co-founder — it scans everything, finds the moves, reaches out, posts,
                  creates, and takes action on your behalf.
                </div>
                <div style={{
                  fontSize: 11.5, lineHeight: 1.7,
                  borderLeft: '2px solid rgba(45,127,249,0.5)', paddingLeft: 10,
                  color: 'rgba(232,232,232,0.55)',
                }}>
                  Nothing touches the outside world without your green light.
                  You approve — Jarvis executes.
                </div>
                {!isReady && (
                  <div style={{ ...PIXEL, fontSize: 10, color: '#f5a623', marginTop: 14 }}>
                    Jarvis needs to know you better first — complete the readiness bar to unlock.
                  </div>
                )}
              </div>
              <Lever armed={isReady} onEngage={engage} />
            </div>
          )}

          {/* ── PHASE: ENGAGING (live takeover) ── */}
          {phase === 'engaging' && (
            <div>
              <div style={{ ...PIXEL, fontSize: 10, letterSpacing: '0.16em', color: '#2d7ff9', marginBottom: 8 }}>
                CO-FOUNDER MODE — ENGAGED
              </div>
              <div style={{ ...PIXEL, fontSize: 17, color: '#e8e8e8', marginBottom: 20, lineHeight: 1.4 }}>
                Jarvis is walking through your business right now.
              </div>
              {STEPS.map((s, i) => {
                const state = i < activeStep ? 'done' : i === activeStep ? 'active' : 'waiting'
                return (
                  <div key={s.id} style={{ display: 'flex', gap: 12, alignItems: 'flex-start', marginBottom: 13, opacity: state === 'waiting' ? 0.35 : 1, transition: 'opacity 400ms ease' }}>
                    <div style={{ width: 16, textAlign: 'center', flexShrink: 0, marginTop: 1 }}>
                      {state === 'done' ? (
                        <span style={{ color: '#22c55e', fontSize: 12 }}>✓</span>
                      ) : state === 'active' ? (
                        <motion.span
                          animate={{ opacity: [1, 0.3, 1] }}
                          transition={{ repeat: Infinity, duration: 1.4 }}
                          style={{ color: '#2d7ff9', fontSize: 12, display: 'inline-block' }}
                        >●</motion.span>
                      ) : (
                        <span style={{ color: 'rgba(232,232,232,0.3)', fontSize: 12 }}>○</span>
                      )}
                    </div>
                    <div>
                      <div style={{ ...PIXEL, fontSize: 12.5, color: state === 'active' ? '#e8e8e8' : 'rgba(232,232,232,0.7)' }}>
                        {s.label}
                      </div>
                      <div style={{ fontSize: 10.5, color: 'rgba(232,232,232,0.4)', marginTop: 2 }}>{s.sub}</div>
                    </div>
                  </div>
                )
              })}
              <div style={{ fontSize: 10.5, color: 'rgba(232,232,232,0.35)', marginTop: 16, lineHeight: 1.6 }}>
                This takes a few minutes. You can keep working — the Boardroom fills up when it's done.
              </div>
            </div>
          )}

          {/* ── PHASE: READY ── */}
          {phase === 'ready' && (
            <div style={{ textAlign: 'center', padding: '8px 0' }}>
              <motion.div
                initial={{ scale: 0.6, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
                transition={{ type: 'spring', stiffness: 260, damping: 18 }}
                style={{ fontSize: 34, marginBottom: 12 }}
              >
                🤝
              </motion.div>
              <div style={{ ...PIXEL, fontSize: 10, letterSpacing: '0.16em', color: '#22c55e', marginBottom: 10 }}>
                YOUR CO-FOUNDER IS ON THE JOB
              </div>
              <div style={{ ...PIXEL, fontSize: 18, color: '#e8e8e8', lineHeight: 1.45, marginBottom: 8 }}>
                {pendingCount != null && pendingCount > 0
                  ? `${pendingCount} initiative${pendingCount === 1 ? '' : 's'} ready for your approval.`
                  : 'First initiatives are landing now.'}
              </div>
              <div style={{ fontSize: 12, color: 'rgba(232,232,232,0.55)', lineHeight: 1.7, marginBottom: 22 }}>
                Real moves on your real data — each one shows exactly what Jarvis
                will do the second you approve it.
              </div>
              <button
                onClick={() => onOpenInitiatives?.()}
                style={{
                  ...PIXEL, background: '#2d7ff9', border: 'none', borderRadius: 12,
                  padding: '12px 26px', color: 'white', fontSize: 13, cursor: 'pointer',
                  boxShadow: '0 0 30px rgba(45,127,249,0.4)',
                }}
              >
                Enter the Boardroom →
              </button>
            </div>
          )}

          {/* ── PHASE: ERROR (honest, mode still on) ── */}
          {phase === 'error' && (
            <div style={{ textAlign: 'center', padding: '8px 0' }}>
              <div style={{ ...PIXEL, fontSize: 10, letterSpacing: '0.16em', color: '#f5a623', marginBottom: 12 }}>
                CO-FOUNDER MODE IS ON
              </div>
              <div style={{ fontSize: 12.5, color: 'rgba(232,232,232,0.65)', lineHeight: 1.75, marginBottom: 20 }}>
                {errorNote}
              </div>
              <button
                onClick={onClose}
                style={{
                  ...PIXEL, background: 'transparent', border: '1px solid rgba(232,232,232,0.18)',
                  borderRadius: 12, padding: '10px 22px', color: 'rgba(232,232,232,0.75)',
                  fontSize: 12, cursor: 'pointer',
                }}
              >
                Got it
              </button>
            </div>
          )}

          {/* ── PHASE: MANAGE (already engaged) ── */}
          {phase === 'manage' && (
            <div>
              <div style={{ ...PIXEL, fontSize: 10, letterSpacing: '0.16em', color: '#22c55e', marginBottom: 10 }}>
                CO-FOUNDER MODE — ACTIVE
              </div>
              <div style={{ ...PIXEL, fontSize: 17, color: '#e8e8e8', lineHeight: 1.4, marginBottom: 8 }}>
                Jarvis is operating your business.
              </div>
              <div style={{ fontSize: 12, color: 'rgba(232,232,232,0.55)', lineHeight: 1.7, marginBottom: 22 }}>
                It scans nightly, prepares the moves, and executes the ones you approve.
              </div>
              <div style={{ display: 'flex', gap: 10, justifyContent: 'center' }}>
                <button
                  onClick={() => onOpenInitiatives?.()}
                  style={{
                    ...PIXEL, background: '#2d7ff9', border: 'none', borderRadius: 12,
                    padding: '11px 20px', color: 'white', fontSize: 12, cursor: 'pointer',
                  }}
                >
                  Open the Boardroom →
                </button>
                <button
                  onClick={disengage}
                  style={{
                    ...PIXEL, background: 'transparent', border: '1px solid rgba(239,68,68,0.35)',
                    borderRadius: 12, padding: '11px 18px', color: '#ef4444', fontSize: 12, cursor: 'pointer',
                  }}
                >
                  Disengage
                </button>
              </div>
            </div>
          )}

          {canClose && phase !== 'ready' && phase !== 'error' && (
            <button
              onClick={onClose}
              aria-label="Close"
              style={{
                position: 'absolute', top: 14, right: 16, background: 'transparent',
                border: 'none', color: 'rgba(232,232,232,0.4)', fontSize: 18, cursor: 'pointer',
              }}
            >
              ×
            </button>
          )}
        </motion.div>
      </motion.div>
    </AnimatePresence>
  )
}
