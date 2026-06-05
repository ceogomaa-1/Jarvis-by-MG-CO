"use client"

import { useScrollReveal } from "@/hooks/useScrollReveal"

const CONNECTORS = [
  { name: "Stripe", color: "#635BFF", status: "live", letter: "S" },
  { name: "Google Calendar", color: "#4285F4", status: "live", letter: "G" },
  { name: "Gmail", color: "#EA4335", status: "live", letter: "G" },
  { name: "ElevenLabs", color: "#FF6B35", status: "live", letter: "E" },
  { name: "Notion", color: "#FFFFFF", status: "live", letter: "N" },
  { name: "Twilio", color: "#F22F46", status: "ready", letter: "T" },
  { name: "GoHighLevel", color: "#00C853", status: "ready", letter: "G" },
  { name: "SMTP", color: "#FFB300", status: "ready", letter: "S" },
  { name: "Slack", color: "#4A154B", status: "coming", letter: "S" },
  { name: "Airtable", color: "#18BFFF", status: "coming", letter: "A" },
  { name: "Mailchimp", color: "#FFE01B", status: "coming", letter: "M" },
  { name: "Calendly", color: "#006BFF", status: "coming", letter: "C" },
]

export default function OS1ConnectorsSection() {
  const ref = useScrollReveal()

  return (
    <section
      ref={ref}
      className="relative py-32 px-6 overflow-hidden os1-grain"
      style={{ backgroundColor: "#060606" }}
    >
      <div className="max-w-5xl mx-auto relative z-10">
        <p
          className="os1-fade-up font-arcade text-center mb-6"
          style={{ fontSize: "9px", letterSpacing: "0.4em", color: "rgba(243,234,217,0.35)" }}
        >
          CONNECTED ECOSYSTEM
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
          Plugs into<br />
          <span style={{ color: "#c84b31" }}>everything you use.</span>
        </h2>

        <p
          className="os1-fade-up os1-fade-up-delay-2 text-center max-w-xl mx-auto mb-16"
          style={{ fontFamily: "'Inter', sans-serif", fontSize: "16px", lineHeight: 1.7, color: "rgba(243,234,217,0.5)" }}
        >
          One-click connectors. Real API integrations — not screenshots, not copy-paste. Jarvis reads, writes, and executes across your entire stack.
        </p>

        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
          {CONNECTORS.map((c, i) => (
            <div
              key={c.name}
              className={`os1-fade-up os1-fade-up-delay-${Math.min(i % 4 + 1, 4)} relative flex items-center gap-3 p-4 rounded-xl`}
              style={{
                backgroundColor: "rgba(243,234,217,0.02)",
                border: "1px solid rgba(243,234,217,0.06)",
                transition: "border-color 0.3s, background-color 0.3s",
                cursor: "default",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = c.color + "44"
                e.currentTarget.style.backgroundColor = c.color + "08"
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = "rgba(243,234,217,0.06)"
                e.currentTarget.style.backgroundColor = "rgba(243,234,217,0.02)"
              }}
            >
              <div
                className="w-8 h-8 rounded-lg flex items-center justify-center text-xs font-bold shrink-0"
                style={{
                  backgroundColor: c.color + "20",
                  color: c.color === "#FFFFFF" ? "#f3ead9" : c.color,
                  fontFamily: "'Inter', sans-serif",
                }}
              >
                {c.letter}
              </div>
              <div>
                <p style={{ fontFamily: "'Inter', sans-serif", fontSize: "13px", color: "#f3ead9", lineHeight: 1.2 }}>
                  {c.name}
                </p>
                <p
                  className="font-arcade"
                  style={{
                    fontSize: "5px",
                    letterSpacing: "0.15em",
                    color:
                      c.status === "live" ? "#22c55e"
                      : c.status === "ready" ? "rgba(243,234,217,0.35)"
                      : "rgba(243,234,217,0.2)",
                    marginTop: "2px",
                  }}
                >
                  {c.status === "live" ? "● LIVE" : c.status === "ready" ? "○ READY" : "◌ COMING"}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
