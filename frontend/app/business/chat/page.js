'use client'
import { useEffect, useState } from 'react'
import Image from 'next/image'
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
        <div style={{ color: 'rgba(243,234,217,0.25)', fontFamily: 'system-ui, sans-serif', fontSize: 13, letterSpacing: '0.05em' }}>
          Loading…
        </div>
      </div>
    )
  }

  return (
    <div style={{
      height: '100vh', display: 'flex', flexDirection: 'column',
      background: `
        radial-gradient(ellipse 60% 50% at 50% 40%, rgba(200,75,49,0.03) 0%, transparent 70%),
        radial-gradient(ellipse 80% 60% at 50% 100%, rgba(243,234,217,0.02) 0%, transparent 50%),
        #0a0908
      `,
      position: 'relative',
    }}>
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
        {/* Left: logo + wordmark */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginLeft: 72 }}>
          <Image
            src="/logo-os1.png"
            alt="Jarvis"
            width={28}
            height={28}
            style={{ objectFit: 'contain' }}
          />
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
            <span style={{
              fontFamily: 'var(--font-serif), Georgia, serif',
              fontSize: 16, letterSpacing: '0.2em',
              color: '#f3ead9', fontWeight: 400,
            }}>
              JARVIS
            </span>
            <span style={{
              fontFamily: 'system-ui, sans-serif',
              fontSize: 10, letterSpacing: '0.3em',
              textTransform: 'uppercase',
              color: '#c84b31', opacity: 0.8,
            }}>
              OS1
            </span>
          </div>
        </div>

        {/* Right: mode toggle + sign in */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginRight: 72 }}>
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

      {/* Chat canvas */}
      <div style={{ flex: 1, minHeight: 0, position: 'relative', zIndex: 1 }}>
        <ChatCanvas userId={userId} />
      </div>
    </div>
  )
}
