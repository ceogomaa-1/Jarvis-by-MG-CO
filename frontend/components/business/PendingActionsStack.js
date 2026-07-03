'use client'
import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { motion } from 'framer-motion'

// ─────────────────────────────────────────────────────────────────────
// Batch 71 — THE BOARDROOM.
//
// Initiatives from your co-founder. Each card is a contract: it shows the
// WHY, the expected impact, and the exact steps Jarvis will run. Tap
// Approve → the Executor agent runs it FOR REAL — and the receipts (what
// actually got sent/posted/updated) land back on the card.
// ─────────────────────────────────────────────────────────────────────

const BACKEND = 'https://jarvis-backend-4oz6.onrender.com'
const PIXEL = { fontFamily: 'var(--pixel)' }
const POLL_MS = 3000

const ACTION_TYPE_LABELS = {
  email_draft: '📧 Email',
  sms_draft: '💬 SMS',
  landing_page: '🌐 Landing Page',
  campaign_bundle: '📦 Campaign',
  report: '📊 Report',
  analysis: '🔍 Analysis',
  research_brief: '📰 Research',
  strategy_doc: '🗺️ Strategy',
  outreach_sequence: '📨 Outreach',
  crm_update: '🗂️ CRM',
  social_posts: '📣 Social',
}

const GLASS_OVERLAY = {
  position: 'fixed', inset: 0, zIndex: 1100,
  background: 'rgba(0,0,0,0.6)',
  backdropFilter: 'blur(8px)',
  WebkitBackdropFilter: 'blur(8px)',
  display: 'flex', alignItems: 'center', justifyContent: 'center',
}

const GLASS_PANEL = {
  width: '100%', maxWidth: 760, margin: '0 20px',
  background: 'rgba(15, 15, 18, 0.6)',
  backdropFilter: 'blur(30px) saturate(180%)',
  WebkitBackdropFilter: 'blur(30px) saturate(180%)',
  border: '1px solid rgba(244,244,242,0.14)',
  borderRadius: 22, padding: 28,
  boxShadow: '0 26px 70px rgba(0,0,0,0.55), inset 0 1px 0 rgba(244,244,242,0.06)',
  maxHeight: '90vh', display: 'flex', flexDirection: 'column',
}

function Chip({ children, color = 'rgba(244,244,242,0.5)', border = 'rgba(244,244,242,0.18)' }) {
  return (
    <span style={{
      ...PIXEL, fontSize: 9, fontWeight: 700, letterSpacing: '0.08em',
      color, border: `1px solid ${border}`,
      padding: '2px 7px', borderRadius: 4, textTransform: 'uppercase', whiteSpace: 'nowrap',
    }}>
      {children}
    </span>
  )
}

function Receipts({ result }) {
  if (!result) return null
  const lines = (result.summary || '').split('\n').filter(Boolean)
  const receipts = result.receipts || []
  return (
    <div style={{
      marginTop: 12, padding: '12px 14px', borderRadius: 10,
      background: 'rgba(34,197,94,0.05)', border: '1px solid rgba(34,197,94,0.18)',
    }}>
      <div style={{ ...PIXEL, fontSize: 9, letterSpacing: '0.1em', color: '#22c55e', marginBottom: 8 }}>
        RECEIPTS — WHAT JARVIS ACTUALLY DID
      </div>
      {lines.map((l, i) => (
        <div key={i} style={{ fontSize: 12, color: 'rgba(244,244,242,0.8)', lineHeight: 1.6 }}>
          {l.replace(/^(DONE|FAILED)\s*$/i, '')}
        </div>
      ))}
      {receipts.length > 0 && (
        <div style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {receipts.map((r, i) => (
            <span key={i} title={r.note} style={{
              fontSize: 10, color: r.ok ? 'rgba(34,197,94,0.85)' : 'rgba(245,166,35,0.9)',
              border: `1px solid ${r.ok ? 'rgba(34,197,94,0.3)' : 'rgba(245,166,35,0.35)'}`,
              borderRadius: 5, padding: '2px 7px',
            }}>
              {r.ok ? '✓' : '⚠'} {r.tool}
            </span>
          ))}
        </div>
      )}
      {typeof result.cost_usd === 'number' && (
        <div style={{ fontSize: 9.5, color: 'rgba(244,244,242,0.3)', marginTop: 8 }}>
          execution cost ${result.cost_usd.toFixed(3)}
        </div>
      )}
    </div>
  )
}

function QuestionCard({ q, onAnswer, onDismiss }) {
  const [answer, setAnswer] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit() {
    if (!answer.trim() || busy) return
    setBusy(true)
    await onAnswer(q.id, answer.trim())
    setBusy(false)
  }

  return (
    <div style={{
      border: '1px solid rgba(168,116,255,0.25)',
      background: 'rgba(168,116,255,0.05)',
      borderRadius: 12, marginBottom: 10, padding: '13px 15px',
    }}>
      <div style={{ ...PIXEL, fontSize: 12.5, color: '#f4f4f2', lineHeight: 1.55 }}>
        {q.question}
      </div>
      {q.why_it_matters && (
        <div style={{ fontSize: 10.5, color: 'rgba(244,244,242,0.5)', marginTop: 5, lineHeight: 1.6 }}>
          Why: {q.why_it_matters}
        </div>
      )}
      {q.unlocks && (
        <div style={{ fontSize: 10.5, color: 'rgba(168,116,255,0.85)', marginTop: 3, lineHeight: 1.6 }}>
          🔓 {q.unlocks}
        </div>
      )}
      <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
        <input
          value={answer}
          onChange={e => setAnswer(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') submit() }}
          placeholder="Your answer — Jarvis remembers it forever"
          style={{
            flex: 1, background: 'rgba(244,244,242,0.05)',
            border: '1px solid rgba(244,244,242,0.12)', borderRadius: 8,
            padding: '8px 12px', color: '#f4f4f2', fontSize: 12, outline: 'none',
          }}
        />
        <button
          onClick={submit}
          disabled={busy || !answer.trim()}
          style={{
            ...PIXEL, background: answer.trim() ? '#a874ff' : 'rgba(168,116,255,0.25)',
            border: 'none', borderRadius: 8, padding: '8px 16px',
            color: 'white', fontSize: 11, cursor: answer.trim() ? 'pointer' : 'default',
          }}
        >
          {busy ? '…' : 'Answer'}
        </button>
        <button
          onClick={() => onDismiss(q.id)}
          title="Skip this question"
          style={{
            background: 'transparent', border: '1px solid rgba(244,244,242,0.12)',
            borderRadius: 8, padding: '8px 10px', color: 'rgba(244,244,242,0.45)',
            fontSize: 11, cursor: 'pointer',
          }}
        >
          skip
        </button>
      </div>
    </div>
  )
}

function InitiativeCard({ action, onApprove, onMarkDone, onDecline, onExpand, expanded }) {
  const [declining, setDeclining] = useState(false)
  const [reason, setReason] = useState('')

  const plan = action.execution_plan || {}
  const isAuto = plan.mode === 'auto' && (plan.steps || []).length > 0
  const isExternal = action.internal_or_external === 'external'
  const typeLabel = ACTION_TYPE_LABELS[action.action_type] || action.action_type
  const executing = action.status === 'executing' || action._executing
  const executed = action.status === 'executed'
  const failed = action.status === 'execution_failed'

  return (
    <div style={{
      border: `1px solid ${executed ? 'rgba(34,197,94,0.25)' : failed ? 'rgba(245,166,35,0.3)' : 'rgba(244,244,242,0.09)'}`,
      borderRadius: 12, marginBottom: 10, overflow: 'hidden',
      background: 'rgba(244,244,242,0.02)',
    }}>
      {/* Header */}
      <div
        onClick={onExpand}
        style={{
          display: 'flex', alignItems: 'flex-start', gap: 12,
          padding: '13px 15px', cursor: 'pointer',
          background: expanded ? 'rgba(244,244,242,0.03)' : 'transparent',
        }}
      >
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', marginBottom: 6 }}>
            <Chip>{typeLabel}</Chip>
            {isAuto
              ? <Chip color="#ff2e51" border="rgba(255,46,81,0.45)">⚡ Jarvis executes</Chip>
              : <Chip color="rgba(244,244,242,0.45)" border="rgba(244,244,242,0.2)">manual</Chip>}
            {isExternal && <Chip color="#f5a623" border="rgba(245,166,35,0.4)">external</Chip>}
            {executing && <Chip color="#ff2e51" border="rgba(255,46,81,0.45)">executing…</Chip>}
            {executed && <Chip color="#22c55e" border="rgba(34,197,94,0.4)">done</Chip>}
            {failed && <Chip color="#f5a623" border="rgba(245,166,35,0.4)">needs attention</Chip>}
          </div>
          <div style={{ ...PIXEL, fontSize: 13.5, color: '#f4f4f2', lineHeight: 1.45 }}>
            {action.title}
          </div>
          {action.description && (
            <div style={{ fontSize: 11.5, color: 'rgba(244,244,242,0.55)', marginTop: 4, lineHeight: 1.55 }}>
              {action.description}
            </div>
          )}
          {action.expected_impact && (
            <div style={{ fontSize: 11, color: 'rgba(34,197,94,0.8)', marginTop: 5 }}>
              ↗ {action.expected_impact}
            </div>
          )}
        </div>
        <span style={{ fontSize: 11, color: 'rgba(244,244,242,0.35)', flexShrink: 0, marginTop: 2 }}>
          {expanded ? '▲' : '▼'}
        </span>
      </div>

      {/* Expanded body */}
      {expanded && (
        <div style={{ borderTop: '1px solid rgba(244,244,242,0.06)', padding: '14px 16px' }}>
          {isAuto && (plan.steps || []).length > 0 && !executed && (
            <div style={{
              marginBottom: 14, padding: '12px 14px', borderRadius: 10,
              background: 'rgba(255,46,81,0.05)', border: '1px solid rgba(255,46,81,0.18)',
            }}>
              <div style={{ ...PIXEL, fontSize: 9, letterSpacing: '0.1em', color: '#ff2e51', marginBottom: 8 }}>
                WHEN YOU APPROVE, JARVIS WILL:
              </div>
              {plan.steps.map((s, i) => (
                <div key={i} style={{ display: 'flex', gap: 8, fontSize: 12, color: 'rgba(244,244,242,0.75)', lineHeight: 1.7 }}>
                  <span style={{ color: 'rgba(255,46,81,0.7)', flexShrink: 0 }}>{i + 1}.</span>
                  <span>{s}</span>
                </div>
              ))}
            </div>
          )}

          {/* The work itself */}
          {action.artifact_markdown && (
            <details style={{ marginBottom: 4 }}>
              <summary style={{
                ...PIXEL, fontSize: 10, color: 'rgba(244,244,242,0.5)',
                cursor: 'pointer', letterSpacing: '0.06em', marginBottom: 8,
              }}>
                VIEW THE WORK
              </summary>
              <div className="biz-markdown" style={{ fontSize: 12.5, color: 'rgba(244,244,242,0.8)', lineHeight: 1.7, marginTop: 8 }}>
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {action.artifact_markdown}
                </ReactMarkdown>
              </div>
            </details>
          )}

          {/* Live executing state */}
          {executing && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 12 }}>
              <motion.span
                animate={{ opacity: [1, 0.25, 1] }}
                transition={{ repeat: Infinity, duration: 1.2 }}
                style={{ color: '#ff2e51', fontSize: 13 }}
              >●</motion.span>
              <span style={{ ...PIXEL, fontSize: 11.5, color: 'rgba(244,244,242,0.75)' }}>
                Jarvis is executing this right now…
              </span>
            </div>
          )}

          {/* Receipts */}
          {(executed || failed) && <Receipts result={action.execution_result} />}
          {failed && (
            <div style={{ fontSize: 11, color: 'rgba(245,166,35,0.85)', marginTop: 8, lineHeight: 1.6 }}>
              You can approve again to retry, or decline it.
            </div>
          )}

          {/* Decline flow */}
          {declining && !executing && !executed && (
            <div style={{ marginTop: 12, display: 'flex', gap: 8 }}>
              <input
                value={reason}
                onChange={e => setReason(e.target.value)}
                placeholder="Why not? (optional — Jarvis learns from this)"
                autoFocus
                style={{
                  flex: 1, background: 'rgba(244,244,242,0.05)',
                  border: '1px solid rgba(244,244,242,0.12)', borderRadius: 8,
                  padding: '8px 12px', color: '#f4f4f2', fontSize: 12, outline: 'none',
                }}
              />
              <button
                onClick={() => onDecline(action.id, reason)}
                style={{
                  background: 'rgba(239,68,68,0.12)', border: '1px solid rgba(239,68,68,0.35)',
                  borderRadius: 8, padding: '8px 14px', color: '#ef4444', fontSize: 11,
                  cursor: 'pointer', ...PIXEL,
                }}
              >
                Decline
              </button>
            </div>
          )}

          {/* Actions */}
          {!executing && !executed && !declining && (
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 14 }}>
              <button
                onClick={() => setDeclining(true)}
                style={{
                  background: 'transparent', border: '1px solid rgba(239,68,68,0.3)',
                  borderRadius: 8, padding: '8px 14px', color: '#ef4444',
                  fontSize: 11, cursor: 'pointer', ...PIXEL,
                }}
              >
                Not this
              </button>
              {isAuto ? (
                <button
                  onClick={() => onApprove(action.id)}
                  style={{
                    background: '#ff2e51', border: 'none', borderRadius: 8,
                    padding: '8px 18px', color: 'white', fontSize: 11.5, fontWeight: 600,
                    cursor: 'pointer', ...PIXEL, boxShadow: '0 0 18px rgba(255,46,81,0.35)',
                  }}
                >
                  ⚡ Approve — Jarvis executes
                </button>
              ) : (
                <button
                  onClick={() => onMarkDone(action.id)}
                  style={{
                    background: 'rgba(34,197,94,0.14)', border: '1px solid rgba(34,197,94,0.4)',
                    borderRadius: 8, padding: '8px 16px', color: '#22c55e', fontSize: 11.5,
                    cursor: 'pointer', ...PIXEL,
                  }}
                >
                  ✓ Mark done
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function PendingActionsStack({ open, onClose, userId }) {
  const [tab, setTab] = useState('approvals')  // 'approvals' | 'done'
  const [actions, setActions] = useState([])
  const [activity, setActivity] = useState([])
  const [questions, setQuestions] = useState([])
  const [loading, setLoading] = useState(true)
  const [expandedId, setExpandedId] = useState(null)
  const pollRef = useRef(null)

  async function loadQuestions() {
    try {
      const res = await fetch(`${BACKEND}/api/business/cofounder/questions?user_id=${encodeURIComponent(userId || '')}`)
      const data = await res.json()
      setQuestions(data.questions || [])
    } catch (e) { console.error('Boardroom questions load failed', e) }
  }

  async function answerQuestion(id, answer) {
    try {
      await fetch(`${BACKEND}/api/business/cofounder/questions/${id}/answer`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, answer }),
      })
      setQuestions(prev => prev.filter(q => q.id !== id))
    } catch (e) { console.error('Answer failed', e) }
  }

  async function dismissQuestion(id) {
    try {
      await fetch(`${BACKEND}/api/business/cofounder/questions/${id}/dismiss`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId }),
      })
      setQuestions(prev => prev.filter(q => q.id !== id))
    } catch (e) { console.error('Dismiss failed', e) }
  }

  async function loadApprovals() {
    try {
      const res = await fetch(`${BACKEND}/api/business/operator/pending?user_id=${encodeURIComponent(userId || '')}`)
      const data = await res.json()
      setActions(prev => {
        const next = data.actions || []
        // keep locally-known terminal states (receipts) for cards still in view
        return next.map(n => prev.find(p => p.id === n.id && (p.status === 'executed' || p.status === 'execution_failed')) || n)
      })
    } catch (e) { console.error('Boardroom load failed', e) }
  }

  async function loadActivity() {
    try {
      const res = await fetch(`${BACKEND}/api/business/operator/activity?user_id=${encodeURIComponent(userId || '')}`)
      const data = await res.json()
      setActivity(data.actions || [])
    } catch (e) { console.error('Boardroom activity load failed', e) }
  }

  useEffect(() => {
    if (!open || !userId) return
    setLoading(true)
    Promise.all([loadApprovals(), loadActivity(), loadQuestions()]).finally(() => setLoading(false))
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [open, userId]) // eslint-disable-line react-hooks/exhaustive-deps

  // Poll any executing card until it lands, then show the receipts in place.
  useEffect(() => {
    if (!open) return
    const executing = actions.filter(a => a.status === 'executing' || a._executing)
    if (executing.length === 0) {
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
      return
    }
    if (pollRef.current) return
    pollRef.current = setInterval(async () => {
      for (const a of actions.filter(x => x.status === 'executing' || x._executing)) {
        try {
          const res = await fetch(`${BACKEND}/api/business/operator/actions/${a.id}?user_id=${encodeURIComponent(userId)}`)
          const data = await res.json()
          const row = data.action
          if (row && ['executed', 'execution_failed', 'shipped'].includes(row.status)) {
            setActions(prev => prev.map(p => (p.id === a.id ? { ...row, _executing: false } : p)))
            loadActivity()
          }
        } catch {}
      }
    }, POLL_MS)
    return () => { if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null } }
  }, [actions, open, userId]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!open) return null

  async function approve(id) {
    setActions(prev => prev.map(a => (a.id === id ? { ...a, status: 'executing', _executing: true } : a)))
    try {
      const res = await fetch(`${BACKEND}/api/business/operator/actions/${id}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        console.error('Approve failed', err)
        setActions(prev => prev.map(a => (a.id === id ? { ...a, status: 'pending', _executing: false } : a)))
      }
    } catch (e) {
      console.error('Approve failed', e)
      setActions(prev => prev.map(a => (a.id === id ? { ...a, status: 'pending', _executing: false } : a)))
    }
  }

  async function markDone(id) {
    try {
      await fetch(`${BACKEND}/api/business/operator/actions/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'shipped' }),
      })
      setActions(prev => prev.filter(a => a.id !== id))
      loadActivity()
    } catch (e) { console.error('Mark done failed', e) }
  }

  async function decline(id, reason) {
    try {
      await fetch(`${BACKEND}/api/business/operator/actions/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'discarded', decline_reason: reason || undefined }),
      })
      setActions(prev => prev.filter(a => a.id !== id))
    } catch (e) { console.error('Decline failed', e) }
  }

  const pendingCount = actions.filter(a => a.status === 'pending' || a.status === 'edited').length
  const list = tab === 'approvals' ? actions : activity

  return (
    <div onClick={onClose} style={GLASS_OVERLAY}>
      <motion.div
        initial={{ scale: 0.97, y: 10, opacity: 0 }}
        animate={{ scale: 1, y: 0, opacity: 1 }}
        transition={{ type: 'spring', stiffness: 320, damping: 30 }}
        onClick={e => e.stopPropagation()}
        style={GLASS_PANEL}
      >
        <div style={{ ...PIXEL, fontSize: 10, letterSpacing: '0.14em', color: '#ff2e51', marginBottom: 6 }}>
          🤝 THE BOARDROOM
        </div>
        <div style={{ ...PIXEL, fontSize: 16, color: '#f4f4f2', marginBottom: 4 }}>
          Initiatives from your co-founder
        </div>
        <div style={{ fontSize: 11.5, color: 'rgba(244,244,242,0.5)', marginBottom: 16, lineHeight: 1.6 }}>
          Every card shows exactly what Jarvis will do. Approve it — Jarvis executes it for real
          and the receipts land right here.
        </div>

        {/* Tabs */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 14 }}>
          {[
            { id: 'approvals', label: `Approvals${pendingCount ? ` (${pendingCount})` : ''}` },
            { id: 'done', label: 'Done' },
          ].map(t => (
            <button
              key={t.id}
              onClick={() => { setTab(t.id); if (t.id === 'done') loadActivity() }}
              style={{
                ...PIXEL, fontSize: 11, padding: '7px 14px', borderRadius: 8, cursor: 'pointer',
                background: tab === t.id ? 'rgba(255,46,81,0.14)' : 'transparent',
                border: `1px solid ${tab === t.id ? 'rgba(255,46,81,0.4)' : 'rgba(244,244,242,0.1)'}`,
                color: tab === t.id ? '#ff2e51' : 'rgba(244,244,242,0.55)',
              }}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div style={{ overflowY: 'auto', flex: 1, paddingRight: 4 }} className="os1-scroll">
          {/* THE DETECTIVE — questions that unlock better moves */}
          {tab === 'approvals' && !loading && questions.length > 0 && (
            <div style={{ marginBottom: 16 }}>
              <div style={{
                ...PIXEL, fontSize: 9.5, letterSpacing: '0.12em',
                color: '#a874ff', marginBottom: 8, textTransform: 'uppercase',
              }}>
                🕵️ Jarvis needs to know — {questions.length} question{questions.length === 1 ? '' : 's'}
              </div>
              {questions.map(q => (
                <QuestionCard key={q.id} q={q} onAnswer={answerQuestion} onDismiss={dismissQuestion} />
              ))}
            </div>
          )}

          {loading ? (
            <div style={{ color: 'rgba(244,244,242,0.5)', fontSize: 13, padding: 8 }}>Loading…</div>
          ) : list.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '38px 0' }}>
              <div style={{ fontSize: 12, color: 'rgba(244,244,242,0.4)', lineHeight: 1.8 }}>
                {tab === 'approvals'
                  ? 'Nothing waiting on you. Jarvis scans nightly — new initiatives land here.'
                  : 'No executed initiatives yet. Approve one and watch the receipts appear.'}
              </div>
            </div>
          ) : (
            list.map(action => (
              <InitiativeCard
                key={action.id}
                action={action}
                expanded={expandedId === action.id}
                onExpand={() => setExpandedId(expandedId === action.id ? null : action.id)}
                onApprove={approve}
                onMarkDone={markDone}
                onDecline={decline}
              />
            ))
          )}
        </div>

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 14 }}>
          <span style={{ fontSize: 10.5, color: 'rgba(244,244,242,0.35)' }}>
            {tab === 'approvals' ? `${pendingCount} waiting for your green light` : `${activity.length} on the record`}
          </span>
          <button
            onClick={onClose}
            style={{
              background: 'transparent', border: '1px solid rgba(244,244,242,0.14)',
              borderRadius: 10, padding: '8px 20px', color: 'rgba(244,244,242,0.7)',
              fontSize: 12.5, cursor: 'pointer',
            }}
          >
            Close
          </button>
        </div>
      </motion.div>
    </div>
  )
}
