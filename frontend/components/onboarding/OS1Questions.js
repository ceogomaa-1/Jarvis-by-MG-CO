'use client'
import { useState, useEffect, useRef, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'

const QUESTIONS = [
  { key: 'name', text: 'What should I call you?' },
  { key: 'industry', text: "What's your world? Pick your industry." },
  { key: 'companyName', text: "What's your business called?" },
  { key: 'mission', text: 'Anything I should know? What are we chasing together?' },
]

const INDUSTRIES = ['Restaurants', 'Real Estate', 'Dental', 'Salon/Spa', 'Trades/Contractors', 'Retail', 'Law', 'Other']

const BIBLE_FILES = {
  'Restaurants': 'restaurant.md',
  'Real Estate': 'real_estate.md',
  'Dental': 'dental.md',
  'Salon/Spa': 'salon_spa.md',
  'Trades/Contractors': 'trades_contractors.md',
  'Retail': 'retail.md',
  'Law': 'law.md',
}

function ArrowLeftIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <line x1="19" y1="12" x2="5" y2="12" />
      <polyline points="12 19 5 12 12 5" />
    </svg>
  )
}

function TypedQuestion({ text, onDone }) {
  const [typed, setTyped] = useState(0)

  useEffect(() => {
    setTyped(0)
  }, [text])

  useEffect(() => {
    if (typed >= text.length) {
      onDone?.()
      return
    }
    const t = setTimeout(() => setTyped(c => c + 1), 25)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [typed, text])

  return (
    <h2 className="font-pixel" style={{ fontSize: 'clamp(22px, 4vw, 32px)', color: '#e8e8e8', textAlign: 'center', margin: 0, lineHeight: 1.4 }}>
      {text.slice(0, typed)}
      {typed < text.length && <span className="os1-cursor" />}
    </h2>
  )
}

const inputBaseStyle = {
  width: '100%', background: 'transparent',
  border: 'none', borderBottom: '1px solid var(--os1-border)',
  borderRadius: 0, padding: '10px 4px', fontSize: 22,
  color: '#e8e8e8', fontFamily: 'var(--pixel)', outline: 'none',
  textAlign: 'center', transition: 'border-color 150ms ease',
}

function FieldInput({ inputRef, value, onChange, onKeyDown, placeholder }) {
  const [focused, setFocused] = useState(false)
  return (
    <input
      ref={inputRef}
      autoFocus
      value={value}
      onChange={e => onChange(e.target.value)}
      onKeyDown={onKeyDown}
      onFocus={() => setFocused(true)}
      onBlur={() => setFocused(false)}
      placeholder={placeholder}
      className="font-pixel"
      style={{ ...inputBaseStyle, borderBottomColor: focused ? 'var(--os1-blue)' : 'var(--os1-border)' }}
    />
  )
}

function IndustryGrid({ value, customValue, onSelect, onCustomChange, onKeyDown, customInputRef }) {
  return (
    <div style={{ width: '100%' }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 12 }}>
        {INDUSTRIES.map(ind => {
          const selected = value === ind
          return (
            <button
              key={ind}
              onClick={() => onSelect(ind)}
              className="os1-card"
              style={{
                padding: '16px 14px', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                cursor: 'pointer', textAlign: 'left',
                borderColor: selected ? 'var(--os1-blue)' : undefined,
                background: selected ? 'rgba(45,127,249,0.08)' : undefined,
              }}
            >
              <span className="font-pixel" style={{ fontSize: 14, color: selected ? '#e8e8e8' : 'var(--os1-text-dim)' }}>{ind}</span>
              {selected && <span style={{ width: 8, height: 8, background: 'var(--os1-blue)', flexShrink: 0 }} />}
            </button>
          )
        })}
      </div>
      <AnimatePresence>
        {value === 'Other' && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.25 }}
            style={{ overflow: 'hidden', marginTop: 18 }}
          >
            <FieldInput
              inputRef={customInputRef}
              value={customValue}
              onChange={onCustomChange}
              onKeyDown={onKeyDown}
              placeholder="Tell me your industry —"
            />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function continueBtnStyle(enabled) {
  return {
    background: enabled ? 'var(--os1-blue)' : 'transparent',
    border: enabled ? 'none' : '1px solid var(--os1-border)',
    borderRadius: 999,
    padding: '10px 28px',
    color: enabled ? '#fff' : 'var(--os1-text-faint)',
    cursor: enabled ? 'pointer' : 'default',
    fontFamily: 'var(--pixel)',
    fontSize: 14,
    transition: 'all 150ms ease',
  }
}

function buildIgnitionLines(answers) {
  const { industry, customIndustry } = answers
  if (industry === 'Other') {
    const label = customIndustry || 'your industry'
    return [
      { text: `no playbook on file — adaptive mode engaged for "${label}"`, status: null },
      { text: 'burying memories: name, business, mission', status: 'OK' },
      { text: `JARVIS OS1 — calibrated for "${label}"`, status: null },
    ]
  }
  const filename = BIBLE_FILES[industry] || `${industry.toLowerCase()}.md`
  return [
    { text: `locating playbook: ${filename}`, status: 'FOUND' },
    { text: 'loading: 25 industry problems', status: 'OK' },
    { text: 'loading: metrics that matter', status: 'OK' },
    { text: 'loading: risk flags', status: 'OK' },
    { text: 'loading: daily operations engine', status: 'OK' },
    { text: 'burying memories: name, business, mission', status: 'OK' },
    { text: `JARVIS OS1 — calibrated for ${industry}`, status: null },
  ]
}

function IgnitingSequence({ answers, onDone }) {
  const lines = useMemo(() => buildIgnitionLines(answers), [answers])
  const [visibleCount, setVisibleCount] = useState(0)

  useEffect(() => {
    if (visibleCount < lines.length) {
      const t = setTimeout(() => setVisibleCount(c => c + 1), 250)
      return () => clearTimeout(t)
    }
    const t = setTimeout(() => onDone?.(), 600)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visibleCount, lines])

  return (
    <div style={{ position: 'fixed', inset: 0, background: '#131313', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100, padding: 24 }}>
      <div style={{ width: '100%', maxWidth: 540, display: 'flex', flexDirection: 'column', gap: 10 }}>
        {lines.slice(0, visibleCount).map((line, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, x: -6 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.25 }}
            className="font-pixel"
            style={{ fontSize: 13, color: '#e8e8e8', display: 'flex', justifyContent: 'space-between', gap: 12 }}
          >
            <span><span style={{ color: 'var(--os1-blue)', marginRight: 8 }}>▸</span>{line.text}</span>
            {line.status && (
              <span style={{ color: line.status === 'FOUND' ? 'var(--os1-blue)' : 'var(--os1-text-dim)', flexShrink: 0 }}>[{line.status}]</span>
            )}
          </motion.div>
        ))}
      </div>
    </div>
  )
}

export default function OS1Questions({ onComplete }) {
  const [step, setStep] = useState(0)
  const [answers, setAnswers] = useState({ name: '', industry: '', customIndustry: '', companyName: '', mission: '' })
  const [igniting, setIgniting] = useState(false)
  const [questionTyped, setQuestionTyped] = useState(false)
  const inputRef = useRef(null)
  const customInputRef = useRef(null)

  useEffect(() => {
    setQuestionTyped(false)
  }, [step])

  const canAdvance = () => {
    switch (step) {
      case 0: return answers.name.trim().length > 0
      case 1: return answers.industry === 'Other' ? answers.customIndustry.trim().length > 0 : !!answers.industry
      case 2: return answers.companyName.trim().length > 0
      case 3: return true
      default: return false
    }
  }

  const next = () => {
    if (step < QUESTIONS.length - 1) {
      setStep(s => s + 1)
    } else {
      setIgniting(true)
    }
  }

  const back = () => {
    if (step > 0) setStep(s => s - 1)
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey && canAdvance()) {
      e.preventDefault()
      next()
    }
  }

  if (igniting) {
    return <IgnitingSequence answers={answers} onDone={() => onComplete(answers)} />
  }

  const q = QUESTIONS[step]
  const enabled = canAdvance()

  return (
    <div style={{
      position: 'fixed', inset: 0, background: '#131313', zIndex: 100,
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: 24,
    }}>
      {step > 0 && (
        <button
          onClick={back}
          className="os1-iconbtn"
          title="Back"
          style={{ position: 'fixed', top: 22, left: 22 }}
        >
          <ArrowLeftIcon />
        </button>
      )}

      <div style={{ position: 'fixed', top: 30, left: '50%', transform: 'translateX(-50%)', display: 'flex', gap: 10 }}>
        {QUESTIONS.map((_, i) => (
          <div
            key={i}
            style={{
              width: 8, height: 8, borderRadius: '50%',
              background: i < step ? 'var(--os1-blue)' : (i === step ? 'var(--os1-text-dim)' : 'var(--os1-border)'),
              transition: 'background 200ms ease',
            }}
          />
        ))}
      </div>

      <AnimatePresence mode="wait">
        <motion.div
          key={step}
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -12 }}
          transition={{ duration: 0.4 }}
          style={{ width: '100%', maxWidth: 560, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 32 }}
        >
          <TypedQuestion text={q.text} onDone={() => setQuestionTyped(true)} />

          {questionTyped && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.4, delay: 0.1 }}
              style={{ width: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 28 }}
            >
              {step === 0 && (
                <FieldInput
                  inputRef={inputRef}
                  value={answers.name}
                  onChange={v => setAnswers(a => ({ ...a, name: v }))}
                  onKeyDown={handleKeyDown}
                  placeholder=""
                />
              )}

              {step === 1 && (
                <IndustryGrid
                  value={answers.industry}
                  customValue={answers.customIndustry}
                  onSelect={ind => setAnswers(a => ({ ...a, industry: ind }))}
                  onCustomChange={v => setAnswers(a => ({ ...a, customIndustry: v }))}
                  onKeyDown={handleKeyDown}
                  customInputRef={customInputRef}
                />
              )}

              {step === 2 && (
                <FieldInput
                  inputRef={inputRef}
                  value={answers.companyName}
                  onChange={v => setAnswers(a => ({ ...a, companyName: v }))}
                  onKeyDown={handleKeyDown}
                  placeholder=""
                />
              )}

              {step === 3 && (
                <textarea
                  ref={inputRef}
                  autoFocus
                  rows={3}
                  value={answers.mission}
                  onChange={e => setAnswers(a => ({ ...a, mission: e.target.value }))}
                  onKeyDown={handleKeyDown}
                  placeholder="revenue goals, problems, the mission..."
                  className="font-pixel"
                  style={{
                    width: '100%', background: 'transparent',
                    border: '1px solid var(--os1-border)', borderRadius: 12,
                    padding: '14px 16px', fontSize: 15, color: '#e8e8e8',
                    fontFamily: 'var(--pixel)', outline: 'none', resize: 'none',
                  }}
                />
              )}

              <div style={{ display: 'flex', justifyContent: 'center', gap: 16 }}>
                {step === 3 ? (
                  <button onClick={next} className="font-pixel" style={continueBtnStyle(!!answers.mission.trim())}>
                    {answers.mission.trim() ? 'Continue →' : 'skip →'}
                  </button>
                ) : (
                  <button onClick={() => enabled && next()} disabled={!enabled} className="font-pixel" style={continueBtnStyle(enabled)}>
                    Continue →
                  </button>
                )}
              </div>
            </motion.div>
          )}
        </motion.div>
      </AnimatePresence>
    </div>
  )
}
