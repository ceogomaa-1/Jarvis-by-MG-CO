'use client'
import { useState, useEffect } from 'react'

export default function ReadinessBar({ userId, apiUrl, onReadinessUpdate }) {
  const [readiness, setReadiness] = useState(null)

  useEffect(() => {
    if (!userId) return
    fetchReadiness()
    const interval = setInterval(fetchReadiness, 30000)
    return () => clearInterval(interval)
  }, [userId])

  async function fetchReadiness() {
    try {
      const res = await fetch(`${apiUrl}/api/business/readiness?user_id=${encodeURIComponent(userId)}`)
      const data = await res.json()
      setReadiness(data)
      onReadinessUpdate?.(data)
    } catch (e) {
      console.error('Readiness fetch failed:', e)
    }
  }

  const score = readiness?.score ?? 20

  return (
    <div className="os1-readiness">
      <div className="os1-readiness-label">Jarvis Knows About Me...</div>
      <div className="os1-readiness-row">
        <div className="os1-readiness-track">
          <div className="os1-readiness-fill" style={{ width: `${Math.max(6, Math.min(score, 100))}%` }} />
        </div>
        <span>{score}%</span>
      </div>
    </div>
  )
}
