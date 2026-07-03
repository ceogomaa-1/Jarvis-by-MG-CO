'use client'
import { useState, useEffect } from 'react'
import LoadingTransition from './LoadingTransition'
import { FallingPattern } from './FallingPattern'
import { preloadSounds } from '../../lib/soundPlayer'

import { BACKEND } from '@/lib/backend'

const TIMEZONE_OPTIONS = [
  { label: 'Toronto / New York (ET)', value: 'America/Toronto' },
  { label: 'Chicago / Dallas (CT)', value: 'America/Chicago' },
  { label: 'Denver / Phoenix (MT)', value: 'America/Denver' },
  { label: 'Los Angeles / Vancouver (PT)', value: 'America/Los_Angeles' },
  { label: 'Halifax (AT)', value: 'America/Halifax' },
  { label: 'London / Dublin (GMT)', value: 'Europe/London' },
  { label: 'Paris / Berlin (CET)', value: 'Europe/Paris' },
  { label: 'Cairo / Helsinki (EET)', value: 'Africa/Cairo' },
  { label: 'Dubai / Riyadh (GST)', value: 'Asia/Dubai' },
  { label: 'Mumbai / Karachi (IST)', value: 'Asia/Kolkata' },
  { label: 'Singapore / Beijing (SGT)', value: 'Asia/Singapore' },
  { label: 'Tokyo (JST)', value: 'Asia/Tokyo' },
  { label: 'Sydney (AEST)', value: 'Australia/Sydney' },
]

export default function TimezoneStep({ onConfirm, userId }) {
  const [selected, setSelected] = useState('')
  const [detected, setDetected] = useState('')
  const [name, setName] = useState('')
  const [showTransition, setShowTransition] = useState(false)

  useEffect(() => {
    preloadSounds()
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone
    setDetected(tz)
    const match = TIMEZONE_OPTIONS.find(opt => opt.value === tz)
    setSelected(match ? tz : 'America/Toronto')
  }, [])

  async function handleConfirm() {
    if (!selected) return
    if (name.trim() && userId) {
      try {
        await fetch(`${BACKEND}/api/user-preferences/preferred-name`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user_id: userId, preferred_name: name.trim() }),
        })
      } catch {}
    }
    setShowTransition(true)
  }

  if (showTransition) {
    return <LoadingTransition onComplete={() => onConfirm(selected)} />
  }

  return (
    <div style={{
      position: 'relative',
      minHeight: '100vh',
      background: 'rgba(10,10,10,0.3)',
      overflow: 'hidden',
    }}>
      {/* Animated background */}
      <div
        style={{
          position: 'fixed',
          inset: 0,
          zIndex: 0,
          pointerEvents: 'none',
          overflow: 'hidden',
        }}
      >
        <FallingPattern
          color="#c84b31"
          backgroundColor="#0a0a0a"
          duration={180}
          blurIntensity="0.9em"
          density={1}
        />
      </div>

      {/* Content */}
      <div style={{
        position: 'relative', zIndex: 2,
        display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
        minHeight: '100vh',
        padding: '40px 24px',
        color: '#f3ead9',
      }}>
        {/* Wordmark */}
        <div style={{ marginBottom: 48, textAlign: 'center' }}>
          <div style={{ fontFamily: 'Georgia, serif', fontSize: 22, letterSpacing: '0.4em', color: '#f3ead9', fontWeight: 400, marginBottom: 4 }}>
            JARVIS
          </div>
          <div style={{ fontFamily: 'system-ui, sans-serif', fontSize: 10, letterSpacing: '0.3em', color: 'rgba(243,234,217,0.35)', textTransform: 'uppercase' }}>
            BY MG & CO
          </div>
        </div>

        {/* Heading */}
        <div style={{ textAlign: 'center', marginBottom: 36, maxWidth: 340 }}>
          <h2 style={{
            fontFamily: 'Georgia, serif',
            fontSize: 22,
            fontWeight: 400,
            letterSpacing: '0.04em',
            marginBottom: 12,
            color: '#f3ead9',
          }}>
            Where are you?
          </h2>
          <p style={{
            fontFamily: 'system-ui, sans-serif',
            fontSize: 14,
            color: 'rgba(243,234,217,0.5)',
            lineHeight: 1.6,
            margin: 0,
          }}>
            Jarvis needs your timezone to get time references right — reminders, calendar events, and anything time-related.
          </p>
          {detected && (
            <p style={{
              fontFamily: 'system-ui, sans-serif',
              fontSize: 12,
              color: 'rgba(243,234,217,0.28)',
              marginTop: 10,
              margin: '10px 0 0',
            }}>
              Detected: {detected}
            </p>
          )}
        </div>

        {/* Options list */}
        <div style={{
          width: '100%',
          maxWidth: 360,
          display: 'flex',
          flexDirection: 'column',
          gap: 8,
          marginBottom: 28,
          maxHeight: 360,
          overflowY: 'auto',
          paddingRight: 4,
        }}>
          {TIMEZONE_OPTIONS.map(tz => (
            <button
              key={tz.value}
              onClick={() => setSelected(tz.value)}
              style={{
                width: '100%',
                textAlign: 'left',
                padding: '13px 18px',
                borderRadius: 14,
                border: selected === tz.value
                  ? '1px solid rgba(200,75,49,0.6)'
                  : '1px solid rgba(243,234,217,0.1)',
                background: selected === tz.value
                  ? 'rgba(200,75,49,0.12)'
                  : 'rgba(243,234,217,0.03)',
                color: selected === tz.value ? '#f3ead9' : 'rgba(243,234,217,0.65)',
                fontFamily: 'system-ui, sans-serif',
                fontSize: 14,
                cursor: 'pointer',
                transition: 'all 150ms ease',
              }}
            >
              {tz.label}
            </button>
          ))}
        </div>

        {/* Name input */}
        <div style={{ width: '100%', maxWidth: 360, marginBottom: 16 }}>
          <label style={{
            display: 'block',
            fontFamily: 'system-ui, sans-serif',
            fontSize: 11,
            letterSpacing: '0.18em',
            color: 'rgba(243,234,217,0.4)',
            textTransform: 'uppercase',
            marginBottom: 10,
          }}>
            What should I call you?
          </label>
          <input
            value={name}
            onChange={e => setName(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') handleConfirm() }}
            placeholder="Your name or nickname"
            style={{
              width: '100%',
              padding: '13px 18px',
              borderRadius: 14,
              border: '1px solid rgba(243,234,217,0.1)',
              background: 'rgba(243,234,217,0.04)',
              color: '#f3ead9',
              fontFamily: 'system-ui, sans-serif',
              fontSize: 14,
              outline: 'none',
              boxSizing: 'border-box',
              transition: 'border-color 150ms ease',
            }}
            onFocus={e => e.target.style.borderColor = 'rgba(200,75,49,0.4)'}
            onBlur={e => e.target.style.borderColor = 'rgba(243,234,217,0.1)'}
          />
        </div>

        {/* Confirm button */}
        <button
          onClick={handleConfirm}
          disabled={!selected}
          style={{
            width: '100%',
            maxWidth: 360,
            padding: '15px 0',
            borderRadius: 14,
            background: selected ? '#f3ead9' : 'rgba(243,234,217,0.15)',
            color: selected ? '#0a0a0a' : 'rgba(243,234,217,0.3)',
            border: 0,
            fontFamily: 'system-ui, sans-serif',
            fontSize: 13,
            letterSpacing: '0.18em',
            textTransform: 'uppercase',
            fontWeight: 500,
            cursor: selected ? 'pointer' : 'default',
            transition: 'all 200ms ease',
          }}
        >
          This is me
        </button>
      </div>
    </div>
  )
}
