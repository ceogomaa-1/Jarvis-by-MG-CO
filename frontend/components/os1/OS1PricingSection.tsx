"use client"

import { useScrollReveal } from "@/hooks/useScrollReveal"

const TIERS = [
  {
    name: "LITE",
    price: "$49",
    period: "/mo",
    desc: "For solo operators who want AI chat with basic automation.",
    features: ["AI Chat (unlimited)", "5 Creation tasks/month", "1 connector", "Basic memory"],
    cta: "Start Lite",
    accent: false,
  },
  {
    name: "PRO",
    price: "$199",
    period: "/mo",
    desc: "Full stack AI operator with connectors and intelligence.",
    features: [
      "Everything in Lite",
      "Unlimited Creation tasks",
      "Risk Management Cron",
      "3 connectors included",
      "Brand system",
      "Compounding memory",
    ],
    cta: "Go Pro",
    accent: true,
  },
  {
    name: "HQ",
    price: "$499",
    period: "/mo",
    desc: "Autonomous mode. Operator Agent. Your AI-powered fractional COO.",
    features: [
      "Everything in Pro",
      "Operator Agent (4-cycle overnight)",
      "Unlimited connectors",
      "Custom Industry Bibles",
      "Priority model routing",
      "Morning Approval Queue",
      "Dedicated onboarding",
    ],
    cta: "Enter HQ",
    accent: false,
  },
]

export default function OS1PricingSection() {
  const ref = useScrollReveal()

  return (
    <section
      id="pricing"
      ref={ref}
      className="relative py-32 px-6 overflow-hidden os1-grain"
      style={{ backgroundColor: "#060606" }}
    >
      <div className="max-w-6xl mx-auto relative z-10">
        <p
          className="os1-fade-up font-arcade text-center mb-6"
          style={{ fontSize: "9px", letterSpacing: "0.4em", color: "rgba(243,234,217,0.35)" }}
        >
          PRICING
        </p>

        <h2
          className="os1-fade-up os1-fade-up-delay-1 text-center mb-20"
          style={{
            fontFamily: "'Instrument Serif', serif",
            fontSize: "clamp(36px, 5vw, 72px)",
            color: "#f3ead9",
            lineHeight: 1.1,
            fontWeight: 400,
          }}
        >
          Less than your worst hire.<br />
          <span style={{ color: "#c84b31" }}>Smarter than your best.</span>
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {TIERS.map((tier, i) => (
            <div
              key={tier.name}
              className={`os1-fade-up os1-fade-up-delay-${i + 1} relative p-8 rounded-2xl flex flex-col`}
              style={{
                backgroundColor: tier.accent ? "rgba(200,75,49,0.06)" : "rgba(243,234,217,0.02)",
                border: tier.accent ? "1px solid rgba(200,75,49,0.3)" : "1px solid rgba(243,234,217,0.06)",
              }}
            >
              {tier.accent && (
                <span
                  className="font-arcade absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-1 rounded-full"
                  style={{ fontSize: "6px", letterSpacing: "0.15em", color: "#0a0a0a", backgroundColor: "#c84b31" }}
                >
                  MOST POPULAR
                </span>
              )}

              <p
                className="font-arcade"
                style={{ fontSize: "11px", color: tier.accent ? "#c84b31" : "#f3ead9", letterSpacing: "0.2em" }}
              >
                {tier.name}
              </p>

              <div className="flex items-baseline gap-1 mt-4 mb-2">
                <span style={{ fontFamily: "'Instrument Serif', serif", fontSize: "48px", color: "#f3ead9", lineHeight: 1 }}>
                  {tier.price}
                </span>
                <span style={{ fontFamily: "'Inter', sans-serif", fontSize: "14px", color: "rgba(243,234,217,0.35)" }}>
                  {tier.period}
                </span>
              </div>

              <p className="mb-6" style={{ fontFamily: "'Inter', sans-serif", fontSize: "14px", lineHeight: 1.6, color: "rgba(243,234,217,0.45)" }}>
                {tier.desc}
              </p>

              <ul className="space-y-3 mb-8 flex-1">
                {tier.features.map((f) => (
                  <li key={f} className="flex items-start gap-2" style={{ fontFamily: "'Inter', sans-serif", fontSize: "13px", color: "rgba(243,234,217,0.55)" }}>
                    <span style={{ color: "#c84b31", marginTop: "2px" }}>✓</span>
                    {f}
                  </li>
                ))}
              </ul>

              <button
                className="font-arcade w-full py-3 rounded-lg text-center"
                style={{
                  fontSize: "9px",
                  letterSpacing: "0.1em",
                  backgroundColor: tier.accent ? "#c84b31" : "transparent",
                  color: tier.accent ? "#0a0a0a" : "#f3ead9",
                  border: tier.accent ? "none" : "1px solid rgba(243,234,217,0.15)",
                  cursor: "pointer",
                  transition: "opacity 0.2s",
                }}
              >
                {tier.cta}
              </button>
            </div>
          ))}
        </div>

        <p
          className="os1-fade-up text-center mt-8"
          style={{ fontFamily: "'Inter', sans-serif", fontSize: "13px", color: "rgba(243,234,217,0.3)" }}
        >
          Annual billing: Pro $1,990/yr · HQ $4,990/yr — save 2 months
        </p>
      </div>
    </section>
  )
}
