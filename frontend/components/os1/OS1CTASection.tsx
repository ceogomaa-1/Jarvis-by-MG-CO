"use client"

import { useScrollReveal } from "@/hooks/useScrollReveal"

export default function OS1CTASection() {
  const ref = useScrollReveal()

  return (
    <section
      ref={ref}
      className="relative py-40 px-6 overflow-hidden"
      style={{ backgroundColor: "#0a0a0a" }}
    >
      <div
        className="absolute top-0 left-1/2 -translate-x-1/2"
        style={{
          width: "400px",
          height: "1px",
          background: "linear-gradient(90deg, transparent, rgba(200,75,49,0.5), transparent)",
        }}
      />

      <div className="max-w-3xl mx-auto text-center relative z-10">
        <h2
          className="os1-fade-up mb-6"
          style={{
            fontFamily: "'Instrument Serif', serif",
            fontSize: "clamp(40px, 6vw, 80px)",
            color: "#f3ead9",
            lineHeight: 1.05,
            fontWeight: 400,
          }}
        >
          Your business<br />
          deserves a brain.
        </h2>

        <p
          className="os1-fade-up os1-fade-up-delay-1 mb-12"
          style={{ fontFamily: "'Inter', sans-serif", fontSize: "17px", lineHeight: 1.7, color: "rgba(243,234,217,0.5)" }}
        >
          Stop duct-taping 14 tools together. Stop paying for an assistant who needs an assistant. Jarvis OS1 remembers, anticipates, and acts — across everything you do.
        </p>

        <div className="os1-fade-up os1-fade-up-delay-2 flex flex-col sm:flex-row items-center justify-center gap-4">
          <a
            href="#pricing"
            className="font-arcade inline-flex items-center gap-2 px-8 py-4 rounded-xl"
            style={{
              fontSize: "10px",
              letterSpacing: "0.1em",
              backgroundColor: "#c84b31",
              color: "#0a0a0a",
              transition: "opacity 0.2s",
            }}
          >
            SEE PLANS →
          </a>
        </div>

        <p
          className="os1-fade-up os1-fade-up-delay-3 font-arcade mt-16"
          style={{ fontSize: "7px", letterSpacing: "0.3em", color: "rgba(243,234,217,0.15)" }}
        >
          JARVIS OS1 BY MG&CO TECHNOLOGIES INC.
        </p>
      </div>
    </section>
  )
}
