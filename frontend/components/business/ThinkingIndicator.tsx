"use client"

import { useEffect, useState } from "react"

const THINKING_PHRASES = [
  "Thinking",
  "Processing",
  "Analyzing",
  "Working on it",
  "On it",
  "Composing",
]

export default function ThinkingIndicator() {
  const [phraseIndex, setPhraseIndex] = useState(0)

  useEffect(() => {
    const interval = setInterval(() => {
      setPhraseIndex((prev) => (prev + 1) % THINKING_PHRASES.length)
    }, 4000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "4px 0 16px" }}>
      <div style={{ position: "relative", width: 22, height: 22 }}>
        <div
          style={{
            position: "absolute", inset: 0, borderRadius: "50%",
            border: "1px solid rgba(237,230,216,0.12)",
          }}
        />
        <div
          style={{
            position: "absolute", inset: -1, borderRadius: "50%",
            border: "1px solid transparent",
            borderTopColor: "var(--os1-accent, #cf8a5b)",
            animation: "os1ArcSpin 1.4s cubic-bezier(0.45, 0.1, 0.55, 0.9) infinite",
          }}
        />
      </div>
      <span className="os1-shimmer-label" style={{ minWidth: 120 }}>
        {THINKING_PHRASES[phraseIndex]}
      </span>
    </div>
  )
}
