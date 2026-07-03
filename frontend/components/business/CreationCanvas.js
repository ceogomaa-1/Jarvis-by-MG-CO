'use client'
import { useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import RefineModal from './RefineModal'
import AIThinkingBlock from '@/components/ui/ai-thinking-block'

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
    pending: { bg: 'rgba(236,230,217,0.04)', border: 'rgba(236,230,217,0.1)', text: 'rgba(236,230,217,0.5)', dot: 'rgba(236,230,217,0.3)' },
    started: { bg: 'rgba(207,138,91,0.08)', border: 'rgba(207,138,91,0.3)', text: '#ece6d9', dot: '#cf8a5b' },
    complete: { bg: 'rgba(34,197,94,0.08)', border: 'rgba(34,197,94,0.3)', text: '#ece6d9', dot: '#22c55e' },
    failed: { bg: 'rgba(239,68,68,0.08)', border: 'rgba(239,68,68,0.3)', text: '#ece6d9', dot: '#ef4444' },
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

export default function CreationCanvas({ msg, onArtifactUpdate, onDeploy, userId }) {
  const {
    title, intro, agents = [], statuses = {}, artifact: streamedArtifact,
    error, complete, creationId, kind, projectName, summary, note,
    rehydrate, stageMessage,
    deploying, deploymentStages = [], deploymentStatus, liveUrl, repoUrl, dbUrl,
    deploymentMessage, deploymentError, deploymentId, expectedUrl,
  } = msg
  const [localArtifact, setLocalArtifact] = useState(null)
  const [localPreviewHtml, setLocalPreviewHtml] = useState(null)
  const [localDeploymentStatus, setLocalDeploymentStatus] = useState(null)
  const [localLiveUrl, setLocalLiveUrl] = useState(null)
  const [showRefine, setShowRefine] = useState(false)
  const [downloading, setDownloading] = useState(false)
  // Standalone HTML preview — from the live stream (msg.previewHtml) or rehydrated from the DB.
  const [hydrated, setHydrated] = useState(null)
  const previewHtml = localPreviewHtml ?? msg.previewHtml ?? hydrated?.preview_html ?? null
  const hydratedTitle = title || hydrated?.title
  const hydratedLiveUrl = localLiveUrl || liveUrl || hydrated?.vercel_url || hydrated?.live_url || null
  const effectiveDeploymentStatus = localDeploymentStatus || deploymentStatus || hydrated?.deployment_status
  const hasUnpublishedChanges = effectiveDeploymentStatus === 'DIRTY'

  // Rehydrate a saved creation after a refresh (CreationCanvas self-fetches its preview).
  useEffect(() => {
    if (!rehydrate || !creationId || hydrated) return
    let cancelled = false
    ;(async () => {
      try {
        const res = await fetch(`${BACKEND}/api/business/creations/${creationId}?user_id=${encodeURIComponent(userId || '')}`)
        if (!res.ok) return
        const data = await res.json()
        if (!cancelled && data.creation) setHydrated(data.creation)
      } catch (e) { /* best-effort */ }
    })()
    return () => { cancelled = true }
  }, [rehydrate, creationId, userId, hydrated])

  const displayArtifact = localArtifact ?? streamedArtifact ?? ''

  function handleDownloadHTML() {
    if (!previewHtml) return
    const blob = new Blob([previewHtml], { type: 'text/html' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${(projectName || hydrated?.title || hydratedTitle || 'landing-page').toString().replace(/[^a-z0-9-]/gi, '-').toLowerCase().slice(0, 40) || 'landing-page'}.html`
    a.click()
    URL.revokeObjectURL(url)
  }

  function handleOpenPreview() {
    if (!previewHtml) return
    const blob = new Blob([previewHtml], { type: 'text/html' })
    const url = URL.createObjectURL(blob)
    const opened = window.open(url, '_blank', 'noopener,noreferrer')
    if (!opened) URL.revokeObjectURL(url)
    else window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
  }

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
      a.download = `creation-${creationId.slice(0, 8)}.pdf`
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      console.error('PDF download failed:', err)
    }
    setDownloading(false)
  }

  function handleRefined(update) {
    if (typeof update === 'string') {
      setLocalArtifact(update)
    } else if (update?.html) {
      setLocalPreviewHtml(update.html)
      if (update.deploymentStatus) setLocalDeploymentStatus(update.deploymentStatus)
      if (update.liveUrl) setLocalLiveUrl(update.liveUrl)
    }
    if (onArtifactUpdate) onArtifactUpdate(update)
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
          color: '#cf8a5b', marginBottom: 6, textTransform: 'uppercase',
        }}>
          CREATION 1.0 · Spinning up sub-agents
        </div>
      )}
      {title && (
        <div style={{
          fontSize: 20, fontWeight: 600, color: '#ece6d9',
          marginBottom: 8, fontFamily: 'system-ui, sans-serif',
        }}>
          {title}
        </div>
      )}
      {intro && (
        <div style={{
          fontSize: 14, color: 'rgba(236,230,217,0.7)', marginBottom: 16,
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

      {!complete && !previewHtml && !error && (title || stageMessage) && (
        <AIThinkingBlock
          label={msg.stage === 'editing' ? 'Applying your website edits' : 'Crafting the website'}
          status={stageMessage || 'Turning the brief into a polished, client-ready experience…'}
          activity={deploymentStages}
          mode={msg.stage === 'editing' ? 'edit' : 'build'}
          className="mb-3"
        />
      )}

      {/* Standalone HTML — live preview + download + deploy */}
      {previewHtml && (
        <div style={{
          background: 'rgba(236,230,217,0.03)',
          border: '1px solid rgba(236,230,217,0.1)',
          borderRadius: 14, padding: 16, marginTop: 12,
        }}>
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            marginBottom: 12, flexWrap: 'wrap', gap: 8,
          }}>
            <div style={{
              fontSize: 10, fontWeight: 600, letterSpacing: '0.12em',
              color: '#22c55e', textTransform: 'uppercase',
            }}>
              {hydratedLiveUrl ? 'LIVE' : 'LIVE PREVIEW'}
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <button
                onClick={handleOpenPreview}
                style={{
                  background: 'rgba(236,230,217,0.06)', border: '1px solid rgba(236,230,217,0.15)',
                  borderRadius: 6, padding: '5px 12px', color: 'rgba(236,230,217,0.85)',
                  fontSize: 12, fontWeight: 500, cursor: 'pointer', fontFamily: 'system-ui, sans-serif',
                }}
              >
                ↗ Open preview
              </button>
              <button
                onClick={handleDownloadHTML}
                style={{
                  background: 'rgba(236,230,217,0.06)', border: '1px solid rgba(236,230,217,0.15)',
                  borderRadius: 6, padding: '5px 12px', color: 'rgba(236,230,217,0.85)',
                  fontSize: 12, fontWeight: 500, cursor: 'pointer', fontFamily: 'system-ui, sans-serif',
                }}
              >
                ⬇ Download HTML
              </button>
              {complete && creationId && (
                <button
                  onClick={() => setShowRefine(true)}
                  disabled={deploying}
                  style={{
                    background: 'rgba(207,138,91,0.1)',
                    border: '1px solid rgba(207,138,91,0.3)',
                    borderRadius: 6, padding: '5px 12px',
                    color: '#70a8ff', fontSize: 12, fontWeight: 600,
                    cursor: deploying ? 'default' : 'pointer',
                    fontFamily: 'system-ui, sans-serif',
                  }}
                >
                  Edit website
                </button>
              )}
              {hydratedLiveUrl ? (
                <>
                  <a
                    href={hydratedLiveUrl} target="_blank" rel="noopener noreferrer"
                    style={{
                      background: hasUnpublishedChanges ? 'rgba(236,230,217,0.07)' : '#22c55e',
                      color: hasUnpublishedChanges ? 'rgba(236,230,217,0.85)' : '#0a0a0a',
                      border: hasUnpublishedChanges ? '1px solid rgba(236,230,217,0.15)' : 'none',
                      borderRadius: 6, padding: '5px 14px', fontSize: 12, fontWeight: 600,
                      textDecoration: 'none', fontFamily: 'system-ui, sans-serif',
                    }}
                  >
                    Open live site
                  </a>
                  {hasUnpublishedChanges && (
                    <button
                      onClick={() => onDeploy && onDeploy()}
                      disabled={deploying}
                      style={{
                        background: deploying ? 'rgba(207,138,91,0.15)' : '#cf8a5b',
                        border: 'none', borderRadius: 6, padding: '5px 14px',
                        color: deploying ? 'rgba(236,230,217,0.6)' : '#fff',
                        fontSize: 12, fontWeight: 600,
                        cursor: deploying ? 'default' : 'pointer',
                        fontFamily: 'system-ui, sans-serif',
                      }}
                    >
                      {deploying ? 'Publishing…' : 'Redeploy changes'}
                    </button>
                  )}
                </>
              ) : (
                <button
                  onClick={() => onDeploy && onDeploy()}
                  disabled={deploying}
                  style={{
                    background: deploying ? 'rgba(207,138,91,0.15)' : 'rgba(207,138,91,0.9)',
                    border: 'none', borderRadius: 6, padding: '5px 14px',
                    color: deploying ? 'rgba(236,230,217,0.6)' : '#fff',
                    fontSize: 12, fontWeight: 600, cursor: deploying ? 'default' : 'pointer',
                    fontFamily: 'system-ui, sans-serif',
                  }}
                >
                  {deploying ? 'Deploying…' : '🚀 Deploy to Vercel'}
                </button>
              )}
            </div>
          </div>
          <iframe
            title="Landing page preview"
            srcDoc={previewHtml}
            sandbox="allow-scripts allow-popups"
            referrerPolicy="no-referrer"
            loading="lazy"
            style={{
              width: '100%', height: 540, border: 0, borderRadius: 12,
              background: '#0a0a0a', display: 'block',
            }}
          />
          {(summary || note) && (
            <div style={{
              marginTop: 12, fontSize: 13, color: 'rgba(236,230,217,0.65)',
              fontFamily: 'system-ui, sans-serif', lineHeight: 1.6,
            }}>
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{note || summary}</ReactMarkdown>
            </div>
          )}
        </div>
      )}

      {/* Final artifact */}
      {displayArtifact && (
        <div style={{
          background: 'rgba(236,230,217,0.03)',
          border: '1px solid rgba(236,230,217,0.1)',
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
                    background: 'rgba(207,138,91,0.1)',
                    border: '1px solid rgba(207,138,91,0.3)',
                    borderRadius: 6, padding: '5px 12px',
                    color: '#cf8a5b', fontSize: 12, fontWeight: 500,
                    cursor: 'pointer', fontFamily: 'system-ui, sans-serif',
                    transition: 'all 200ms ease',
                  }}
                  onMouseEnter={e => (e.currentTarget.style.background = 'rgba(207,138,91,0.2)')}
                  onMouseLeave={e => (e.currentTarget.style.background = 'rgba(207,138,91,0.1)')}
                >
                  Refine
                </button>
                <button
                  onClick={handleDownloadPDF}
                  disabled={downloading}
                  style={{
                    background: 'rgba(236,230,217,0.06)',
                    border: '1px solid rgba(236,230,217,0.15)',
                    borderRadius: 6, padding: '5px 12px',
                    color: downloading ? 'rgba(236,230,217,0.3)' : 'rgba(236,230,217,0.7)',
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
              fontSize: 14, color: '#ece6d9', lineHeight: 1.7,
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
          background: liveUrl ? 'rgba(34,197,94,0.05)' : deploymentError ? 'rgba(239,68,68,0.05)' : 'rgba(207,138,91,0.05)',
          border: `1px solid ${liveUrl ? 'rgba(34,197,94,0.25)' : deploymentError ? 'rgba(239,68,68,0.25)' : 'rgba(207,138,91,0.2)'}`,
          borderRadius: 12,
          padding: '14px 18px',
        }}>
          {deploying && !liveUrl && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <AIThinkingBlock
                label="Publishing your website"
                status={deploymentStatus || 'Preparing the validated build for Vercel…'}
                activity={deploymentStages}
                mode="deploy"
              />
              {(repoUrl || expectedUrl || deploymentId) && (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 8 }}>
                  {repoUrl && (
                    <a
                      href={repoUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{
                        display: 'inline-flex', alignItems: 'center',
                        padding: '6px 12px', borderRadius: 8,
                        background: 'rgba(236,230,217,0.07)',
                        border: '1px solid rgba(236,230,217,0.15)',
                        color: 'rgba(236,230,217,0.8)',
                        fontSize: 12, fontWeight: 500,
                        textDecoration: 'none', fontFamily: 'system-ui, sans-serif',
                      }}
                    >
                      GitHub repo
                    </a>
                  )}
                  {expectedUrl && (
                    <a
                      href={expectedUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{
                        display: 'inline-flex', alignItems: 'center',
                        padding: '6px 12px', borderRadius: 8,
                        background: 'rgba(207,138,91,0.08)',
                        border: '1px solid rgba(207,138,91,0.2)',
                        color: '#cf8a5b',
                        fontSize: 12, fontWeight: 500,
                        textDecoration: 'none', fontFamily: 'system-ui, sans-serif',
                      }}
                    >
                      Expected URL
                    </a>
                  )}
                </div>
              )}
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
                      background: 'rgba(236,230,217,0.07)',
                      border: '1px solid rgba(236,230,217,0.15)',
                      color: 'rgba(236,230,217,0.8)',
                      fontSize: 12, fontWeight: 500,
                      textDecoration: 'none', fontFamily: 'system-ui, sans-serif',
                    }}
                  >
                    GitHub repo →
                  </a>
                )}
                {dbUrl && (
                  <a
                    href={dbUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                      display: 'inline-flex', alignItems: 'center', gap: 6,
                      padding: '7px 14px', borderRadius: 8,
                      background: 'rgba(62,207,142,0.08)',
                      border: '1px solid rgba(62,207,142,0.25)',
                      color: 'rgba(62,207,142,0.9)',
                      fontSize: 12, fontWeight: 500,
                      textDecoration: 'none', fontFamily: 'system-ui, sans-serif',
                    }}
                  >
                    Supabase →
                  </a>
                )}
              </div>
              {liveUrl && (
                <div style={{
                  marginTop: 8, fontSize: 11,
                  color: 'rgba(236,230,217,0.4)',
                  fontFamily: 'system-ui, sans-serif',
                }}>
                  {liveUrl}
                </div>
              )}
            </div>
          )}

          {deploymentError && (
            <div style={{ fontFamily: 'system-ui, sans-serif' }}>
              <div style={{ fontSize: 12, color: 'rgba(239,68,68,0.85)', marginBottom: 8 }}>
                Deployment failed: {deploymentError}
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {repoUrl && (
                  <a
                    href={repoUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                      display: 'inline-flex', alignItems: 'center',
                      padding: '6px 12px', borderRadius: 8,
                      background: 'rgba(236,230,217,0.07)',
                      border: '1px solid rgba(236,230,217,0.15)',
                      color: 'rgba(236,230,217,0.8)',
                      fontSize: 12, fontWeight: 500,
                      textDecoration: 'none',
                    }}
                  >
                    Open GitHub repo
                  </a>
                )}
                {expectedUrl && (
                  <a
                    href={expectedUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                      display: 'inline-flex', alignItems: 'center',
                      padding: '6px 12px', borderRadius: 8,
                      background: 'rgba(207,138,91,0.08)',
                      border: '1px solid rgba(207,138,91,0.2)',
                      color: '#cf8a5b',
                      fontSize: 12, fontWeight: 500,
                      textDecoration: 'none',
                    }}
                  >
                    Try expected URL
                  </a>
                )}
              </div>
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
          color: '#ece6d9', fontSize: 13, marginTop: 12,
        }}>
          {error}
        </div>
      )}

      {showRefine && creationId && (
        <RefineModal
          creationId={creationId}
          userId={userId}
          kind={kind || hydrated?.kind}
          onClose={() => setShowRefine(false)}
          onRefined={handleRefined}
        />
      )}
    </div>
  )
}
