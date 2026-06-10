// DEPRECATED (Batch 43): superseded by /business/onboarding (OS1Cinematic + OS1Questions).
// No longer invoked anywhere — kept in place for reference only.
'use client'
import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { supabase } from '../../lib/supabase'
import { createBusinessUser, setJarvisMode } from '../../lib/userPreferences'

const INDUSTRIES = [
  'Restaurants',
  'Real Estate',
  'Dental',
  'Salon/Spa',
  'Trades/Contractors',
  'Retail',
  'Law',
]

const ROLES = ['Owner', 'Manager', 'Operator']

const overlay = {
  position: 'fixed', inset: 0,
  background: 'rgba(0,0,0,0.82)',
  backdropFilter: 'blur(6px)',
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  zIndex: 1000,
  padding: '24px',
}

const card = {
  background: '#0f0e0d',
  border: '1px solid rgba(243,234,217,0.1)',
  borderRadius: 16,
  padding: '48px 40px',
  width: '100%',
  maxWidth: 480,
  position: 'relative',
}

export default function BusinessOnboardingModal({ onClose }) {
  const [step, setStep] = useState(1)
  const [form, setForm] = useState({ companyName: '', industry: '', role: '' })
  const [busy, setBusy] = useState(false)

  const step1Valid = form.companyName.trim() && form.industry && form.role

  const handleGoogleSignIn = async () => {
    if (!supabase) return
    // Store form data in sessionStorage so it survives the OAuth redirect
    sessionStorage.setItem('jarvis_biz_onboard', JSON.stringify(form))
    await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: {
        redirectTo: `${window.location.origin}/auth/callback?next=/business/chat&onboard=business`,
      },
    })
  }

  return (
    <div style={overlay} onClick={e => { if (e.target === e.currentTarget) onClose() }}>
      <style>{`
        select option {
          background-color: #1a1a1a;
          color: #e5e5e5;
        }
      `}</style>
      <AnimatePresence mode="wait">
        <motion.div
          key={step}
          style={card}
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -16 }}
          transition={{ duration: 0.28, ease: [0.25, 0.1, 0.25, 1] }}
        >
          {/* Close */}
          <button
            onClick={onClose}
            style={{
              position: 'absolute', top: 18, right: 20,
              background: 'none', border: 'none', cursor: 'pointer',
              color: 'rgba(243,234,217,0.3)', fontSize: 18, lineHeight: 1,
            }}
          >
            ×
          </button>

          {/* Step indicator */}
          <div style={{ display: 'flex', gap: 6, marginBottom: 32 }}>
            {[1, 2].map(n => (
              <div key={n} style={{
                height: 2, flex: 1, borderRadius: 2,
                background: step >= n ? '#f59e0b' : 'rgba(243,234,217,0.12)',
                transition: 'background 0.3s',
              }} />
            ))}
          </div>

          {step === 1 && (
            <>
              <div style={{ fontFamily: 'Georgia, serif', fontSize: 22, color: '#f3ead9', marginBottom: 6, letterSpacing: '0.02em' }}>
                Tell us about your business
              </div>
              <div style={{ fontFamily: 'system-ui, sans-serif', fontSize: 13, color: 'rgba(243,234,217,0.45)', marginBottom: 32, lineHeight: 1.5 }}>
                Jarvis personalizes every insight to your industry and role.
              </div>

              {/* Company name */}
              <label style={labelStyle}>Company name</label>
              <input
                type="text"
                value={form.companyName}
                onChange={e => setForm(f => ({ ...f, companyName: e.target.value }))}
                placeholder="e.g. Maple Street Grill"
                style={inputStyle}
              />

              {/* Industry */}
              <label style={{ ...labelStyle, marginTop: 20 }}>Industry</label>
              <select
                value={form.industry}
                onChange={e => setForm(f => ({ ...f, industry: e.target.value }))}
                style={{
                  ...inputStyle,
                  cursor: 'pointer',
                  appearance: 'none',
                  background: '#1a1a1a',
                  color: '#e5e5e5',
                  border: '1px solid #333',
                }}
                onFocus={e => { e.currentTarget.style.borderColor = '#f59e0b' }}
                onBlur={e => { e.currentTarget.style.borderColor = '#333' }}
              >
                <option value="">Select your industry</option>
                {INDUSTRIES.map(i => (
                  <option key={i} value={i}>{i}</option>
                ))}
              </select>

              {/* Role */}
              <label style={{ ...labelStyle, marginTop: 20 }}>Your role</label>
              <div style={{ display: 'flex', gap: 10 }}>
                {ROLES.map(r => (
                  <button
                    key={r}
                    onClick={() => setForm(f => ({ ...f, role: r.toLowerCase() }))}
                    style={{
                      flex: 1, padding: '10px 0',
                      border: `1px solid ${form.role === r.toLowerCase() ? '#f59e0b' : 'rgba(243,234,217,0.12)'}`,
                      borderRadius: 8,
                      background: form.role === r.toLowerCase() ? 'rgba(245,158,11,0.1)' : 'transparent',
                      color: form.role === r.toLowerCase() ? '#f59e0b' : 'rgba(243,234,217,0.5)',
                      fontFamily: 'system-ui, sans-serif',
                      fontSize: 12, letterSpacing: '0.06em',
                      cursor: 'pointer',
                      transition: 'all 0.2s',
                    }}
                  >
                    {r}
                  </button>
                ))}
              </div>

              <button
                disabled={!step1Valid}
                onClick={() => setStep(2)}
                style={{
                  ...ctaStyle,
                  marginTop: 36,
                  opacity: step1Valid ? 1 : 0.35,
                  cursor: step1Valid ? 'pointer' : 'default',
                }}
              >
                Continue →
              </button>
            </>
          )}

          {step === 2 && (
            <>
              <div style={{ fontFamily: 'Georgia, serif', fontSize: 22, color: '#f3ead9', marginBottom: 6, letterSpacing: '0.02em' }}>
                Connect your Google account
              </div>
              <div style={{ fontFamily: 'system-ui, sans-serif', fontSize: 13, color: 'rgba(243,234,217,0.45)', marginBottom: 32, lineHeight: 1.6 }}>
                Jarvis uses Google for calendar scheduling and email actions — so you can act, not just read.
              </div>

              {/* Summary */}
              <div style={{
                background: 'rgba(245,158,11,0.06)',
                border: '1px solid rgba(245,158,11,0.15)',
                borderRadius: 10, padding: '16px 20px', marginBottom: 32,
              }}>
                <div style={{ fontFamily: 'system-ui, sans-serif', fontSize: 11, color: 'rgba(243,234,217,0.35)', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 10 }}>
                  Your profile
                </div>
                <Row label="Company" value={form.companyName} />
                <Row label="Industry" value={form.industry} />
                <Row label="Role" value={form.role.charAt(0).toUpperCase() + form.role.slice(1)} />
              </div>

              <button onClick={handleGoogleSignIn} style={ctaStyle}>
                <GoogleIcon />
                Sign in with Google
              </button>

              <button
                onClick={() => setStep(1)}
                style={{
                  background: 'none', border: 'none', cursor: 'pointer',
                  color: 'rgba(243,234,217,0.3)', fontFamily: 'system-ui, sans-serif',
                  fontSize: 12, marginTop: 16, width: '100%', textAlign: 'center',
                  letterSpacing: '0.04em',
                }}
              >
                ← Back
              </button>
            </>
          )}
        </motion.div>
      </AnimatePresence>
    </div>
  )
}

function Row({ label, value }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
      <span style={{ fontFamily: 'system-ui, sans-serif', fontSize: 12, color: 'rgba(243,234,217,0.35)' }}>{label}</span>
      <span style={{ fontFamily: 'system-ui, sans-serif', fontSize: 12, color: 'rgba(243,234,217,0.75)', fontWeight: 500 }}>{value}</span>
    </div>
  )
}

function GoogleIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" style={{ marginRight: 10, flexShrink: 0 }}>
      <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
      <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
      <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"/>
      <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
    </svg>
  )
}

const labelStyle = {
  display: 'block',
  fontFamily: 'system-ui, sans-serif',
  fontSize: 11,
  letterSpacing: '0.1em',
  textTransform: 'uppercase',
  color: 'rgba(243,234,217,0.38)',
  marginBottom: 8,
}

const inputStyle = {
  width: '100%',
  padding: '11px 14px',
  background: 'rgba(243,234,217,0.04)',
  border: '1px solid rgba(243,234,217,0.1)',
  borderRadius: 8,
  color: '#f3ead9',
  fontFamily: 'system-ui, sans-serif',
  fontSize: 14,
  outline: 'none',
  boxSizing: 'border-box',
  transition: 'border-color 0.2s',
}

const ctaStyle = {
  width: '100%',
  padding: '13px 0',
  background: 'rgba(245,158,11,0.12)',
  border: '1px solid rgba(245,158,11,0.35)',
  borderRadius: 8,
  color: '#f59e0b',
  fontFamily: 'system-ui, sans-serif',
  fontSize: 13,
  letterSpacing: '0.06em',
  cursor: 'pointer',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  transition: 'background 0.2s, border-color 0.2s',
}
