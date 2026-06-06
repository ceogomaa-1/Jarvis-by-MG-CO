'use client'
import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import RefineModal from './RefineModal'

const BACKEND = 'https://jarvis-backend-4oz6.onrender.com'

const ROLE_LABELS = {
  strategist: 'STRATEGIST',
  copywriter: 'COPYWRITER',
  designer: 'DESIGNER',
  researcher: 'RESEARCHER',
  analyst: 'ANALYST',
  reporter: 'REPORTER',
}

const ROLE_ICONS = {
  strategist: '🎯',
  copywriter: '✍️',
  designer: '🎨',
  researcher: '🔍',
  analyst: '📊',
  reporter: '📦',
}

function StatusPill({ agent, status }) {
  const palette = {
    pending: { bg: 'rgba(243,234,217,0.04)', border: 'rgba(243,234,217,0.1)', text: 'rgba(243,234,217,0.5)', dot: 'rgba(243,234,217,0.3)' },
    started: { bg: 'rgba(200,75,49,0.08)', border: 'rgba(200,75,49,0.3)', text: '#f3ead9', dot: '#c84b31' },
    complete: { bg: 'rgba(34,197,94,0.08)', border: 'rgba(34,197,94,0.3)', text: '#f3ead9', dot: '#22c55e' },
    failed: { bg: 'rgba(239,68,68,0.08)', border: 'rgba(239,68,68,0.3)', text: '#f3ead9', dot: '#ef4444' },
  }
  const c = palette[status] || palette.pending

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 10,
      padding: '10px 14px',
      background: c.bg,
      border: `1px solid ${c.border}`,
      borderRadius: 10,
      transition: 'all 300ms ease',
    }}>
      <div style={{
        width: 8, height: 8, borderRadius: '50%',
        background: c.dot,
        animation: status === 'started' ? 'pulseDot 1.2s ease-in-out infinite' : 'none',
        flexShrink: 0,
      }} />
      <div style={{ fontSize: 14, flexShrink: 0 }}>{ROLE_ICONS[agent.role] || '⚙️'}</div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontSize: 10, fontWeight: 600, letterSpacing: '0.08em',
          color: c.text, opacity: 0.7, marginBottom: 2,
        }}>
          {ROLE_LABELS[agent.role] || agent.role.toUpperCase()}
        </div>
        <div style={{
          fontSize: 12, color: c.text,
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
          {agent.task}
        </div>
      </div>
    </div>
  )
}

export default function CreationCanvas({ msg, onArtifactUpdate }) {
  const {
    title, intro, agents = [], statuses = {}, artifact: streamedArtifact,
    error, complete, creationId,
    deploying, deploymentStatus, liveUrl, repoUrl, deploymentMessage, deploymentError,
  } = msg
  const [localArtifact, setLocalArtifact] = useState(null)
  const [showRefine, setShowRefine] = useState(false)
  const [downloading, setDownloading] = useState(false)

  const displayArtifact = localArtifact ?? streamedArtifact ?? ''

  async function handleDownloadPDF() {
    if (!creationId || downloading) return
    setDownloading(true)
    try {
      const res = await fetch(`${BACKEND}/api/business/create/${creationId}/pdf`)
      if (!res.ok) throw new Error('Download failed')
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `jarvis-creation-${creationId.slice(0, 8)}.pdf`
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      console.error('PDF download failed:', err)
    }
    setDownloading(false)
  }

  function handleRefined(newArtifact) {
    setLocalArtifact(newArtifact)
    if (onArtifactUpdate) onArtifactUpdate(newArtifact)
  }

  return (
    <div style={{ marginBottom: 24, maxWidth: '94%' }}>
      <style>{`
        @keyframes pulseDot {
          0%, 100% { transform: scale(1); opacity: 1; }
          50%      { transform: scale(1.4); opacity: 0.5; }
        }
      `}</style>

      {/* Header */}
      {title && (
        <div style={{
          fontSize: 11, fontWeight: 600, letterSpacing: '0.12em',
          color: '#c84b31', marginBottom: 6, textTransform: 'uppercase',
        }}>
          CREATION 1.0 · Spinning up sub-agents
        </div>
      )}
      {title && (
        <div style={{
          fontSize: 20, fontWeight: 600, color: '#f3ead9',
          marginBottom: 8, fontFamily: 'system-ui, sans-serif',
        }}>
          {title}
        </div>
      )}
      {intro && (
        <div style={{
          fontSize: 14, color: 'rgba(243,234,217,0.7)', marginBottom: 16,
          fontFamily: 'system-ui, sans-serif', lineHeight: 1.6,
        }}>
          {intro}
        </div>
      )}

      {/* Sub-agent pills */}
      {agents.length > 0 && (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
          gap: 10, marginBottom: 18,
        }}>
          {agents.map(a => (
            <StatusPill key={a.id} agent={a} status={statuses[a.id] || 'pending'} />
          ))}
        </div>
      )}

      {/* Final artifact */}
      {displayArtifact && (
        <div style={{
          background: 'rgba(243,234,217,0.03)',
          border: '1px solid rgba(243,234,217,0.1)',
          borderRadius: 14,
          padding: '22px 26px',
          marginTop: 12,
        }}>
          <div style={{
            display: 'flex', alignItems: 'center',
            justifyContent: 'space-between', marginBottom: 14,
          }}>
            <div style={{
              fontSize: 10, fontWeight: 600, letterSpacing: '0.12em',
              color: '#22c55e', textTransform: 'uppercase',
            }}>
              SHIPPED
            </div>

            {complete && creationId && (
              <div style={{ display: 'flex', gap: 8 }}>
                <button
                  onClick={() => setShowRefine(true)}
                  style={{
                    background: 'rgba(200,75,49,0.1)',
                    border: '1px solid rgba(200,75,49,0.3)',
                    borderRadius: 6, padding: '5px 12px',
                    color: '#c84b31', fontSize: 12, fontWeight: 500,
                    cursor: 'pointer', fontFamily: 'system-ui, sans-serif',
                    transition: 'all 200ms ease',
                  }}
                  onMouseEnter={e => (e.currentTarget.style.background = 'rgba(200,75,49,0.2)')}
                  onMouseLeave={e => (e.currentTarget.style.background = 'rgba(200,75,49,0.1)')}
                >
                  Refine
                </button>
                <button
                  onClick={handleDownloadPDF}
                  disabled={downloading}
                  style={{
                    background: 'rgba(243,234,217,0.06)',
                    border: '1px solid rgba(243,234,217,0.15)',
                    borderRadius: 6, padding: '5px 12px',
                    color: downloading ? 'rgba(243,234,217,0.3)' : 'rgba(243,234,217,0.7)',
                    fontSize: 12, fontWeight: 500,
                    cursor: downloading ? 'default' : 'pointer',
                    fontFamily: 'system-ui, sans-serif',
                    transition: 'all 200ms ease',
                  }}
                >
                  {downloading ? 'Downloading...' : 'Download PDF'}
                </button>
              </div>
            )}
          </div>

          <div
            className="biz-markdown"
            style={{
              fontSize: 14, color: '#f3ead9', lineHeight: 1.7,
              fontFamily: 'system-ui, sans-serif',
            }}
          >
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{displayArtifact}</ReactMarkdown>
          </div>
        </div>
      )}

      {/* Deployment phase */}
      {(deploying || liveUrl || deploymentError) && (
        <div style={{
          marginTop: 16,
          background: liveUrl ? 'rgba(34,197,94,0.05)' : deploymentError ? 'rgba(239,68,68,0.05)' : 'rgba(200,75,49,0.05)',
          border: `1px solid ${liveUrl ? 'rgba(34,197,94,0.25)' : deploymentError ? 'rgba(239,68,68,0.25)' : 'rgba(200,75,49,0.2)'}`,
          borderRadius: 12,
          padding: '14px 18px',
        }}>
          {deploying && !liveUrl && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <div style={{
                width: 8, height: 8, borderRadius: '50%',
                background: '#c84b31',
                animation: 'pulseDot 1.2s ease-in-out infinite',
                flexShrink: 0,
              }} />
              <span style={{
                fontSize: 12, color: 'rgba(243,234,217,0.75)',
                fontFamily: 'system-ui, sans-serif',
              }}>
                {deploymentStatus || 'Deploying...'}
              </span>
            </div>
          )}

          {liveUrl && (
            <div>
              <div style={{
                fontSize: 10, fontWeight: 600, letterSpacing: '0.12em',
                color: '#22c55e', textTransform: 'uppercase', marginBottom: 10,
              }}>
                DEPLOYED
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                <a
                  href={liveUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{
                    display: 'inline-flex', alignItems: 'center', gap: 6,
                    padding: '7px 14px', borderRadius: 8,
                    background: '#22c55e', color: '#0a0a0a',
                    fontSize: 12, fontWeight: 600,
                    textDecoration: 'none', fontFamily: 'system-ui, sans-serif',
                  }}
                >
                  🚀 Open live site
                </a>
                {repoUrl && (
                  <a
                    href={repoUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                      display: 'inline-flex', alignItems: 'center', gap: 6,
                      padding: '7px 14px', borderRadius: 8,
                      background: 'rgba(243,234,217,0.07)',
                      border: '1px solid rgba(243,234,217,0.15)',
                      color: 'rgba(243,234,217,0.8)',
                      fontSize: 12, fontWeight: 500,
                      textDecoration: 'none', fontFamily: 'system-ui, sans-serif',
                    }}
                  >
                    GitHub repo →
                  </a>
                )}
              </div>
              {liveUrl && (
                <div style={{
                  marginTop: 8, fontSize: 11,
                  color: 'rgba(243,234,217,0.4)',
                  fontFamily: 'system-ui, sans-serif',
                }}>
                  {liveUrl}
                </div>
              )}
            </div>
          )}

          {deploymentError && (
            <div style={{ fontSize: 12, color: 'rgba(239,68,68,0.85)', fontFamily: 'system-ui, sans-serif' }}>
              Deployment failed: {deploymentError}
            </div>
          )}
        </div>
      )}

      {/* Error state */}
      {error && (
        <div style={{
          background: 'rgba(239,68,68,0.08)',
          border: '1px solid rgba(239,68,68,0.3)',
          borderRadius: 10, padding: '14px 18px',
          color: '#f3ead9', fontSize: 13, marginTop: 12,
        }}>
          {error}
        </div>
      )}

      {showRefine && creationId && (
        <RefineModal
          creationId={creationId}
          onClose={() => setShowRefine(false)}
          onRefined={handleRefined}
        />
      )}
    </div>
  )
}
