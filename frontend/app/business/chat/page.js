'use client'
import { useEffect, useState, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { supabase } from '../../../lib/supabase'
import ChatCanvas from '../../../components/business/ChatCanvas'
import ChatSidebar from '../../../components/business/ChatSidebar'
import ChatHeaderMenu from '../../../components/business/ChatHeaderMenu'
import { getBusinessUser } from '../../../lib/userPreferences'
import { useFontPref } from '../../../lib/fontPref'
import TetrisLoader from '../../../components/ui/TetrisLoader'

const BACKEND = 'https://jarvis-backend-4oz6.onrender.com'

export default function BusinessChatPage() {
  const router = useRouter()
  const [userId, setUserId] = useState(null)       // 'user_' prefixed — for backend API calls
  const [loading, setLoading] = useState(true)

  // Conversation state — lifted so sidebar + canvas share it
  const [conversations, setConversations] = useState([])
  const [conversationsLoading, setConversationsLoading] = useState(false)
  const [activeConversationId, setActiveConversationId] = useState(null)
  const [memoryCount, setMemoryCount] = useState(0)
  const [sidebarMobileOpen, setSidebarMobileOpen] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const [injectPrompt, setInjectPrompt] = useState(null)

  useFontPref(userId)

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

  // Warm up the Render backend immediately on mount — free-tier dynos sleep after
  // idle and the first request can otherwise time out silently (see Batch 46.1).
  useEffect(() => {
    fetch(`${BACKEND}/health`).catch(() => {})
  }, [])

  useEffect(() => {
    if (!supabase) { setLoading(false); return }
    supabase.auth.getSession().then(async ({ data: { session } }) => {
      if (session?.user) {
        const uid = 'user_' + session.user.id.replace(/-/g, '')
        setUserId(uid)

        // Loop breaker: onboarding just confirmed success and may not have
        // propagated to this read yet — skip the redirect this one time.
        const justOnboarded = sessionStorage.getItem('jarvis_onboarded') === '1'

        const businessUser = await getBusinessUser(uid)
        // Only redirect on a *definitive* "no profile" (HTTP 200, exists:false).
        // exists === null means the lookup failed (network/server error) —
        // never bounce back to onboarding on that, it would loop forever.
        if (businessUser.exists === false && !justOnboarded) {
          router.replace('/business/onboarding')
          return
        }
        if (businessUser.exists !== null) {
          sessionStorage.removeItem('jarvis_onboarded')
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
        background: '#131313',
      }}>
        <TetrisLoader size="md" speed="normal" showLoadingText={true} loadingText="Starting Jarvis..." />
      </div>
    )
  }

  return (
    <div className="os1-root" style={{
      height: '100vh', display: 'flex',
      background: '#131313',
      position: 'relative', overflow: 'hidden',
    }}>
      {/* Collapsed-state sidebar toggle — floats top-left when sidebar is hidden */}
      {sidebarCollapsed && (
        <button
          onClick={() => setSidebarCollapsed(false)}
          className="os1-iconbtn business-sidebar-desktop-toggle"
          title="Open sidebar"
          style={{ position: 'fixed', top: 22, left: 22, zIndex: 45 }}
        >
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
            <rect x="3" y="4" width="18" height="16" rx="3" />
            <line x1="9" y1="4" x2="9" y2="20" />
          </svg>
        </button>
      )}

      {/* Mobile sidebar hamburger */}
      <button
        onClick={() => setSidebarMobileOpen(o => !o)}
        className="os1-iconbtn mobile-sidebar-toggle"
        style={{ position: 'fixed', top: 18, left: 18, zIndex: 45, display: 'none' }}
      >
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
          <rect x="3" y="4" width="18" height="16" rx="3" />
          <line x1="9" y1="4" x2="9" y2="20" />
        </svg>
      </button>
      <style>{`@media (max-width: 768px) {
        .mobile-sidebar-toggle { display: flex !important; }
        .business-sidebar-desktop-toggle { display: none !important; }
      }`}</style>

      {/* Sign in (only when logged out) — top right, left of the menu hamburger */}
      {!userId && (
        <button
          onClick={handleGoogleSignIn}
          style={{
            position: 'fixed', top: 24, right: 76, zIndex: 45,
            background: 'transparent', border: '1px solid var(--os1-border)',
            borderRadius: 999, padding: '6px 16px',
            color: 'var(--os1-text-dim)', cursor: 'pointer',
            fontFamily: 'var(--pixel)', fontSize: 13,
            transition: 'all 200ms ease',
          }}
        >
          Sign in
        </button>
      )}

      {/* Right-side menu: hamburger (fixed top-right) + slide panel + modals */}
      <ChatHeaderMenu
        userId={userId}
        onBrandSaved={() => {}}
        open={menuOpen}
        onToggle={() => setMenuOpen(o => !o)}
        onClose={() => setMenuOpen(false)}
        onActPrompt={(prompt) => setInjectPrompt({ text: prompt, ts: Date.now() })}
      />

      {/* Body: floating sidebar + chat canvas */}
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
        collapsed={sidebarCollapsed}
        onCollapse={() => setSidebarCollapsed(true)}
        onOpenSettings={() => setMenuOpen(true)}
      />

      <div style={{ flex: 1, minHeight: 0, minWidth: 0, position: 'relative' }}>
        <ChatCanvas
          userId={userId}
          activeConversationId={activeConversationId}
          onConversationCreated={handleConversationCreated}
          onConversationsUpdated={handleConversationsUpdated}
          onMemoryCountUpdate={(count) => setMemoryCount(c => Math.max(c, count))}
          injectPrompt={injectPrompt}
        />
      </div>
    </div>
  )
}
