"use client"

import { useScrollReveal } from "@/hooks/useScrollReveal"

export default function OS1SafetySection() {
  const ref = useScrollReveal()

  return (
    <section
      ref={ref}
      className="relative py-32 px-6 overflow-hidden"
      style={{ backgroundColor: "#0a0a0a" }}
    >
      <div className="max-w-5xl mx-auto">
        <p
          className="os1-fade-up font-arcade text-center mb-6"
          style={{ fontSize: "9px", letterSpacing: "0.4em", color: "rgba(243,234,217,0.35)" }}
        >
          TRUST ARCHITECTURE
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
          Autonomous.<br />
          <span style={{ color: "#c84b31" }}>Never reckless.</span>
        </h2>

        <p
          className="os1-fade-up os1-fade-up-delay-2 text-center max-w-xl mx-auto mb-20"
          style={{ fontFamily: "'Inter', sans-serif", fontSize: "16px", lineHeight: 1.7, color: "rgba(243,234,217,0.5)" }}
        >
          Every write action requires human confirmation. Every overnight run has a budget cap. Every dangerous operation queues for your morning approval.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {[
            {
              title: "HOLD-TO-CONFIRM",
              desc: "Sending an email? Creating a calendar event? Modifying data? You press and hold for 2 seconds. No accidental executions. Ever.",
              accent: "2s",
            },
            {
              title: "$5/DAY BUDGET CAP",
              desc: "The Operator Agent has a daily spend limit. It can't drain your Stripe or blow your ad budget overnight. You control the ceiling.",
              accent: "$5",
            },
            {
              title: "MORNING APPROVAL QUEUE",
              desc: "Overnight runs queue all write actions. You wake up, review the list, approve or reject in batch. Full transparency.",
              accent: "AM",
            },
            {
              title: "READ/WRITE SEPARATION",
              desc: "Reading your calendar? Instant. Deleting a meeting? Requires confirmation. Every action is classified by risk level.",
              accent: "R/W",
            },
          ].map((item, i) => (
            <div
              key={item.title}
              className={`os1-fade-up os1-fade-up-delay-${i + 1} p-8 rounded-xl relative overflow-hidden`}
              style={{ backgroundColor: "rgba(243,234,217,0.02)", border: "1px solid rgba(243,234,217,0.06)" }}
            >
              <span
                className="absolute top-4 right-6"
                style={{ fontFamily: "'Instrument Serif', serif", fontSize: "48px", color: "rgba(200,75,49,0.08)", lineHeight: 1 }}
              >
                {item.accent}
              </span>
              <h3
                className="font-arcade mb-3 relative z-10"
                style={{ fontSize: "10px", color: "#f3ead9", letterSpacing: "0.12em" }}
              >
                {item.title}
              </h3>
              <p className="relative z-10" style={{ fontFamily: "'Inter', sans-serif", fontSize: "14px", lineHeight: 1.7, color: "rgba(243,234,217,0.5)" }}>
                {item.desc}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
