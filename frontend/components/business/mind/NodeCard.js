'use client'

import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useRouter } from 'next/navigation'
import { X } from 'lucide-react'
import { colorForCategory, MIND_LABELS, GOLD } from './colors'

const SOURCE_LABELS = {
  chat: 'From a conversation',
  knowledge_base: 'From your knowledge base',
  morning_queue: 'From the Morning Queue',
}

function relativeTime(isoStr) {
  if (!isoStr) return ''
  const date = new Date(isoStr)
  const diffMs = Date.now() - date.getTime()
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

function truncate(text, n) {
  if (!text) return ''
  return text.length > n ? `${text.slice(0, n).trim()}...` : text
}

function pixelButton({ accent = '#2d7ff9', muted = false } = {}) {
  return {
    width: '100%',
    background: muted ? 'transparent' : accent,
    border: muted ? '1px solid rgba(232,232,232,0.18)' : 'none',
    borderRadius: 4,
    padding: '12px 0',
    color: muted ? '#9a9a9a' : (accent === GOLD ? '#131313' : '#ffffff'),
    fontSize: 10,
    fontFamily: 'var(--pixel)',
    cursor: 'pointer',
    letterSpacing: '0.15em',
    textTransform: 'uppercase',
    transition: 'filter 150ms',
  }
}

function CategoryPill({ category }) {
  const color = colorForCategory(category)
  return (
    <span style={{
      display: 'inline-block',
      fontFamily: 'var(--pixel)',
      fontSize: 9, letterSpacing: '0.15em', textTransform: 'uppercase',
      color, background: `${color}22`,
      border: `1px solid ${color}55`,
      padding: '4px 10px', borderRadius: 4,
    }}>
      {MIND_LABELS[category] || MIND_LABELS.general}
    </span>
  )
}

export default function NodeCard({ node, userId, onClose, onForget }) {
  const router = useRouter()
  const [confirmingForget, setConfirmingForget] = useState(false)

  useEffect(() => {
    setConfirmingForget(false)
  }, [node])

  if (!node) return null

  function goToChat(context) {
    try {
      sessionStorage.setItem('jarvis_node_context', JSON.stringify(context))
    } catch { /* sessionStorage unavailable */ }
    onClose()
    router.push('/business/chat')
  }

  function actOnQueueItem() {
    try {
      sessionStorage.setItem('jarvis_prefill', node.action_prompt || node.title || '')
    } catch { /* sessionStorage unavailable */ }
    onClose()
    router.push('/business/chat')
  }

  const isSynapse = node.type === 'synapse'
  const isGap = node.type === 'gap'
  const isQueue = node.type === 'queue_item'
  const accent = isSynapse ? GOLD : isQueue ? '#2d7ff9' : colorForCategory(node.mind_category)

  return (
    <AnimatePresence>
      <motion.div
        key={node.id}
        initial={{ x: 360, opacity: 0 }}
        animate={{ x: 0, opacity: 1 }}
        exit={{ x: 360, opacity: 0 }}
        transition={{ duration: 0.28, ease: 'easeOut' }}
        style={{
          position: 'absolute', right: 0, top: 0, bottom: 0,
          width: 'min(360px, 100vw)',
          background: 'rgba(19,19,19,0.85)',
          backdropFilter: 'blur(24px) saturate(160%)',
          WebkitBackdropFilter: 'blur(24px) saturate(160%)',
          borderLeft: `1px solid ${isSynapse ? 'rgba(255,210,74,0.35)' : 'rgba(232,232,232,0.12)'}`,
          boxShadow: isSynapse ? `inset 0 0 40px rgba(255,210,74,0.06)` : 'none',
          display: 'flex', flexDirection: 'column',
          overflowY: 'auto', zIndex: 40,
        }}
      >
        {/* Close */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', padding: 16 }}>
          <button
            onClick={onClose}
            style={{
              background: 'rgba(232,232,232,0.06)',
              border: '1px solid rgba(232,232,232,0.12)',
              borderRadius: 6, padding: 8, cursor: 'pointer',
              color: '#e8e8e8', display: 'flex', alignItems: 'center',
            }}
          >
            <X size={14} />
          </button>
        </div>

        <div style={{ padding: '0 24px 28px', display: 'flex', flexDirection: 'column', gap: 16, flex: 1 }}>
          {/* Header */}
          {isSynapse ? (
            <div>
              <div style={{
                fontFamily: 'var(--pixel)', fontSize: 11, letterSpacing: '0.2em',
                color: GOLD, textTransform: 'uppercase', marginBottom: 8,
              }}>
                ✦ Golden Synapse
              </div>
              <div style={{ fontSize: 10, color: '#6e6e6e', letterSpacing: '0.05em' }}>
                {relativeTime(node.created_at)}
              </div>
            </div>
          ) : isGap ? (
            <div>
              <div style={{
                fontFamily: 'var(--pixel)', fontSize: 11, letterSpacing: '0.2em',
                color: '#e8e8e8', textTransform: 'uppercase', marginBottom: 8,
              }}>
                Knowledge Gap
              </div>
              <CategoryPill category={node.mind_category} />
            </div>
          ) : isQueue ? (
            <div>
              <div style={{
                fontFamily: 'var(--pixel)', fontSize: 11, letterSpacing: '0.2em',
                color: '#2d7ff9', textTransform: 'uppercase', marginBottom: 8,
              }}>
                Morning Queue
              </div>
              <div style={{ fontSize: 10, color: '#2d7ff9', letterSpacing: '0.05em' }}>
                born {node.created_at ? new Date(node.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''} ⚡
              </div>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <CategoryPill category={node.mind_category} />
              <div style={{ fontSize: 10, color: '#6e6e6e', letterSpacing: '0.05em' }}>
                {SOURCE_LABELS[node.source] || 'From a conversation'} · {relativeTime(node.created_at)}
              </div>
            </div>
          )}

          {/* Body */}
          {isSynapse ? (
            <>
              <div style={{ fontSize: 14, color: '#e8e8e8', lineHeight: 1.7 }}>
                {node.insight}
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {[node._a, node._b].map((m, i) => m && (
                  <div key={i} style={{
                    fontSize: 12, color: '#9a9a9a', lineHeight: 1.6,
                    padding: '10px 12px', borderRadius: 4,
                    background: 'rgba(232,232,232,0.03)',
                    border: `1px solid ${colorForCategory(m.mind_category)}33`,
                    borderLeft: `2px solid ${colorForCategory(m.mind_category)}`,
                  }}>
                    {truncate(m.memory, 140)}
                  </div>
                ))}
              </div>
            </>
          ) : isGap ? (
            <div style={{ fontSize: 14, color: '#e8e8e8', lineHeight: 1.7 }}>
              {node.label}
            </div>
          ) : isQueue ? (
            <div style={{ fontSize: 14, color: '#e8e8e8', lineHeight: 1.7 }}>
              {node.title}
            </div>
          ) : (
            <>
              <div style={{ fontSize: 14, color: '#e8e8e8', lineHeight: 1.7 }}>
                {node.memory}
              </div>

              {/* Strength bar */}
              <div>
                <div style={{
                  fontFamily: 'var(--pixel)', fontSize: 9, letterSpacing: '0.2em',
                  color: '#6e6e6e', textTransform: 'uppercase', marginBottom: 6,
                }}>
                  Strength
                </div>
                <div style={{ height: 4, borderRadius: 2, background: 'rgba(232,232,232,0.08)', overflow: 'hidden' }}>
                  <div style={{
                    height: '100%', width: `${Math.round((node.strength || 0) * 100)}%`,
                    background: accent, boxShadow: `0 0 8px ${accent}`,
                  }} />
                </div>
              </div>

              {/* Related memories */}
              {node._related && node._related.length > 0 && (
                <div>
                  <div style={{
                    fontFamily: 'var(--pixel)', fontSize: 9, letterSpacing: '0.2em',
                    color: '#6e6e6e', textTransform: 'uppercase', marginBottom: 8,
                  }}>
                    Related
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    {node._related.map(rel => (
                      <div key={rel.id} style={{
                        fontSize: 11, color: '#9a9a9a', lineHeight: 1.5,
                        padding: '8px 10px', borderRadius: 4,
                        background: 'rgba(232,232,232,0.03)',
                        borderLeft: `2px solid ${colorForCategory(rel.mind_category)}`,
                      }}>
                        {truncate(rel.memory, 100)}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}

          {/* Actions */}
          <div style={{ marginTop: 'auto', display: 'flex', flexDirection: 'column', gap: 10, paddingTop: 12 }}>
            {isSynapse && (
              <button
                style={pixelButton({ accent: GOLD })}
                onMouseEnter={e => (e.currentTarget.style.filter = 'brightness(1.1)')}
                onMouseLeave={e => (e.currentTarget.style.filter = 'brightness(1)')}
                onClick={() => goToChat({
                  mode: 'synapse',
                  insight: node.insight,
                  memory_a_text: node._a?.memory || '',
                  memory_b_text: node._b?.memory || '',
                })}
              >
                Talk to Rue about this →
              </button>
            )}

            {isGap && (
              <button
                style={pixelButton({ accent: '#2d7ff9' })}
                onMouseEnter={e => (e.currentTarget.style.filter = 'brightness(1.1)')}
                onMouseLeave={e => (e.currentTarget.style.filter = 'brightness(1)')}
                onClick={() => goToChat({
                  mode: 'gap',
                  label: node.label,
                  prompt: node.prompt,
                  mind_category: node.mind_category,
                })}
              >
                Give it to me →
              </button>
            )}

            {isQueue && (
              <button
                style={pixelButton({ accent: '#2d7ff9' })}
                onMouseEnter={e => (e.currentTarget.style.filter = 'brightness(1.1)')}
                onMouseLeave={e => (e.currentTarget.style.filter = 'brightness(1)')}
                onClick={actOnQueueItem}
              >
                Act on this →
              </button>
            )}

            {!isSynapse && !isGap && !isQueue && (
              <>
                <button
                  style={pixelButton({ accent: '#2d7ff9' })}
                  onMouseEnter={e => (e.currentTarget.style.filter = 'brightness(1.1)')}
                  onMouseLeave={e => (e.currentTarget.style.filter = 'brightness(1)')}
                  onClick={() => goToChat({
                    mode: 'memory',
                    memory_id: node.id,
                    memory_text: node.memory,
                    mind_category: node.mind_category,
                  })}
                >
                  Talk to Rue about this →
                </button>

                {confirmingForget ? (
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button
                      style={{ ...pixelButton({ accent: '#ff5d5d' }), flex: 1 }}
                      onClick={() => onForget(node.id)}
                    >
                      Yes, forget
                    </button>
                    <button
                      style={{ ...pixelButton({ muted: true }), flex: 1 }}
                      onClick={() => setConfirmingForget(false)}
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  <button
                    style={pixelButton({ muted: true })}
                    onClick={() => setConfirmingForget(true)}
                  >
                    Forget this
                  </button>
                )}
              </>
            )}
          </div>
        </div>
      </motion.div>
    </AnimatePresence>
  )
}
