'use client'
import { motion } from 'framer-motion'
import WorkflowCanvas from '../../../components/business/WorkflowCanvas'
import MindCanvas from '../../../components/business/mind/MindCanvas'
import ChatHeaderMenu from '../../../components/business/ChatHeaderMenu'
import ViewToggle from '../../../components/business/workflow/ViewToggle'
import { useEffect, useState } from 'react'
import { supabase } from '../../../lib/supabase'
import { useFontPref } from '../../../lib/fontPref'

const TABS = [
  { id: 'mind', label: 'MIND' },
  { id: 'agents', label: 'AGENTS' },
]

export default function WorkflowPage() {
  const [userId, setUserId] = useState(null)
  const [activeTab, setActiveTab] = useState('mind')

  useFontPref(userId)

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
      style={{ height: '100vh', background: '#050506', display: 'flex', flexDirection: 'column' }}
    >
      {/* Header strip */}
      <div style={{
        height: 56, flexShrink: 0,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '0 40px',
        borderBottom: '1px solid rgba(244,244,242,0.07)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginLeft: 72 }}>
          <div style={{
            fontFamily: 'Georgia, serif', fontSize: 16, letterSpacing: '0.3em',
            color: '#f4f4f2', fontWeight: 400,
          }}>
            JARVIS
          </div>
          <div style={{
            fontSize: 10, letterSpacing: '0.2em', textTransform: 'uppercase',
            color: '#ff2e51', fontFamily: 'system-ui, sans-serif', fontWeight: 500,
            padding: '2px 8px', border: '1px solid rgba(255,46,81,0.3)', borderRadius: 4,
          }}>
            Workflow
          </div>
        </div>

        {/* MIND / AGENTS tabs */}
        <div style={{ display: 'flex', gap: 6 }}>
          {TABS.map(tab => {
            const active = activeTab === tab.id
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                style={{
                  fontFamily: 'var(--pixel)',
                  fontSize: 11,
                  letterSpacing: '0.18em',
                  padding: '7px 16px',
                  background: active ? 'rgba(255,46,81,0.08)' : 'transparent',
                  color: active ? '#ff2e51' : '#71717a',
                  border: `1px solid ${active ? 'rgba(255,46,81,0.45)' : 'rgba(244,244,242,0.12)'}`,
                  borderRadius: 4,
                  cursor: 'pointer',
                  transition: 'all 0.2s ease',
                  boxShadow: active ? '0 0 14px rgba(255,46,81,0.18)' : 'none',
                }}
              >
                {tab.label}
              </button>
            )
          })}
        </div>
      </div>

      {/* Canvas */}
      {activeTab === 'mind'
        ? <MindCanvas userId={userId} />
        : <WorkflowCanvas userId={userId} />
      }

      {/* Floating UI */}
      <ViewToggle />
      <ChatHeaderMenu userId={userId} onBrandSaved={() => {}} />
    </motion.div>
  )
}
