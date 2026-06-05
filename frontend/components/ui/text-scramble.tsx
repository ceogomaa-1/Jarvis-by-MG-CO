"use client"

import { useState, useCallback, useRef, useEffect } from "react"

const CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%&*"

interface TextScrambleProps {
  text: string
  className?: string
  onClick?: () => void
}

export function TextScramble({ text, className = "", onClick }: TextScrambleProps) {
  const [displayText, setDisplayText] = useState(text)
  const [isHovering, setIsHovering] = useState(false)
  const [isScrambling, setIsScrambling] = useState(false)
  const intervalRef = useRef<NodeJS.Timeout | null>(null)
  const frameRef = useRef(0)

  const scramble = useCallback(() => {
    setIsScrambling(true)
    frameRef.current = 0
    const duration = text.length * 3

    if (intervalRef.current) clearInterval(intervalRef.current)

    intervalRef.current = setInterval(() => {
      frameRef.current++

      const progress = frameRef.current / duration
      const revealedLength = Math.floor(progress * text.length)

      const newText = text
        .split("")
        .map((char, i) => {
          if (char === " ") return " "
          if (i < revealedLength) return text[i]
          return CHARS[Math.floor(Math.random() * CHARS.length)]
        })
        .join("")

      setDisplayText(newText)

      if (frameRef.current >= duration) {
        if (intervalRef.current) clearInterval(intervalRef.current)
        setDisplayText(text)
        setIsScrambling(false)
      }
    }, 30)
  }, [text])

  const handleMouseEnter = () => {
    setIsHovering(true)
    scramble()
  }

  const handleMouseLeave = () => {
    setIsHovering(false)
  }

  useEffect(() => {
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [])

  return (
    <div
      className={`group relative inline-flex flex-col cursor-pointer select-none ${className}`}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onClick={onClick}
    >
      <span
        className="relative tracking-widest uppercase text-4xl md:text-5xl lg:text-6xl"
        style={{ fontFamily: "var(--font-arcade), 'Press Start 2P', monospace" }}
      >
        {displayText.split("").map((char, i) => (
          <span
            key={i}
            className={`inline-block transition-all duration-150 ${
              isScrambling && char !== text[i] ? "scale-110" : ""
            }`}
            style={{
              transitionDelay: `${i * 10}ms`,
              color: isScrambling && char !== text[i] ? "#c84b31" : "#f3ead9",
            }}
          >
            {char}
          </span>
        ))}
      </span>

      {/* Animated underline */}
      <span className="relative h-px w-full mt-3 overflow-hidden">
        <span
          className="absolute inset-0 transition-transform duration-500 ease-out origin-left"
          style={{
            backgroundColor: "#c84b31",
            transform: isHovering ? "scaleX(1)" : "scaleX(0)",
          }}
        />
        <span className="absolute inset-0" style={{ backgroundColor: "rgba(243,234,217,0.15)" }} />
      </span>

      {/* Subtle glow on hover */}
      <span
        className="absolute rounded-lg transition-opacity duration-300 -z-10"
        style={{
          inset: "-16px",
          backgroundColor: "rgba(200,75,49,0.07)",
          opacity: isHovering ? 1 : 0,
        }}
      />
    </div>
  )
}
