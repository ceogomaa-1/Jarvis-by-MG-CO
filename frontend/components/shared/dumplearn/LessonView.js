'use client'

import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import ComprehensionKnob, { LEVELS } from './ComprehensionKnob'
import ConceptMap from './ConceptMap'
import { getBin, explainBin, askBin } from '../../../lib/dumpLearnApi'
import { createStudyNote, listStudyNotes } from '../../../lib/studyApi'

// ─────────────────────────────────────────────────────────────────────────────
// Act 3 — The Lesson. A structured document, not chat bubbles: TL;DR, concept
// blocks (with analogy/nuance callouts), a linked mind map, a self-check quiz,
// and a scoped follow-up chat dock. Re-twisting the knob re-explains from the
// already-condensed material only — never re-parses the source.
// ─────────────────────────────────────────────────────────────────────────────

const CREAM = '#F3EAD9'
const ACCENT = '#ff9072'

// Wraps a piece of the lesson so it fades/slides up on its own beat instead of
// the whole page popping in at once — "laid down" rather than "slapped down".
function Reveal({ index = 0, children }) {
  return (
    <div style={{ animation: 'dlReveal 480ms cubic-bezier(.22,1,.36,1) both', animationDelay: `${Math.min(index, 10) * 90}ms` }}>
      {children}
    </div>
  )
}

const THINKING_PHRASES = [
  'Reading everything in the bin…',
  'Connecting the concepts…',
  'Choosing the clearest way to explain it…',
  'Laying out the lesson…',
]

function ThinkingIndicator({ fixedLabel }) {
  const [phraseIdx, setPhraseIdx] = useState(0)
  useEffect(() => {
    if (fixedLabel) return
    const id = setInterval(() => setPhraseIdx(i => (i + 1) % THINKING_PHRASES.length), 1900)
    return () => clearInterval(id)
  }, [fixedLabel])
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 14, padding: '70px 0', color: 'rgba(243,234,217,0.6)', fontFamily: 'var(--sans)' }}>
      <div style={{ display: 'flex', gap: 6 }}>
        {[0, 1, 2].map(i => (
          <span
            key={i}
            style={{ width: 8, height: 8, borderRadius: '50%', background: ACCENT, animation: 'dlBounce 1.1s ease-in-out infinite', animationDelay: `${i * 0.15}s` }}
          />
        ))}
      </div>
      <div style={{ fontSize: 13.5, minHeight: 20, textAlign: 'center', transition: 'opacity 200ms ease' }}>
        {fixedLabel || THINKING_PHRASES[phraseIdx]}
      </div>
      <style>{`
        @keyframes dlBounce { 0%, 80%, 100% { transform: translateY(0); opacity: 0.5; } 40% { transform: translateY(-7px); opacity: 1; } }
        @keyframes dlReveal { 0% { opacity: 0; transform: translateY(14px); } 100% { opacity: 1; transform: translateY(0); } }
      `}</style>
    </div>
  )
}

// Flattens a lesson into the same markdown-note shape Study Mode already
// stores (study_notes.content) so a saved lesson shows up exactly like any
// other captured note — same drawer, same subject folders.
function lessonToMarkdown(lesson, title) {
  const parts = [`# ${title || 'Dump Learn lesson'}`]
  if (lesson.tldr) parts.push(lesson.tldr)
  for (const s of lesson.sections || []) {
    parts.push(`## ${s.heading || ''}\n\n${s.body_md || ''}`)
    if (s.callout_text) parts.push(`> ${s.callout_text}`)
  }
  if (lesson.quiz?.length) {
    parts.push('## Check yourself')
    parts.push(lesson.quiz.map(q => `- **Q:** ${q.question}\n  **A:** ${q.answer}`).join('\n'))
  }
  return parts.join('\n\n')
}

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

  const [revealKey, setRevealKey] = useState(0)
  const sectionRefs = useRef([])
  const questionRef = useRef(null)

  // Save-to-folder — reuses Study Mode's existing study_notes/category system
  // (the same subject folders shown in the Study drawer), not a new store.
  const [saveMenuOpen, setSaveMenuOpen] = useState(false)
  const [categories, setCategories] = useState([])
  const [newCategory, setNewCategory] = useState('')
  const [saving, setSaving] = useState(false)
  const [savedFlash, setSavedFlash] = useState(false)

  const handleQuestionChange = (e) => {
    setQuestion(e.target.value)
    const ta = e.target
    ta.style.height = 'auto'
    ta.style.height = Math.min(ta.scrollHeight, 160) + 'px'
    ta.style.overflowY = ta.scrollHeight > 160 ? 'auto' : 'hidden'
  }

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
        setRevealKey(k => k + 1) // forces the lesson subtree to remount so the staggered reveal replays
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

  const openSaveMenu = async () => {
    setSaveMenuOpen(true)
    try {
      const notes = await listStudyNotes(userId)
      const cats = [...new Set(notes.map(n => n.category || 'General'))].sort((a, b) => a.localeCompare(b))
      setCategories(cats)
    } catch { /* best-effort — the free-text field still works without this */ }
  }

  const saveToFolder = async (category) => {
    const cat = (category || newCategory || 'General').trim() || 'General'
    if (!lesson || saving) return
    setSaving(true)
    try {
      const title = items[0]?.source_name || 'Dump Learn lesson'
      await createStudyNote(userId, lessonToMarkdown(lesson, title), cat)
      setSaveMenuOpen(false)
      setNewCategory('')
      setSavedFlash(true)
      setTimeout(() => setSavedFlash(false), 2400)
    } catch (e) {
      console.error('[DumpLearn] save to folder failed', e)
    } finally {
      setSaving(false)
    }
  }

  const submitQuestion = async () => {
    const q = question.trim()
    if (!q || asking) return
    setQuestion('')
    if (questionRef.current) questionRef.current.style.height = 'auto'
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
      <div style={{ flexShrink: 0, borderBottom: '1px solid rgba(255,255,255,0.08)', padding: '12px 16px', position: 'relative' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
          <button onClick={onClose} aria-label="close" style={{ background: 'none', border: 0, color: CREAM, cursor: 'pointer', fontSize: 20, padding: 6 }}>✕</button>
          <ComprehensionKnob level={level} onChange={setLevel} mini disabled={loading} />
          <button
            onClick={openSaveMenu}
            disabled={!lesson}
            title="Save this lesson to a subject folder"
            style={{
              background: 'none', border: '1px solid rgba(255,255,255,0.14)', borderRadius: 999,
              padding: '6px 12px', color: lesson ? CREAM : 'rgba(243,234,217,0.3)',
              cursor: lesson ? 'pointer' : 'default', fontFamily: 'var(--sans)', fontSize: 12.5,
              display: 'flex', alignItems: 'center', gap: 6, whiteSpace: 'nowrap',
            }}
          >
            {savedFlash ? '✓ Saved' : '💾 Save'}
          </button>
        </div>

        {saveMenuOpen && (
          <div onClick={() => setSaveMenuOpen(false)} style={{ position: 'fixed', inset: 0, zIndex: 40, background: 'rgba(0,0,0,0.5)' }}>
            <div
              onClick={e => e.stopPropagation()}
              style={{
                position: 'absolute', top: 56, right: 16, width: 260, background: '#242424',
                border: '1px solid rgba(255,255,255,0.1)', borderRadius: 14, padding: 14,
                animation: 'fadeUp 160ms ease both', boxShadow: '0 10px 28px rgba(0,0,0,0.4)',
              }}
            >
              <div style={{ fontFamily: 'var(--sans)', fontSize: 13, fontWeight: 700, color: CREAM, marginBottom: 10 }}>
                Save to which subject?
              </div>
              {categories.length > 0 && (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 10 }}>
                  {categories.map(cat => (
                    <button
                      key={cat}
                      onClick={() => saveToFolder(cat)}
                      disabled={saving}
                      style={{
                        padding: '5px 10px', borderRadius: 999, border: '1px solid rgba(255,144,114,0.35)',
                        background: 'rgba(255,144,114,0.1)', color: CREAM, fontFamily: 'var(--sans)',
                        fontSize: 12, cursor: saving ? 'default' : 'pointer',
                      }}
                    >{cat}</button>
                  ))}
                </div>
              )}
              <div style={{ display: 'flex', gap: 6 }}>
                <input
                  value={newCategory}
                  onChange={e => setNewCategory(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') saveToFolder() }}
                  placeholder="New subject name…"
                  style={{ flex: 1, padding: '8px 10px', borderRadius: 9, background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.14)', color: CREAM, fontFamily: 'var(--sans)', fontSize: 12.5, outline: 'none' }}
                />
                <button
                  onClick={() => saveToFolder()}
                  disabled={saving}
                  style={{ padding: '8px 14px', borderRadius: 9, border: 0, background: ACCENT, color: '#1A1A1A', fontFamily: 'var(--sans)', fontSize: 12.5, fontWeight: 700, cursor: saving ? 'default' : 'pointer' }}
                >{saving ? '…' : 'Save'}</button>
              </div>
            </div>
          </div>
        )}
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
            <ThinkingIndicator fixedLabel={lesson ? `Re-explaining as ${currentLevelMeta?.label}…` : null} />
          )}

          {error && !loading && (
            <div style={{ padding: 16, borderRadius: 12, background: 'rgba(90,0,0,0.25)', border: '1px solid rgba(239,68,68,0.4)', color: CREAM, fontFamily: 'var(--sans)', fontSize: 13.5 }}>
              {error}
            </div>
          )}

          {lesson && !error && !loading && (
            <div key={revealKey}>
              {/* TL;DR */}
              {lesson.tldr && (
                <Reveal index={0}>
                  <div style={{ padding: '14px 16px', borderRadius: 14, background: 'rgba(255,144,114,0.08)', border: '1px solid rgba(255,144,114,0.25)', marginBottom: 18 }}>
                    <div style={{ fontSize: 10.5, letterSpacing: '0.08em', color: ACCENT, fontWeight: 700, marginBottom: 5 }}>TL;DR</div>
                    <div style={{ fontFamily: 'var(--sans)', fontSize: 14.5, lineHeight: 1.55, color: CREAM }}>{lesson.tldr}</div>
                  </div>
                </Reveal>
              )}

              {/* View toggle */}
              {lesson.mind_map && (
                <Reveal index={1}>
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
                </Reveal>
              )}

              {viewMode === 'map' && lesson.mind_map ? (
                <Reveal index={2}>
                  <ConceptMap mindMap={lesson.mind_map} onNodeClick={jumpToNode} />
                </Reveal>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                  {(lesson.sections || []).map((s, idx) => (
                    <Reveal key={idx} index={idx + 2}>
                      <div
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
                    </Reveal>
                  ))}
                </div>
              )}

              {/* Quiz */}
              {lesson.quiz?.length > 0 && (
                <Reveal index={(lesson.sections?.length || 0) + 3}>
                  <div style={{ marginTop: 26 }}>
                    <div style={{ fontFamily: 'var(--sans)', fontSize: 13, fontWeight: 700, color: 'rgba(243,234,217,0.6)', letterSpacing: '0.04em', marginBottom: 10 }}>
                      CHECK YOURSELF
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                      {lesson.quiz.map((q, i) => <QuizCard key={i} q={q} />)}
                    </div>
                  </div>
                </Reveal>
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
        <div style={{ maxWidth: 640, margin: '0 auto', display: 'flex', gap: 8, alignItems: 'flex-end' }}>
          <textarea
            ref={questionRef}
            value={question}
            onChange={handleQuestionChange}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submitQuestion() } }}
            placeholder="Ask about anything here, or say 'go deeper on X'…"
            rows={1}
            style={{
              flex: 1, padding: '12px 14px', borderRadius: 20, background: 'rgba(255,255,255,0.06)',
              border: '1px solid rgba(255,255,255,0.14)', color: CREAM, fontFamily: 'var(--sans)',
              fontSize: 13.5, outline: 'none', resize: 'none', overflowY: 'hidden', maxHeight: 160,
              lineHeight: 1.4,
            }}
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
