'use client'
import { motion, AnimatePresence } from 'framer-motion'
import { useRouter } from 'next/navigation'
import { X } from 'lucide-react'
import {
  Brain, Search, Sparkles, Package, Compass,
  PenTool, Palette, Telescope, BarChart3, FileText,
} from 'lucide-react'

const ICONS = { Brain, Search, Sparkles, Package, Compass, PenTool, Palette, Telescope, BarChart3, FileText }

const MOCK_ACTIVITY = [
  { time: '2h ago',    summary: 'Drafted Q3 outreach sequence (3 emails)' },
  { time: 'Yesterday', summary: 'Generated weekly newsletter — 680 words' },
  { time: '2 days ago', summary: 'Analyzed competitor pricing from 4 sources' },
]

export default function AgentInspectorPanel({ agent, onClose }) {
  const router = useRouter()
  const Icon = agent ? (ICONS[agent.icon] || Brain) : null

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
              fontFamily: 'var(--font-serif), Georgia, serif',
              fontSize: 28, color: '#f3ead9', fontWeight: 400,
              marginBottom: 10,
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

          {/* Recent Activity */}
          <div style={{ padding: '20px 24px' }}>
            <div style={{
              fontSize: 10, fontWeight: 700, letterSpacing: '0.12em',
              color: 'rgba(243,234,217,0.4)', textTransform: 'uppercase',
              marginBottom: 12,
            }}>
              Recent Activity
            </div>
            {MOCK_ACTIVITY.map((item, i) => (
              <div
                key={i}
                style={{
                  padding: '10px 0',
                  borderBottom: i < MOCK_ACTIVITY.length - 1 ? '1px solid rgba(243,234,217,0.06)' : 'none',
                }}
              >
                <div style={{ fontSize: 10, color: 'rgba(243,234,217,0.35)', marginBottom: 3 }}>
                  {item.time}
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
              fontSize: 10, fontWeight: 700, letterSpacing: '0.12em',
              color: 'rgba(243,234,217,0.4)', textTransform: 'uppercase',
              marginBottom: 10,
            }}>
              Last Output
            </div>
            <div style={{
              height: 120,
              background: 'rgba(243,234,217,0.03)',
              border: '1px solid rgba(243,234,217,0.08)',
              borderRadius: 8, padding: '12px 14px',
              fontSize: 12, color: 'rgba(243,234,217,0.35)',
              lineHeight: 1.6, overflow: 'hidden',
              fontFamily: 'ui-monospace, monospace',
            }}>
              No output yet. Trigger an Operator run or a Creation 1.0 task to see live output from this agent here.
            </div>
          </div>

          {/* CTA */}
          <div style={{ padding: '0 24px 32px', marginTop: 'auto' }}>
            <button
              onClick={() => router.push('/business/chat')}
              style={{
                width: '100%',
                background: '#c84b31',
                border: 'none', borderRadius: 10,
                padding: '14px 0',
                color: 'white', fontSize: 13, fontWeight: 600,
                fontFamily: 'var(--font-sans), system-ui, sans-serif',
                cursor: 'pointer', letterSpacing: '0.04em',
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
