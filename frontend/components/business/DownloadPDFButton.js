'use client'
import { useState } from 'react'

const BACKEND = 'https://jarvis-backend-4oz6.onrender.com'

export default function DownloadPDFButton({ walkthrough }) {
  const [loading, setLoading] = useState(false)

  const handleDownload = async () => {
    if (!walkthrough || loading) return
    setLoading(true)
    try {
      const res = await fetch(`${BACKEND}/api/business/show-me-how/pdf`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ walkthrough }),
      })
      if (!res.ok) throw new Error('PDF generation failed')
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${(walkthrough.title || 'walkthrough').slice(0, 40)}.pdf`
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      console.error('PDF download failed:', err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <button
      onClick={handleDownload}
      disabled={loading}
      style={{
        marginTop: 16,
        background: 'transparent',
        border: '1px solid rgba(255,46,81,0.4)',
        borderRadius: 6,
        padding: '8px 16px',
        color: '#ff2e51',
        cursor: loading ? 'wait' : 'pointer',
        fontFamily: 'system-ui, sans-serif',
        fontSize: 11,
        letterSpacing: '0.1em',
        textTransform: 'uppercase',
        display: 'inline-flex',
        alignItems: 'center',
        gap: 8,
        transition: 'border-color 200ms, opacity 200ms',
        opacity: loading ? 0.6 : 1,
      }}
    >
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/>
      </svg>
      {loading ? 'Generating PDF...' : 'Download as PDF'}
    </button>
  )
}
