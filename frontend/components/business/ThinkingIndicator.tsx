"use client"

import { useEffect, useState } from "react"

const THINKING_PHRASES = [
  "thinking",
  "processing",
  "analyzing",
  "working on it",
  "on it",
  "cooking",
]

export default function ThinkingIndicator() {
  const [dots, setDots] = useState("")
  const [phraseIndex, setPhraseIndex] = useState(0)

  useEffect(() => {
    const interval = setInterval(() => {
      setDots((prev) => (prev.length >= 3 ? "" : prev + "."))
    }, 400)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    const interval = setInterval(() => {
      setPhraseIndex((prev) => (prev + 1) % THINKING_PHRASES.length)
    }, 4000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "4px 0 16px" }}>
      <div style={{ position: "relative", display: "flex", alignItems: "center", justifyContent: "center", width: 28, height: 28 }}>
        <div
          style={{
            position: "absolute",
            width: 28,
            height: 28,
            borderRadius: "50%",
            backgroundColor: "rgba(200,75,49,0.15)",
            animation: "thinkPulseOuter 1.5s ease-in-out infinite",
          }}
        />
        <div
          style={{
            position: "relative",
            width: 10,
            height: 10,
            borderRadius: "50%",
            backgroundColor: "#c84b31",
            boxShadow: "0 0 12px rgba(200,75,49,0.5)",
            animation: "thinkPulseInner 1.5s ease-in-out infinite",
          }}
        />
      </div>
      <span
        style={{
          fontFamily: "'var(--font-arcade)', monospace",
          fontSize: 8,
          color: "rgba(243,234,217,0.4)",
          letterSpacing: "0.12em",
          minWidth: 120,
        }}
      >
        {THINKING_PHRASES[phraseIndex]}{dots}
      </span>
    </div>
  )
}
