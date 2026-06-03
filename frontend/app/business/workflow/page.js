'use client'
import { motion } from 'framer-motion'
import WorkflowCanvas from '../../../components/business/WorkflowCanvas'
import ChatHeaderMenu from '../../../components/business/ChatHeaderMenu'
import ViewToggle from '../../../components/business/workflow/ViewToggle'
import { useEffect, useState } from 'react'
import { supabase } from '../../../lib/supabase'

export default function WorkflowPage() {
  const [userId, setUserId] = useState(null)

  useEffect(() => {
    if (!supabase) return
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session?.user) {
        setUserId('user_' + session.user.id.replace(/-/g, ''))
      }
    }).catch(() => {})
  }, [])

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.96 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 1.04 }}
      transition={{ duration: 0.4, ease: 'easeOut' }}
      style={{ height: '100vh', background: '#0a0908', display: 'flex', flexDirection: 'column' }}
    >
      {/* Header strip */}
      <div style={{
        height: 56, flexShrink: 0,
        display: 'flex', alignItems: 'center',
        padding: '0 40px',
        borderBottom: '1px solid rgba(243,234,217,0.07)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, paddingLeft: 64 }}>
          <div style={{
            fontFamily: 'Georgia, serif', fontSize: 16, letterSpacing: '0.3em',
            color: '#f3ead9', fontWeight: 400,
          }}>
            JARVIS
          </div>
          <div style={{
            fontSize: 10, letterSpacing: '0.2em', textTransform: 'uppercase',
            color: '#c84b31', fontFamily: 'system-ui, sans-serif', fontWeight: 500,
            padding: '2px 8px', border: '1px solid rgba(200,75,49,0.3)', borderRadius: 4,
          }}>
            Workflow
          </div>
        </div>
      </div>

      {/* Canvas */}
      <WorkflowCanvas />

      {/* Floating UI */}
      <ViewToggle />
      <ChatHeaderMenu userId={userId} onBrandSaved={() => {}} />
    </motion.div>
  )
}
