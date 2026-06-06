'use client'
import { useEffect, useState, useCallback } from 'react'
import Image from 'next/image'
import { supabase } from '../../../lib/supabase'
import ChatCanvas from '../../../components/business/ChatCanvas'
import ChatSidebar from '../../../components/business/ChatSidebar'
import ModeToggle from '../../../components/shared/ModeToggle'
import { setJarvisMode, createBusinessUser } from '../../../lib/userPreferences'
import ChatBackground from '../../../components/business/ChatBackground'
import TetrisLoader from '../../../components/ui/TetrisLoader'

const BACKEND = 'https://jarvis-backend-4oz6.onrender.com'

export default function BusinessChatPage() {
  const [userId, setUserId] = useState(null)       // 'user_' prefixed — for backend API calls
  const [loading, setLoading] = useState(true)

  // Conversation state — lifted so sidebar + canvas share it
  const [conversations, setConversations] = useState([])
  const [conversationsLoading, setConversationsLoading] = useState(false)
  const [activeConversationId, setActiveConversationId] = useState(null)
  const [memoryCount, setMemoryCount] = useState(0)
  const [sidebarMobileOpen, setSidebarMobileOpen] = useState(false)

  const loadConversations = useCallback(async (uid) => {
    const id = uid || userId
    if (!id) return
    setConversationsLoading(true)
    try {
      const res = await fetch(`${BACKEND}/api/business/conversations?user_id=${encodeURIComponent(id)}`)
      const data = await res.json()
      const convos = data.conversations || []
      setConversations(convos)
      // Load most recent conversation if none active
      setActiveConversationId(prev => {
        if (prev) return prev  // Keep current if already set
        return convos.length > 0 ? convos[0].id : null
      })
    } catch (e) {
      console.error('loadConversations failed', e)
    } finally {
      setConversationsLoading(false)
    }
  }, [userId])

  const loadMemoryCount = useCallback(async (uid) => {
    const id = uid || userId
    if (!id) return
    try {
      const res = await fetch(`${BACKEND}/api/business/memories/count?user_id=${encodeURIComponent(id)}`)
      if (!res.ok) { console.error('loadMemoryCount HTTP error:', res.status); return }
      const data = await res.json()
      if (data.count != null) setMemoryCount(data.count)
    } catch (e) {
      console.error('loadMemoryCount failed:', e)
    }
  }, [userId])

  useEffect(() => {
    if (!supabase) { setLoading(false); return }
    supabase.auth.getSession().then(async ({ data: { session } }) => {
      if (session?.user) {
        const uid = 'user_' + session.user.id.replace(/-/g, '')
        setUserId(uid)

        const params = new URLSearchParams(window.location.search)
        if (params.get('onboard') === 'business') {
          const saved = sessionStorage.getItem('jarvis_biz_onboard')
          if (saved) {
            try {
              const form = JSON.parse(saved)
              await createBusinessUser({
                userId: uid,
                email: session.user.email,
                companyName: form.companyName,
                industry: form.industry,
                role: form.role,
              })
            } catch {}
            sessionStorage.removeItem('jarvis_biz_onboard')
          }
          await setJarvisMode(uid, 'business').catch(() => {})
          window.history.replaceState({}, '', '/business/chat')
        }

        await loadConversations(uid)
        await loadMemoryCount(uid)
      }
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  const handleGoogleSignIn = async () => {
    if (!supabase) return
    await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: { redirectTo: `${window.location.origin}/auth/callback?next=/business/chat` },
    })
  }

  const handleSelectConversation = (id) => {
    setActiveConversationId(id)
    setSidebarMobileOpen(false)
  }

  const handleNewChat = () => {
    setActiveConversationId(null)
    setSidebarMobileOpen(false)
  }

  const handleDeleteConversation = async (id) => {
    if (!userId) return
    try {
      await fetch(`${BACKEND}/api/business/conversations/${id}?user_id=${encodeURIComponent(userId)}`, {
        method: 'DELETE',
      })
      setConversations(prev => prev.filter(c => c.id !== id))
      if (activeConversationId === id) setActiveConversationId(null)
    } catch (e) {
      console.error('Delete conversation failed', e)
    }
  }

  const handleConversationCreated = (id) => {
    setActiveConversationId(id)
    loadConversations()
  }

  const handleConversationsUpdated = () => {
    loadConversations()
    loadMemoryCount()
  }

  if (loading) {
    return (
      <div style={{
        height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: '#0a0908',
      }}>
        <TetrisLoader size="md" speed="normal" showLoadingText={true} loadingText="Starting Jarvis..." />
      </div>
    )
  }

  return (
    <div style={{
      height: '100vh', display: 'flex', flexDirection: 'column',
      background: '#0a0908',
      position: 'relative',
    }}>
      <ChatBackground />
      {/* Noise grain overlay */}
      <div style={{
        position: 'fixed', inset: 0, opacity: 0.015, pointerEvents: 'none', zIndex: 0,
        backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E")`,
      }} />

      {/* Header */}
      <div style={{
        height: 56, flexShrink: 0,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '0 40px',
        borderBottom: '1px solid rgba(243,234,217,0.06)',
        background: 'rgba(10,9,8,0.8)',
        backdropFilter: 'blur(20px) saturate(180%)',
        WebkitBackdropFilter: 'blur(20px) saturate(180%)',
        position: 'relative', zIndex: 10,
      }}>
        {/* Left: hamburger (mobile) + logo */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          {/* Mobile sidebar toggle */}
          <button
            onClick={() => setSidebarMobileOpen(o => !o)}
            className="mobile-sidebar-toggle"
            style={{
              display: 'none',
              background: 'transparent', border: 'none',
              color: 'rgba(243,234,217,0.5)', cursor: 'pointer',
              fontSize: 18, padding: '4px 8px', lineHeight: 1,
            }}
          >
            ☰
          </button>
          <style>{`@media (max-width: 768px) { .mobile-sidebar-toggle { display: flex !important; } }`}</style>

          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginLeft: 60 }}
            className="header-logo-offset">
            <style>{`@media (max-width: 768px) { .header-logo-offset { margin-left: 0 !important; } }`}</style>
            <Image src="/logo-transparent.png" alt="Jarvis" width={28} height={28} style={{ objectFit: 'contain' }} />
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
              <span style={{ fontFamily: 'var(--font-serif), Georgia, serif', fontSize: 16, letterSpacing: '0.2em', color: '#f3ead9', fontWeight: 400 }}>
                JARVIS
              </span>
              <span style={{ fontFamily: 'system-ui, sans-serif', fontSize: 10, letterSpacing: '0.3em', textTransform: 'uppercase', color: '#c84b31', opacity: 0.8 }}>
                OS1
              </span>
            </div>
          </div>
        </div>

        {/* Right: mode toggle + sign in */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginRight: 60 }}>
          {!userId && (
            <button
              onClick={handleGoogleSignIn}
              style={{
                background: 'rgba(200,75,49,0.08)', border: '1px solid rgba(200,75,49,0.2)',
                borderRadius: 6, padding: '6px 14px',
                color: '#c84b31', cursor: 'pointer',
                fontFamily: 'system-ui, sans-serif', fontSize: 11,
                letterSpacing: '0.08em', transition: 'all 200ms ease',
              }}
            >
              Sign in
            </button>
          )}
          <ModeToggle userId={userId} currentMode="business" />
        </div>
      </div>

      {/* Body: sidebar + chat */}
      <div style={{ flex: 1, minHeight: 0, display: 'flex', position: 'relative', zIndex: 1 }}>
        <ChatSidebar
          conversations={conversations}
          loading={conversationsLoading}
          activeConversationId={activeConversationId}
          onSelectConversation={handleSelectConversation}
          onNewChat={handleNewChat}
          onDeleteConversation={handleDeleteConversation}
          memoryCount={memoryCount}
          isMobileOpen={sidebarMobileOpen}
          onClose={() => setSidebarMobileOpen(false)}
        />

        <div style={{ flex: 1, minHeight: 0, position: 'relative' }}>
          <ChatCanvas
            userId={userId}
            activeConversationId={activeConversationId}
            onConversationCreated={handleConversationCreated}
            onConversationsUpdated={handleConversationsUpdated}
            onMemoryCountUpdate={(count) => setMemoryCount(c => Math.max(c, count))}
          />
        </div>
      </div>
    </div>
  )
}
