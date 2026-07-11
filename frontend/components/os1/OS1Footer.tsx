"use client"

import Image from "next/image"

export default function OS1Footer() {
  return (
    <footer
      className="relative px-6 overflow-hidden"
      style={{ backgroundColor: "#0a0a0a" }}
    >
      <div
        className="w-full h-px"
        style={{ background: "linear-gradient(90deg, transparent, rgba(243,234,217,0.08), transparent)" }}
      />

      <div className="max-w-7xl mx-auto py-24 flex flex-col items-center gap-10">
        {/* Logo + wordmark */}
        <div className="flex items-center gap-4">
          <div className="relative" style={{ width: "40px", height: "40px" }}>
            <Image
              src="/jarvis-logo-mono.png"
              alt="Rue OS1"
              fill
              style={{ objectFit: "contain", opacity: 0.7 }}
            />
          </div>
          <span
            className="font-arcade"
            style={{ fontSize: "14px", color: "rgba(243,234,217,0.6)", letterSpacing: "0.08em" }}
          >
            RUE OS1
          </span>
        </div>

        {/* Giant MG&CO */}
        <div
          className="w-full text-center select-none"
          style={{
            fontFamily: "'Inter', 'Helvetica Neue', sans-serif",
            fontSize: "clamp(60px, 14vw, 200px)",
            fontWeight: 900,
            color: "#f3ead9",
            lineHeight: 0.9,
            letterSpacing: "-0.04em",
            opacity: 0.9,
          }}
        >
          MG&amp;CO
          <sup
            style={{
              fontSize: "clamp(14px, 3vw, 36px)",
              fontWeight: 400,
              verticalAlign: "super",
              letterSpacing: "0",
              opacity: 0.6,
            }}
          >
            ™
          </sup>
        </div>

        {/* Subtitle */}
        <p
          style={{
            fontFamily: "'Inter', sans-serif",
            fontSize: "clamp(11px, 1.5vw, 15px)",
            color: "rgba(243,234,217,0.3)",
            letterSpacing: "0.3em",
            textTransform: "uppercase",
            textAlign: "center",
          }}
        >
          Technologies Inc.
        </p>

        {/* Bottom row */}
        <div className="pt-8 flex flex-col sm:flex-row items-center gap-4">
          <a
            href="https://mgcotechnologies.com"
            target="_blank"
            rel="noopener noreferrer"
            style={{ fontFamily: "'Inter', sans-serif", fontSize: "12px", color: "rgba(243,234,217,0.25)", textDecoration: "none" }}
          >
            mgcotechnologies.com
          </a>
          <span style={{ color: "rgba(243,234,217,0.1)" }}>·</span>
          <p style={{ fontFamily: "'Inter', sans-serif", fontSize: "12px", color: "rgba(243,234,217,0.25)" }}>
            Based in Toronto, Canada
          </p>
          <span style={{ color: "rgba(243,234,217,0.1)" }}>·</span>
          <p style={{ fontFamily: "'Inter', sans-serif", fontSize: "12px", color: "rgba(243,234,217,0.25)" }}>
            © {new Date().getFullYear()} MG&amp;CO Technologies Inc.
          </p>
        </div>
      </div>
    </footer>
  )
}
