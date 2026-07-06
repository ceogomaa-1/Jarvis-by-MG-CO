'use client'

import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import ComprehensionKnob, { LEVELS } from './ComprehensionKnob'
import ConceptMap from './ConceptMap'
import { getBin, explainBin, askBin } from '../../../lib/dumpLearnApi'

// ─────────────────────────────────────────────────────────────────────────────
// Act 3 — The Lesson. A structured document, not chat bubbles: TL;DR, concept
// blocks (with analogy/nuance callouts), a linked mind map, a self-check quiz,
// and a scoped follow-up chat dock. Re-twisting the knob re-explains from the
// already-condensed material only — never re-parses the source.
// ─────────────────────────────────────────────────────────────────────────────

const CREAM = '#F3EAD9'
const ACCENT = '#ff9072'

function CalloutBox({ type, text }) {
  if (!text) return null
  const isAnalogy = type === 'analogy'
  return (
    <div style={{
      marginTop: 10, padding: '10px 13px', borderRadius: 12,
      background: isAnalogy ? 'rgba(255,194,102,0.08)' : 'rgba(122,162,255,0.08)',
      border: `1px solid ${isAnalogy ? 'rgba(255,194,102,0.3)' : 'rgba(122,162,255,0.3)'}`,
      fontFamily: 'var(--sans)', fontSize: 13, lineHeight: 1.5, color: CREAM,
    }}>
      <span style={{ marginRight: 6 }}>{isAnalogy ? '👉' : '🔍'}</span>{text}
    </div>
  )
}

function QuizCard({ q }) {
  const [flipped, setFlipped] = useState(false)
  return (
    <div
      onClick={() => setFlipped(f => !f)}
      style={{
        cursor: 'pointer', padding: '14px 16px', borderRadius: 14,
        background: flipped ? 'rgba(255,144,114,0.08)' : 'rgba(255,255,255,0.04)',
        border: '1px solid rgba(255,255,255,0.09)', transition: 'background 180ms ease',
        fontFamily: 'var(--sans)',
      }}
    >
      <div style={{ fontSize: 11, color: 'rgba(243,234,217,0.45)', marginBottom: 4 }}>
        {flipped ? 'ANSWER — tap to hide' : 'QUESTION — tap to reveal'}
      </div>
      <div style={{ fontSize: 14, color: CREAM, lineHeight: 1.5 }}>
        {flipped ? q.answer : q.question}
      </div>
    </div>
  )
}

export default function LessonView({ userId, binId, initialLevel, onClose }) {
  const [level, setLevel] = useState(initialLevel || 'graduate')
  const [lesson, setLesson] = useState(null)
  const [cached, setCached] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [viewMode, setViewMode] = useState('blocks') // 'blocks' | 'map'
  const [activeSection, setActiveSection] = useState(-1)
  const [items, setItems] = useState([])
  const [question, setQuestion] = useState('')
  const [followups, setFollowups] = useState([])
  const [asking, setAsking] = useState(false)

  const sectionRefs = useRef([])

  useEffect(() => {
    getBin(userId, binId).then(d => setItems(d.items || [])).catch(() => {})
  }, [userId, binId])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    explainBin(userId, binId, level)
      .then(res => {
        if (cancelled) return
        setLesson(res.lesson)
        setCached(res.cached)
      })
      .catch(e => { if (!cancelled) setError(e.message || 'Could not generate this lesson.') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [userId, binId, level])

  const totalTokens = items.reduce((s, i) => s + (i.token_estimate || 0), 0)
  const currentLevelMeta = LEVELS.find(l => l.key === level)

  const jumpToNode = (nodeId) => {
    const node = (lesson?.mind_map?.nodes || []).find(n => n.id === nodeId)
    if (!node) return
    const label = (node.label || '').toLowerCase()
    const idx = (lesson?.sections || []).findIndex(s => {
      const h = (s.heading || '').toLowerCase()
      return h && label && (h.includes(label) || label.includes(h))
    })
    if (idx >= 0) {
      setViewMode('blocks')
      setActiveSection(idx)
      setTimeout(() => {
        sectionRefs.current[idx]?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      }, 60)
      setTimeout(() => setActiveSection(-1), 2200)
    }
  }

  const submitQuestion = async () => {
    const q = question.trim()
    if (!q || asking) return
    setQuestion('')
    setAsking(true)
    setFollowups(prev => [...prev, { question: q, answer: null }])
    try {
      const res = await askBin(userId, binId, q)
      setFollowups(prev => prev.map((f, i) => (i === prev.length - 1 ? { ...f, answer: res.answer } : f)))
    } catch (e) {
      setFollowups(prev => prev.map((f, i) => (i === prev.length - 1 ? { ...f, answer: `Couldn't answer that (${e.message || 'error'}).` } : f)))
    } finally {
      setAsking(false)
    }
  }

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 30, background: '#1A1A1A', display: 'flex', flexDirection: 'column', animation: 'fadeUp 260ms ease both' }}>
      {/* Header */}
      <div style={{ flexShrink: 0, borderBottom: '1px solid rgba(255,255,255,0.08)', padding: '12px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
          <button onClick={onClose} aria-label="close" style={{ background: 'none', border: 0, color: CREAM, cursor: 'pointer', fontSize: 20, padding: 6 }}>✕</button>
          <ComprehensionKnob level={level} onChange={setLevel} mini disabled={loading} />
        </div>
        <div style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
          {items.map(it => (
            <span key={it.id} style={{ fontSize: 11, padding: '3px 9px', borderRadius: 999, background: 'rgba(255,255,255,0.06)', color: 'rgba(243,234,217,0.65)', border: '1px solid rgba(255,255,255,0.08)' }}>
              {it.source_name || it.kind}
            </span>
          ))}
          {items.length > 0 && (
            <span style={{ fontSize: 11, color: 'rgba(243,234,217,0.4)' }}>
              · Digested {items.length} source{items.length === 1 ? '' : 's'} · ~{totalTokens.toLocaleString()} tokens{cached ? ' · instant (cached)' : ''}
            </span>
          )}
        </div>
      </div>

      {/* Body */}
      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '18px 18px 100px' }}>
        <div style={{ maxWidth: 640, margin: '0 auto', position: 'relative' }}>
          {loading && (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10, padding: '60px 0', color: 'rgba(243,234,217,0.55)', fontFamily: 'var(--sans)' }}>
              <span style={{ width: 10, height: 10, borderRadius: '50%', background: ACCENT, animation: 'dlPulse 1s ease-in-out infinite' }} />
              {lesson ? `Re-explaining as ${currentLevelMeta?.label}…` : 'Digesting everything in the bin…'}
              <style>{`@keyframes dlPulse { 0%,100% { opacity: 1; } 50% { opacity: 0.3; } }`}</style>
            </div>
          )}

          {error && !loading && (
            <div style={{ padding: 16, borderRadius: 12, background: 'rgba(90,0,0,0.25)', border: '1px solid rgba(239,68,68,0.4)', color: CREAM, fontFamily: 'var(--sans)', fontSize: 13.5 }}>
              {error}
            </div>
          )}

          {lesson && !error && (
            <div style={{ opacity: loading ? 0.35 : 1, transition: 'opacity 200ms ease', pointerEvents: loading ? 'none' : 'auto' }}>
              {/* TL;DR */}
              {lesson.tldr && (
                <div style={{ padding: '14px 16px', borderRadius: 14, background: 'rgba(255,144,114,0.08)', border: '1px solid rgba(255,144,114,0.25)', marginBottom: 18 }}>
                  <div style={{ fontSize: 10.5, letterSpacing: '0.08em', color: ACCENT, fontWeight: 700, marginBottom: 5 }}>TL;DR</div>
                  <div style={{ fontFamily: 'var(--sans)', fontSize: 14.5, lineHeight: 1.55, color: CREAM }}>{lesson.tldr}</div>
                </div>
              )}

              {/* View toggle */}
              {lesson.mind_map && (
                <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
                  {['blocks', 'map'].map(mode => (
                    <button
                      key={mode}
                      onClick={() => setViewMode(mode)}
                      style={{
                        padding: '7px 14px', borderRadius: 999, border: '1px solid rgba(255,255,255,0.12)',
                        background: viewMode === mode ? ACCENT : 'transparent',
                        color: viewMode === mode ? '#1A1A1A' : CREAM,
                        fontFamily: 'var(--sans)', fontSize: 12.5, fontWeight: 600, cursor: 'pointer',
                      }}
                    >
                      {mode === 'blocks' ? '📖 Lesson' : '🕸 Mind Map'}
                    </button>
                  ))}
                </div>
              )}

              {viewMode === 'map' && lesson.mind_map ? (
                <ConceptMap mindMap={lesson.mind_map} onNodeClick={jumpToNode} />
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                  {(lesson.sections || []).map((s, idx) => (
                    <div
                      key={idx}
                      ref={el => { sectionRefs.current[idx] = el }}
                      style={{
                        padding: '14px 16px', borderRadius: 14,
                        background: activeSection === idx ? 'rgba(255,144,114,0.12)' : 'rgba(255,255,255,0.03)',
                        border: `1px solid ${activeSection === idx ? 'rgba(255,144,114,0.4)' : 'rgba(255,255,255,0.07)'}`,
                        transition: 'background 300ms ease, border-color 300ms ease',
                      }}
                    >
                      <div style={{ fontFamily: 'var(--font-display-round), var(--sans)', fontSize: 15.5, fontWeight: 600, color: CREAM, marginBottom: 6 }}>
                        {s.heading}
                      </div>
                      <div className="dl-markdown" style={{ fontFamily: 'var(--sans)', fontSize: 14, lineHeight: 1.6, color: 'rgba(243,234,217,0.9)' }}>
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{s.body_md || ''}</ReactMarkdown>
                      </div>
                      <CalloutBox type={s.callout_type} text={s.callout_text} />
                    </div>
                  ))}
                </div>
              )}

              {/* Quiz */}
              {lesson.quiz?.length > 0 && (
                <div style={{ marginTop: 26 }}>
                  <div style={{ fontFamily: 'var(--sans)', fontSize: 13, fontWeight: 700, color: 'rgba(243,234,217,0.6)', letterSpacing: '0.04em', marginBottom: 10 }}>
                    CHECK YOURSELF
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {lesson.quiz.map((q, i) => <QuizCard key={i} q={q} />)}
                  </div>
                </div>
              )}

              {/* Follow-up thread */}
              {followups.length > 0 && (
                <div style={{ marginTop: 26, display: 'flex', flexDirection: 'column', gap: 10 }}>
                  {followups.map((f, i) => (
                    <div key={i}>
                      <div style={{ fontFamily: 'var(--sans)', fontSize: 13.5, color: CREAM, fontWeight: 600 }}>{f.question}</div>
                      <div style={{ fontFamily: 'var(--sans)', fontSize: 13.5, color: 'rgba(243,234,217,0.8)', marginTop: 4, lineHeight: 1.55 }}>
                        {f.answer == null ? '…' : f.answer}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Follow-up dock */}
      <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, padding: '12px 16px', background: 'linear-gradient(0deg, #1A1A1A 60%, transparent)' }}>
        <div style={{ maxWidth: 640, margin: '0 auto', display: 'flex', gap: 8 }}>
          <input
            value={question}
            onChange={e => setQuestion(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') submitQuestion() }}
            placeholder="Ask about anything here, or say 'go deeper on X'…"
            style={{ flex: 1, padding: '12px 14px', borderRadius: 999, background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.14)', color: CREAM, fontFamily: 'var(--sans)', fontSize: 13.5, outline: 'none' }}
          />
          <button
            onClick={submitQuestion}
            disabled={asking || !question.trim()}
            style={{ width: 44, height: 44, borderRadius: '50%', border: 'none', background: ACCENT, color: '#1A1A1A', fontSize: 16, cursor: 'pointer', flexShrink: 0, opacity: asking || !question.trim() ? 0.5 : 1 }}
          >↑</button>
        </div>
      </div>
    </div>
  )
}
