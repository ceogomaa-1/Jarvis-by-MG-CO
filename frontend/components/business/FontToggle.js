'use client'
import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { getStoredFontPref, setFontPref, saveFontPref } from '../../lib/fontPref'

// OS1 v2 — "Readable Font" row for the menu panel, directly under My Profile.
// Reuses the horizontal pixel rocker switch from AutonomousToggle (Batch 45).
export default function FontToggle({ userId }) {
  const [isNormal, setIsNormal] = useState(false)

  useEffect(() => {
    setIsNormal(getStoredFontPref() === 'normal')
  }, [])

  function handleToggle() {
    const next = !isNormal
    setIsNormal(next)
    const pref = next ? 'normal' : 'pixel'
    setFontPref(pref)
    if (userId) saveFontPref(userId, pref)
  }

  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      gap: 10, padding: '2px 2px 16px',
    }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 3, minWidth: 0 }}>
        <span className="font-pixel" style={{ fontSize: 12, lineHeight: 1.3, color: 'var(--os1-text-dim)' }}>
          Readable Font
        </span>
        <span className="os1-serif-micro" style={{ fontSize: 9, lineHeight: 1.35 }}>
          switch to a normal font everyone can read
        </span>
      </div>

      {/* Horizontal pixel rocker switch */}
      <button
        onClick={handleToggle}
        title="Readable Font"
        style={{
          position: 'relative',
          flexShrink: 0,
          width: 56,
          height: 26,
          borderRadius: 999,
          border: `1px solid ${isNormal ? '#cf8a5b' : '#3a332b'}`,
          background: isNormal ? 'rgba(207,138,91,0.25)' : '#221e19',
          cursor: 'pointer',
          padding: 0,
          transition: 'background 0.3s ease, border-color 0.3s ease',
        }}
      >
        {/* Micro-labels */}
        <span className="font-pixel" style={{
          position: 'absolute', left: 6, top: '50%', transform: 'translateY(-50%)',
          fontSize: 7, lineHeight: 1, color: '#6a6a6a', userSelect: 'none',
        }}>
          OFF
        </span>
        <span className="font-pixel" style={{
          position: 'absolute', right: 6, top: '50%', transform: 'translateY(-50%)',
          fontSize: 7, lineHeight: 1, color: isNormal ? '#cf8a5b' : '#6a6a6a', userSelect: 'none',
          transition: 'color 0.3s ease',
        }}>
          ON
        </span>

        {/* Knob */}
        <motion.div
          animate={{ x: isNormal ? 30 : 0 }}
          transition={{ type: 'spring', stiffness: 500, damping: 30 }}
          style={{
            position: 'absolute', top: 2, left: 2,
            width: 20, height: 20, borderRadius: 4,
            background: isNormal ? '#cf8a5b' : '#8c857b',
            boxShadow: isNormal ? '0 0 10px rgba(207,138,91,0.6)' : 'none',
          }}
        />
      </button>
    </div>
  )
}
