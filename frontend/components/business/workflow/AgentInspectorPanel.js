'use client'
import { motion, AnimatePresence } from 'framer-motion'
import { useRouter } from 'next/navigation'
import { X } from 'lucide-react'
import {
  Brain, Search, Sparkles, Package, Compass,
  PenTool, Palette, Telescope, BarChart3, FileText,
} from 'lucide-react'
import TetrisLoader from '../../ui/TetrisLoader'

const ICONS = { Brain, Search, Sparkles, Package, Compass, PenTool, Palette, Telescope, BarChart3, FileText }

function relativeTime(isoStr) {
  if (!isoStr) return ''
  const date = new Date(isoStr)
  const now = new Date()
  const diffMs = now - date
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMs / 3600000)
  const diffDays = Math.floor(diffMs / 86400000)
  if (diffMins < 1) return 'just now'
  if (diffMins < 60) return `${diffMins}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  if (diffDays === 1) return 'Yesterday'
  if (diffDays < 7) return `${diffDays}d ago`
  return date.toLocaleDateString()
}

export default function AgentInspectorPanel({ agent, agentActivity, activityLoading, onClose }) {
  const router = useRouter()
  const Icon = agent ? (ICONS[agent.icon] || Brain) : null

  const activity = agentActivity || {}
  const recentActivity = activity.recent_activity || []
  const lastOutput = activity.last_output || null

  function handleOpenInChat() {
    const msg = `Show me the latest output from the ${agent.name} agent`
    sessionStorage.setItem('jarvis_prefill', msg)
    router.push('/business/chat')
  }

  return (
    <AnimatePresence>
      {agent && (
        <motion.div
          initial={{ x: 380, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: 380, opacity: 0 }}
          transition={{ duration: 0.3, ease: 'easeOut' }}
          style={{
            position: 'fixed', right: 0, top: 0,
            width: 'min(380px, 100vw)',
            height: '100vh',
            background: 'rgba(15,15,18,0.75)',
            backdropFilter: 'blur(28px) saturate(180%)',
            WebkitBackdropFilter: 'blur(28px) saturate(180%)',
            borderLeft: '1px solid rgba(243,234,217,0.12)',
            zIndex: 50,
            display: 'flex', flexDirection: 'column',
            fontFamily: 'var(--font-sans), system-ui, sans-serif',
            overflowY: 'auto',
          }}
        >
          {/* Close button */}
          <div style={{ display: 'flex', justifyContent: 'flex-end', padding: 16 }}>
            <button
              onClick={onClose}
              style={{
                background: 'rgba(243,234,217,0.06)',
                border: '1px solid rgba(243,234,217,0.12)',
                borderRadius: 8, padding: 8, cursor: 'pointer',
                color: '#f3ead9', display: 'flex', alignItems: 'center',
              }}
            >
              <X size={16} />
            </button>
          </div>

          {/* Header */}
          <div style={{ padding: '0 24px 24px' }}>
            <div style={{
              width: 56, height: 56, borderRadius: '50%',
              background: 'rgba(200,75,49,0.1)',
              border: '1px solid rgba(200,75,49,0.2)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              marginBottom: 16,
            }}>
              {Icon && <Icon size={28} color="#c84b31" />}
            </div>

            <div style={{
              fontFamily: 'var(--font-arcade), monospace',
              fontSize: 14, color: '#f3ead9',
              marginBottom: 10, lineHeight: 1.5,
            }}>
              {agent.name}
            </div>

            <span style={{
              display: 'inline-block',
              fontSize: 9, fontWeight: 700, letterSpacing: '0.12em',
              textTransform: 'uppercase',
              color: '#c84b31',
              background: 'rgba(200,75,49,0.15)',
              padding: '4px 10px', borderRadius: 4,
              marginBottom: 16,
            }}>
              {agent.group === 'operator' ? 'Operator Cycle' : 'Creation 1.0'}
            </span>

            <p style={{
              fontSize: 13, color: 'rgba(243,234,217,0.65)',
              lineHeight: 1.6, margin: 0,
            }}>
              {agent.role}
            </p>
          </div>

          {/* Divider */}
          <div style={{ height: 1, background: 'rgba(243,234,217,0.07)', margin: '0 24px' }} />

          {activityLoading ? (
            <div style={{ display: 'flex', justifyContent: 'center', padding: '32px 0' }}>
              <TetrisLoader size="sm" speed="fast" loadingText="Loading activity..." />
            </div>
          ) : (
            <>
              {/* Recent Activity */}
              <div style={{ padding: '20px 24px' }}>
                <div style={{
                  fontFamily: 'var(--font-arcade), monospace',
                  fontSize: 9, letterSpacing: '0.2em',
                  color: 'rgba(243,234,217,0.4)', textTransform: 'uppercase',
                  marginBottom: 12,
                }}>
                  Recent Activity
                </div>
                {recentActivity.length === 0 ? (
                  <div style={{ fontSize: 12, color: 'rgba(243,234,217,0.3)', lineHeight: 1.6 }}>
                    No activity yet. This agent activates when you trigger an Operator cycle or Creation task.
                  </div>
                ) : recentActivity.map((item, i) => (
                  <div
                    key={i}
                    style={{
                      padding: '10px 0',
                      borderBottom: i < recentActivity.length - 1 ? '1px solid rgba(243,234,217,0.06)' : 'none',
                    }}
                  >
                    <div style={{ fontSize: 10, color: 'rgba(243,234,217,0.35)', marginBottom: 3 }}>
                      {item.time ? (item.time.includes('T') ? relativeTime(item.time) : item.time) : ''}
                    </div>
                    <div style={{ fontSize: 13, color: '#f3ead9' }}>
                      {item.summary}
                    </div>
                  </div>
                ))}
              </div>

              {/* Last Output */}
              <div style={{ padding: '0 24px 20px' }}>
                <div style={{
                  fontFamily: 'var(--font-arcade), monospace',
                  fontSize: 9, letterSpacing: '0.2em',
                  color: 'rgba(243,234,217,0.4)', textTransform: 'uppercase',
                  marginBottom: 10,
                }}>
                  Last Output
                </div>
                <div style={{
                  minHeight: 80, maxHeight: 140,
                  background: 'rgba(243,234,217,0.03)',
                  border: '1px solid rgba(243,234,217,0.08)',
                  borderRadius: 8, padding: '12px 14px',
                  fontSize: 12,
                  color: lastOutput ? 'rgba(243,234,217,0.7)' : 'rgba(243,234,217,0.3)',
                  lineHeight: 1.6, overflow: 'hidden',
                  fontFamily: lastOutput ? 'system-ui, sans-serif' : 'ui-monospace, monospace',
                }}>
                  {lastOutput || 'No output yet. Trigger an Operator run or a Creation 1.0 task to see live output from this agent here.'}
                </div>
              </div>
            </>
          )}

          {/* CTA */}
          <div style={{ padding: '0 24px 32px', marginTop: 'auto' }}>
            <button
              onClick={handleOpenInChat}
              style={{
                width: '100%',
                background: '#c84b31',
                border: 'none', borderRadius: 10,
                padding: '14px 0',
                color: 'white', fontSize: 10,
                fontFamily: 'var(--font-arcade), monospace',
                cursor: 'pointer', letterSpacing: '0.1em', textTransform: 'uppercase',
                transition: 'brightness 150ms',
              }}
              onMouseEnter={e => (e.currentTarget.style.filter = 'brightness(1.12)')}
              onMouseLeave={e => (e.currentTarget.style.filter = 'brightness(1)')}
            >
              Open in Chat
            </button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
