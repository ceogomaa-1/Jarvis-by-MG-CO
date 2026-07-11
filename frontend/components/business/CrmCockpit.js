'use client'
import { useEffect, useRef, useState, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { X, MessageSquare, ExternalLink, RefreshCw } from 'lucide-react'
import ChatCanvas from './ChatCanvas'

import { BACKEND } from '@/lib/backend'

// Phase 3 — the Rue CRM cockpit: the user's own white-labeled CRM embedded,
// with the existing Business chat docked as a collapsible side panel. The docked
// chat is the SAME ChatCanvas component (not a fork); because the backend resolves
// the CRM workspace by user_id (Phase 2 for_user), the chat is automatically scoped
// to the workspace on screen. After a Rue CRM write the chat fires onCrmChanged
// and we reload the embed so the change shows ("feels live").
export default function CrmCockpit({ open, onClose, userId, workspace }) {
  const [chatOpen, setChatOpen] = useState(true)
  const [reloadTick, setReloadTick] = useState(0)
  const [conversationId, setConversationId] = useState(null)
  const iframeRef = useRef(null)

  const embedUrl = workspace?.embed_url || null

  // Refresh-on-action: re-point the iframe at a cache-busted URL so the new record
  // appears within a second or two. (True websocket sync is out of scope by design.)
  const refreshEmbed = useCallback(() => setReloadTick(t => t + 1), [])

  // Re-assign src on tick (avoids a full React remount / auth flash where possible).
  useEffect(() => {
    if (reloadTick === 0 || !iframeRef.current || !embedUrl) return
    const u = new URL(embedUrl)
    u.searchParams.set('_jarvisRefresh', String(Date.now()))
    iframeRef.current.src = u.toString()
  }, [reloadTick, embedUrl])

  if (!open) return null

  return (
    <AnimatePresence>
      <motion.div
        key="crm-cockpit"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.2 }}
        style={{
          position: 'fixed', inset: 0, zIndex: 60,
          background: '#0B0B0C', display: 'flex', flexDirection: 'column',
        }}
      >
        {/* Cockpit top bar */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '10px 16px', borderBottom: '1px solid var(--os1-border-soft, rgba(255,255,255,0.08))',
          background: '#131316', flexShrink: 0,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span className="font-pixel" style={{ fontSize: 14, color: 'var(--os1-text, #F5F5F4)' }}>
              {workspace?.display_name || 'Rue CRM'}
            </span>
            {workspace?.shared && (
              <span className="os1-serif-micro" style={{ fontSize: 9, color: 'var(--os1-text-faint, #6E6E6C)' }}>
                shared instance
              </span>
            )}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <button onClick={refreshEmbed} className="os1-iconbtn" title="Refresh CRM"><RefreshCw size={16} /></button>
            {embedUrl && (
              <a href={embedUrl} target="_blank" rel="noreferrer" className="os1-iconbtn" title="Open in new tab"
                 style={{ display: 'flex', alignItems: 'center', color: 'var(--os1-text-dim, #A8A8A6)' }}>
                <ExternalLink size={16} />
              </a>
            )}
            <button onClick={() => setChatOpen(o => !o)} className="os1-iconbtn" title={chatOpen ? 'Hide chat' : 'Show chat'}>
              <MessageSquare size={16} />
            </button>
            <button onClick={onClose} className="os1-iconbtn" title="Close CRM"><X size={18} /></button>
          </div>
        </div>

        {/* Body: embed + docked chat */}
        <div style={{ flex: 1, minHeight: 0, display: 'flex' }}>
          <div style={{ flex: 1, minWidth: 0, position: 'relative', background: '#0B0B0C' }}>
            {embedUrl ? (
              <iframe
                ref={iframeRef}
                src={embedUrl}
                title="Rue CRM"
                style={{ width: '100%', height: '100%', border: 'none' }}
                allow="clipboard-read; clipboard-write"
              />
            ) : (
              <div style={{
                height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center',
                color: 'var(--os1-text-dim, #A8A8A6)', textAlign: 'center', padding: 24,
              }}>
                <div>
                  <div className="font-pixel" style={{ fontSize: 14, marginBottom: 8 }}>CRM not provisioned yet</div>
                  <div className="os1-serif-micro" style={{ fontSize: 11 }}>
                    Your Rue CRM workspace hasn't been set up. Ask your admin to provision it.
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Docked chat — reuses ChatCanvas; collapsible */}
          <AnimatePresence>
            {chatOpen && (
              <motion.div
                key="crm-chat-dock"
                initial={{ width: 0, opacity: 0 }}
                animate={{ width: 'min(440px, 38vw)', opacity: 1 }}
                exit={{ width: 0, opacity: 0 }}
                transition={{ duration: 0.2, ease: 'easeOut' }}
                style={{
                  borderLeft: '1px solid var(--os1-border-soft, rgba(255,255,255,0.08))',
                  background: '#131313', display: 'flex', flexDirection: 'column',
                  minWidth: 320, flexShrink: 0, overflow: 'hidden',
                }}
              >
                <div style={{ flex: 1, minHeight: 0, minWidth: 0, position: 'relative' }}>
                  <ChatCanvas
                    userId={userId}
                    activeConversationId={conversationId}
                    onConversationCreated={setConversationId}
                    onConversationsUpdated={() => {}}
                    onMemoryCountUpdate={() => {}}
                    onCrmChanged={refreshEmbed}
                    compact
                  />
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </motion.div>
    </AnimatePresence>
  )
}
