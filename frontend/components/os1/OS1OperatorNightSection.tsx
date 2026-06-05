"use client"

import { useScrollReveal } from "@/hooks/useScrollReveal"

const CYCLES = [
  {
    time: "11:00 PM",
    label: "CYCLE 1 — SCAN",
    desc: "Operator scans all connected apps. Calendar gaps, unanswered emails, overdue invoices, inventory alerts.",
  },
  {
    time: "1:00 AM",
    label: "CYCLE 2 — PLAN",
    desc: "It drafts a prioritized action queue. Morning meetings get prep docs. Follow-ups get drafted. Risks get flagged.",
  },
  {
    time: "3:00 AM",
    label: "CYCLE 3 — EXECUTE",
    desc: "Safe actions run automatically. Dangerous ones queue for your morning approval. Budget cap: $5/day.",
  },
  {
    time: "6:00 AM",
    label: "CYCLE 4 — BRIEF",
    desc: "You wake up to a Morning Briefing: what happened overnight, what needs your approval, what's ready to go.",
  },
]

export default function OS1OperatorNightSection() {
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
          OPERATOR AGENT
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
          It thinks while<br />
          <span style={{ color: "#c84b31" }}>you sleep.</span>
        </h2>

        <p
          className="os1-fade-up os1-fade-up-delay-2 text-center max-w-xl mx-auto mb-20"
          style={{ fontFamily: "'Inter', sans-serif", fontSize: "16px", lineHeight: 1.7, color: "rgba(243,234,217,0.5)" }}
        >
          Every night, the Operator Agent runs a 4-cycle autonomous pipeline across your entire business stack. No prompts. No babysitting.
        </p>

        <div className="relative">
          <div
            className="absolute left-6 md:left-1/2 top-0 bottom-0 w-px"
            style={{ background: "linear-gradient(to bottom, transparent, rgba(200,75,49,0.3), rgba(200,75,49,0.3), transparent)" }}
          />

          {CYCLES.map((cycle, i) => (
            <div
              key={cycle.label}
              className={`os1-fade-up os1-fade-up-delay-${i + 1} relative flex flex-col md:flex-row items-start md:items-center gap-6 mb-16 last:mb-0`}
            >
              <div className="md:w-1/2 md:text-right md:pr-12">
                <span className="font-arcade" style={{ fontSize: "8px", color: "#c84b31", letterSpacing: "0.2em" }}>
                  {cycle.time}
                </span>
              </div>

              <div
                className="absolute left-6 md:left-1/2 -translate-x-1/2 w-3 h-3 rounded-full"
                style={{ backgroundColor: "#c84b31", boxShadow: "0 0 12px rgba(200,75,49,0.6)" }}
              />

              <div className="md:w-1/2 md:pl-12 pl-12">
                <h3
                  className="font-arcade mb-2"
                  style={{ fontSize: "10px", color: "#f3ead9", letterSpacing: "0.1em" }}
                >
                  {cycle.label}
                </h3>
                <p style={{ fontFamily: "'Inter', sans-serif", fontSize: "14px", lineHeight: 1.7, color: "rgba(243,234,217,0.5)" }}>
                  {cycle.desc}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
