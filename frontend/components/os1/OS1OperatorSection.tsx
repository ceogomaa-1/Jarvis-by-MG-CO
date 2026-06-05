"use client"

import { CpuArchitecture } from "@/components/ui/cpu-architecture"
import { useScrollReveal } from "@/hooks/useScrollReveal"

export default function OS1OperatorSection() {
  const ref = useScrollReveal()

  return (
    <section
      ref={ref}
      className="relative py-32 px-6 overflow-hidden"
      style={{ backgroundColor: "#0a0a0a" }}
    >
      <div
        className="absolute top-0 left-1/2 -translate-x-1/2"
        style={{
          width: "600px",
          height: "1px",
          background: "linear-gradient(90deg, transparent, rgba(200,75,49,0.4), transparent)",
        }}
      />

      <div className="max-w-6xl mx-auto">
        <p
          className="os1-fade-up font-arcade text-center mb-6"
          style={{ fontSize: "9px", letterSpacing: "0.4em", color: "rgba(243,234,217,0.35)" }}
        >
          THE BRAIN
        </p>

        <h2
          className="os1-fade-up os1-fade-up-delay-1 text-center mb-4"
          style={{
            fontFamily: "'Instrument Serif', serif",
            fontSize: "clamp(36px, 5vw, 72px)",
            color: "#f3ead9",
            lineHeight: 1.1,
            fontWeight: 400,
          }}
        >
          It doesn't just respond.<br />
          <span style={{ color: "#c84b31" }}>It orchestrates.</span>
        </h2>

        <p
          className="os1-fade-up os1-fade-up-delay-2 text-center max-w-2xl mx-auto mb-20"
          style={{
            fontFamily: "'Inter', sans-serif",
            fontSize: "17px",
            lineHeight: 1.7,
            color: "rgba(243,234,217,0.55)",
          }}
        >
          Creation 1.0 is the engine at the heart of Jarvis OS1. It doesn't wait for instructions — it spawns specialized AI agents, assigns them sub-tasks, supervises their execution, and synthesizes results. One prompt triggers an entire autonomous workforce.
        </p>

        <div className="os1-fade-up os1-fade-up-delay-3 max-w-3xl mx-auto">
          <div
            className="rounded-2xl p-8 md:p-12"
            style={{
              backgroundColor: "rgba(243,234,217,0.03)",
              border: "1px solid rgba(243,234,217,0.08)",
            }}
          >
            <CpuArchitecture text="Operator" animateText animateLines animateMarkers />
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-8 mt-16">
          {[
            {
              num: "01",
              title: "SPAWN",
              desc: "Jarvis creates purpose-built sub-agents for each task. Research, scheduling, outreach, analysis — each gets its own specialist.",
            },
            {
              num: "02",
              title: "SUPERVISE",
              desc: "The Operator Agent monitors every sub-agent in real-time. If one stalls or errors, it intervenes, retries, or reassigns.",
            },
            {
              num: "03",
              title: "SYNTHESIZE",
              desc: "Results from all agents converge. Jarvis compiles, verifies, and delivers a single coherent output — while you sleep.",
            },
          ].map((item, i) => (
            <div
              key={item.num}
              className={`os1-fade-up os1-fade-up-delay-${i + 1} p-6 rounded-xl`}
              style={{
                backgroundColor: "rgba(243,234,217,0.02)",
                border: "1px solid rgba(243,234,217,0.06)",
              }}
            >
              <span className="font-arcade" style={{ fontSize: "10px", color: "#c84b31" }}>{item.num}</span>
              <h3
                className="font-arcade mt-4 mb-3"
                style={{ fontSize: "11px", color: "#f3ead9", letterSpacing: "0.15em" }}
              >
                {item.title}
              </h3>
              <p style={{ fontFamily: "'Inter', sans-serif", fontSize: "14px", lineHeight: 1.7, color: "rgba(243,234,217,0.5)" }}>
                {item.desc}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
