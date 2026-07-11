"use client"

import { useScrollReveal } from "@/hooks/useScrollReveal"
import { useEffect, useState, useRef } from "react"

function AnimatedCounter({ target, suffix = "" }: { target: number; suffix?: string }) {
  const [count, setCount] = useState(0)
  const ref = useRef<HTMLSpanElement>(null)
  const started = useRef(false)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && !started.current) {
          started.current = true
          const duration = 2000
          const startTime = performance.now()
          const animate = (now: number) => {
            const elapsed = now - startTime
            const progress = Math.min(elapsed / duration, 1)
            const eased = 1 - Math.pow(1 - progress, 3)
            setCount(Math.floor(eased * target))
            if (progress < 1) requestAnimationFrame(animate)
          }
          requestAnimationFrame(animate)
        }
      },
      { threshold: 0.5 }
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [target])

  return <span ref={ref}>{count}{suffix}</span>
}

export default function OS1MemorySection() {
  const ref = useScrollReveal()

  return (
    <section
      ref={ref}
      className="relative py-32 px-6 overflow-hidden"
      style={{ backgroundColor: "#0a0a0a" }}
    >
      <div className="max-w-6xl mx-auto">
        <p
          className="os1-fade-up font-arcade text-center mb-6"
          style={{ fontSize: "9px", letterSpacing: "0.4em", color: "rgba(243,234,217,0.35)" }}
        >
          COMPOUNDING INTELLIGENCE
        </p>

        <h2
          className="os1-fade-up os1-fade-up-delay-1 text-center mb-6"
          style={{
            fontFamily: "'Instrument Serif', serif",
            fontSize: "clamp(36px, 5vw, 72px)",
            color: "#f3ead9",
            lineHeight: 1.1,
            fontWeight: 400,
          }}
        >
          Every conversation<br />
          <span style={{ color: "#c84b31" }}>makes it sharper.</span>
        </h2>

        <p
          className="os1-fade-up os1-fade-up-delay-2 text-center max-w-xl mx-auto mb-20"
          style={{ fontFamily: "'Inter', sans-serif", fontSize: "16px", lineHeight: 1.7, color: "rgba(243,234,217,0.5)" }}
        >
          Rue doesn't start from zero. It extracts facts, preferences, and patterns from every exchange and builds a permanent memory layer that compounds over time.
        </p>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-6 mb-20">
          {[
            { value: 30, suffix: "+", label: "MEMORIES / USER" },
            { value: 7, suffix: "", label: "INDUSTRY BIBLES" },
            { value: 4, suffix: "", label: "NIGHTLY CYCLES" },
            { value: 200, suffix: "hr", label: "SETUP REPLACED" },
          ].map((stat, i) => (
            <div
              key={stat.label}
              className={`os1-fade-up os1-fade-up-delay-${i + 1} text-center p-6 rounded-xl`}
              style={{ backgroundColor: "rgba(243,234,217,0.02)", border: "1px solid rgba(243,234,217,0.06)" }}
            >
              <div style={{ fontFamily: "'Instrument Serif', serif", fontSize: "clamp(36px, 4vw, 56px)", color: "#c84b31", lineHeight: 1 }}>
                <AnimatedCounter target={stat.value} suffix={stat.suffix} />
              </div>
              <p
                className="font-arcade mt-3"
                style={{ fontSize: "7px", letterSpacing: "0.2em", color: "rgba(243,234,217,0.35)" }}
              >
                {stat.label}
              </p>
            </div>
          ))}
        </div>

        <div className="os1-fade-up os1-fade-up-delay-2 max-w-2xl mx-auto space-y-3">
          {[
            "Owner prefers follow-up emails sent before 9 AM on weekdays",
            "Business has 3 active service packages — Premium is top seller",
            "Q4 revenue target: increase repeat bookings by 22%",
            "Stripe shows Tuesday and Thursday as highest-grossing days",
            "Team lead Sarah handles all enterprise client onboarding",
            "Preferred tone for client emails: warm, professional, no jargon",
            "Seasonal discount campaign planned for first week of December",
          ].map((memory, i) => (
            <div
              key={i}
              className="flex items-start gap-3 px-4 py-3 rounded-lg"
              style={{ backgroundColor: "rgba(243,234,217,0.02)", border: "1px solid rgba(243,234,217,0.04)" }}
            >
              <span style={{ color: "#c84b31", fontSize: "10px", marginTop: "4px" }}>●</span>
              <p style={{ fontFamily: "'Inter', sans-serif", fontSize: "13px", lineHeight: 1.6, color: "rgba(243,234,217,0.45)" }}>
                {memory}
              </p>
            </div>
          ))}
          <p
            className="font-arcade text-center pt-4"
            style={{ fontSize: "7px", color: "rgba(243,234,217,0.2)", letterSpacing: "0.2em" }}
          >
            EXAMPLE MEMORIES FROM A LIVE RUE INSTANCE
          </p>
        </div>
      </div>
    </section>
  )
}
