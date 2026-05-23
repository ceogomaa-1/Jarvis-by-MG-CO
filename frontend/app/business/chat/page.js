'use client'
import { useEffect, useState } from 'react'
import { supabase } from '../../../lib/supabase'
import ChatCanvas from '../../../components/business/ChatCanvas'
import ModeToggle from '../../../components/shared/ModeToggle'
import { setJarvisMode, createBusinessUser } from '../../../lib/userPreferences'

export default function BusinessChatPage() {
  const [userId, setUserId] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!supabase) { setLoading(false); return }
    supabase.auth.getSession().then(async ({ data: { session } }) => {
      if (session?.user) {
        const uid = 'user_' + session.user.id.replace(/-/g, '')
        setUserId(uid)

        // Complete business onboarding if we just came from the modal
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
      }
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [])

  const handleGoogleSignIn = async () => {
    if (!supabase) return
    await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: { redirectTo: `${window.location.origin}/business/chat` },
    })
  }

  if (loading) {
    return (
      <div style={{
        height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: '#0a0908',
      }}>
        <div style={{ color: 'rgba(243,234,217,0.4)', fontFamily: 'system-ui, sans-serif', fontSize: 13 }}>
          Loading...
        </div>
      </div>
    )
  }

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', background: '#0a0908' }}>
      {/* Header */}
      <div style={{
        height: 56, flexShrink: 0,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '0 40px',
        borderBottom: '1px solid rgba(243,234,217,0.07)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
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
            for Business
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          {!userId ? (
            <button
              onClick={handleGoogleSignIn}
              style={{
                background: 'rgba(200,75,49,0.1)', border: '1px solid rgba(200,75,49,0.3)',
                borderRadius: 6, padding: '7px 16px',
                color: '#c84b31', cursor: 'pointer',
                fontFamily: 'system-ui, sans-serif', fontSize: 12,
                letterSpacing: '0.08em',
              }}
            >
              Sign in with Google
            </button>
          ) : (
            <div style={{
              fontSize: 11, color: 'rgba(243,234,217,0.35)',
              fontFamily: 'system-ui, sans-serif',
            }}>
              Signed in
            </div>
          )}
          <ModeToggle userId={userId} currentMode="business" />
        </div>
      </div>

      {/* Chat canvas */}
      <div style={{ flex: 1, minHeight: 0 }}>
        <ChatCanvas userId={userId} />
      </div>
    </div>
  )
}
