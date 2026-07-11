'use client'

import { useState } from 'react'
import { supabase } from '../../../lib/supabase'

export default function PersonalLogin() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const handleLogin = async () => {
    if (!supabase) return
    setLoading(true)
    setError(null)
    const { error: authError } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: {
        // Encode the destination so it survives as a single `next` query param
        // and lands at /?onboard=personal — page.js picks up ?onboard=personal
        // to set jarvis_mode='personal' and skip the portal selector.
        redirectTo: `${window.location.origin}/auth/callback?next=${encodeURIComponent('/?onboard=personal')}`,
      },
    })
    if (authError) {
      setError(authError.message)
      setLoading(false)
    }
  }

  return (
    <div style={{
      minHeight: '100vh',
      background: '#0a0a0a',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '1rem',
    }}>
      <div style={{
        width: '100%',
        maxWidth: 400,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 0,
      }}>
        <div style={{
          fontFamily: 'Georgia, serif',
          fontSize: '2.8rem',
          letterSpacing: '0.55em',
          paddingLeft: '0.55em',
          color: '#f3ead9',
          fontWeight: 400,
          userSelect: 'none',
        }}>
          RUE
        </div>
        <div style={{
          fontFamily: 'system-ui, sans-serif',
          fontSize: '0.65rem',
          letterSpacing: '0.4em',
          paddingLeft: '0.4em',
          color: 'rgba(243,234,217,0.4)',
          textTransform: 'uppercase',
          fontWeight: 400,
          marginTop: 4,
        }}>
          by MG &amp; Co
        </div>

        <div style={{
          fontFamily: 'Georgia, serif',
          fontSize: '1.05rem',
          color: 'rgba(243,234,217,0.55)',
          fontWeight: 300,
          marginTop: 32,
          marginBottom: 40,
          textAlign: 'center',
          lineHeight: 1.5,
        }}>
          Your personal AI. Sign in to continue.
        </div>

        <button
          onClick={handleLogin}
          disabled={loading}
          style={{
            width: '100%',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 14,
            padding: '14px 24px',
            background: 'rgba(243,234,217,0.04)',
            border: '1px solid rgba(243,234,217,0.12)',
            borderRadius: 12,
            cursor: loading ? 'default' : 'pointer',
            transition: 'border-color 250ms ease, background 250ms ease',
            outline: 'none',
            opacity: loading ? 0.6 : 1,
          }}
          onMouseEnter={e => {
            if (!loading) {
              e.currentTarget.style.borderColor = 'rgba(255,144,114,0.4)'
              e.currentTarget.style.background = 'rgba(255,144,114,0.05)'
            }
          }}
          onMouseLeave={e => {
            e.currentTarget.style.borderColor = 'rgba(243,234,217,0.12)'
            e.currentTarget.style.background = 'rgba(243,234,217,0.04)'
          }}
        >
          <svg width="18" height="18" viewBox="0 0 18 18" xmlns="http://www.w3.org/2000/svg">
            <path d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.875 2.684-6.615z" fill="#4285F4"/>
            <path d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332C2.438 15.983 5.482 18 9 18z" fill="#34A853"/>
            <path d="M3.964 10.71c-.18-.54-.282-1.117-.282-1.71s.102-1.17.282-1.71V4.958H.957C.347 6.173 0 7.548 0 9s.348 2.827.957 4.042l3.007-2.332z" fill="#FBBC05"/>
            <path d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0 5.482 0 2.438 2.017.957 4.958L3.964 6.29C4.672 4.163 6.656 3.58 9 3.58z" fill="#EA4335"/>
          </svg>
          <span style={{
            fontFamily: 'system-ui, sans-serif',
            fontSize: '0.9rem',
            letterSpacing: '0.08em',
            color: '#f3ead9',
            fontWeight: 400,
          }}>
            {loading ? 'Redirecting...' : 'Continue with Google'}
          </span>
        </button>

        {error && (
          <div style={{
            marginTop: 16,
            fontFamily: 'system-ui, sans-serif',
            fontSize: '0.75rem',
            color: '#ef4444',
            textAlign: 'center',
          }}>
            {error}
          </div>
        )}

        <div style={{
          marginTop: 48,
          fontFamily: 'system-ui, sans-serif',
          fontSize: '0.65rem',
          color: 'rgba(243,234,217,0.25)',
          letterSpacing: '0.1em',
          textAlign: 'center',
          lineHeight: 1.8,
        }}>
          Your conversation and memory persist<br />
          across every session.
        </div>
      </div>
    </div>
  )
}
