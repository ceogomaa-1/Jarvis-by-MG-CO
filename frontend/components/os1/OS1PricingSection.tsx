"use client"

import { useScrollReveal } from "@/hooks/useScrollReveal"
import { useState, useRef } from "react"

const inputStyle = {
  fontFamily: "'Inter', sans-serif",
  fontSize: "14px",
  backgroundColor: "rgba(243,234,217,0.04)",
  border: "1px solid rgba(243,234,217,0.1)",
  color: "#f3ead9",
} as const

const textareaStyle = {
  fontFamily: "'Inter', sans-serif",
  fontSize: "14px",
  backgroundColor: "rgba(243,234,217,0.04)",
  border: "1px solid rgba(243,234,217,0.08)",
  color: "#f3ead9",
} as const

const labelStyle = {
  fontFamily: "'Inter', sans-serif",
  fontSize: "13px",
  color: "rgba(243,234,217,0.5)",
  display: "block",
  marginBottom: "6px",
} as const

export default function OS1PricingSection() {
  const ref = useScrollReveal()
  const [firstName, setFirstName] = useState("")
  const [email, setEmail] = useState("")
  const [challenge, setChallenge] = useState("")
  const [triedBefore, setTriedBefore] = useState("")
  const [whyNow, setWhyNow] = useState("")
  const [status, setStatus] = useState<"idle" | "sending" | "sent" | "error">("idle")
  const formRef = useRef<HTMLFormElement>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!firstName.trim() || !email.trim()) return
    setStatus("sending")
    try {
      const res = await fetch("/api/waitlist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          firstName: firstName.trim(),
          email: email.trim(),
          challenge: challenge.trim(),
          triedBefore: triedBefore.trim(),
          whyNow: whyNow.trim(),
        }),
      })
      if (res.ok) {
        setStatus("sent")
        setFirstName("")
        setEmail("")
        setChallenge("")
        setTriedBefore("")
        setWhyNow("")
      } else {
        setStatus("error")
      }
    } catch {
      setStatus("error")
    }
  }

  return (
    <section
      ref={ref}
      className="relative py-32 px-6 overflow-hidden"
      style={{ backgroundColor: "#0a0a0a" }}
    >
      <div className="max-w-2xl mx-auto relative z-10">
        <p
          className="os1-fade-up font-arcade text-center mb-6"
          style={{ fontSize: "9px", letterSpacing: "0.4em", color: "rgba(243,234,217,0.35)" }}
        >
          EARLY ACCESS
        </p>

        <h2
          className="os1-fade-up os1-fade-up-delay-1 text-center mb-6"
          style={{
            fontFamily: "'Instrument Serif', serif",
            fontSize: "clamp(36px, 5vw, 64px)",
            color: "#f3ead9",
            lineHeight: 1.1,
            fontWeight: 400,
          }}
        >
          Get in before<br />
          <span style={{ color: "#c84b31" }}>everyone else.</span>
        </h2>

        <p
          className="os1-fade-up os1-fade-up-delay-2 text-center max-w-lg mx-auto mb-12"
          style={{ fontFamily: "'Inter', sans-serif", fontSize: "16px", lineHeight: 1.7, color: "rgba(243,234,217,0.5)" }}
        >
          Jarvis OS1 is rolling out to early adopters first. Drop your name and we'll reach out when it's your turn.
        </p>

        {status === "sent" ? (
          <div
            className="os1-fade-up text-center py-16 rounded-2xl"
            style={{ backgroundColor: "rgba(200,75,49,0.06)", border: "1px solid rgba(200,75,49,0.2)" }}
          >
            <p style={{ fontFamily: "'Instrument Serif', serif", fontSize: "32px", color: "#f3ead9", marginBottom: "8px" }}>
              You&apos;re on the list.
            </p>
            <p className="font-arcade" style={{ fontSize: "8px", color: "rgba(243,234,217,0.4)", letterSpacing: "0.2em" }}>
              WE&apos;LL BE IN TOUCH SOON
            </p>
          </div>
        ) : (
          <form ref={formRef} onSubmit={handleSubmit} className="os1-fade-up os1-fade-up-delay-2 space-y-4">
            {/* Name + Email */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="font-arcade" style={{ fontSize: "7px", letterSpacing: "0.15em", color: "rgba(243,234,217,0.4)", display: "block", marginBottom: "6px" }}>
                  FIRST NAME *
                </label>
                <input
                  type="text"
                  required
                  value={firstName}
                  onChange={(e) => setFirstName(e.target.value)}
                  placeholder="Your first name"
                  className="w-full px-4 py-3 rounded-lg outline-none"
                  style={inputStyle}
                  onFocus={(e) => (e.target.style.borderColor = "rgba(200,75,49,0.4)")}
                  onBlur={(e) => (e.target.style.borderColor = "rgba(243,234,217,0.1)")}
                />
              </div>
              <div>
                <label className="font-arcade" style={{ fontSize: "7px", letterSpacing: "0.15em", color: "rgba(243,234,217,0.4)", display: "block", marginBottom: "6px" }}>
                  EMAIL *
                </label>
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@company.com"
                  className="w-full px-4 py-3 rounded-lg outline-none"
                  style={inputStyle}
                  onFocus={(e) => (e.target.style.borderColor = "rgba(200,75,49,0.4)")}
                  onBlur={(e) => (e.target.style.borderColor = "rgba(243,234,217,0.1)")}
                />
              </div>
            </div>

            {/* Optional divider */}
            <div className="pt-6 pb-2">
              <p className="text-center" style={{ fontFamily: "'Inter', sans-serif", fontSize: "12px", fontStyle: "italic", color: "rgba(243,234,217,0.3)" }}>
                Not required, but helps both of us better
              </p>
            </div>

            <div>
              <label style={labelStyle}>What&apos;s the biggest challenge you&apos;re trying to solve right now?</label>
              <textarea
                value={challenge}
                onChange={(e) => setChallenge(e.target.value)}
                rows={2}
                placeholder="e.g. I'm drowning in admin work and can't focus on growth..."
                className="w-full px-4 py-3 rounded-lg outline-none resize-none"
                style={textareaStyle}
                onFocus={(e) => (e.target.style.borderColor = "rgba(200,75,49,0.3)")}
                onBlur={(e) => (e.target.style.borderColor = "rgba(243,234,217,0.08)")}
              />
            </div>

            <div>
              <label style={labelStyle}>What have you already tried?</label>
              <textarea
                value={triedBefore}
                onChange={(e) => setTriedBefore(e.target.value)}
                rows={2}
                placeholder="e.g. Hired a VA, used Zapier + ChatGPT, tried 5 different CRMs..."
                className="w-full px-4 py-3 rounded-lg outline-none resize-none"
                style={textareaStyle}
                onFocus={(e) => (e.target.style.borderColor = "rgba(200,75,49,0.3)")}
                onBlur={(e) => (e.target.style.borderColor = "rgba(243,234,217,0.08)")}
              />
            </div>

            <div>
              <label style={labelStyle}>Why is now the right time to address this?</label>
              <textarea
                value={whyNow}
                onChange={(e) => setWhyNow(e.target.value)}
                rows={2}
                placeholder="e.g. Scaling to 10 clients and the manual process is breaking..."
                className="w-full px-4 py-3 rounded-lg outline-none resize-none"
                style={textareaStyle}
                onFocus={(e) => (e.target.style.borderColor = "rgba(200,75,49,0.3)")}
                onBlur={(e) => (e.target.style.borderColor = "rgba(243,234,217,0.08)")}
              />
            </div>

            <div className="pt-4">
              <button
                type="submit"
                disabled={status === "sending" || !firstName.trim() || !email.trim()}
                className="font-arcade w-full py-4 rounded-xl"
                style={{
                  fontSize: "11px",
                  letterSpacing: "0.12em",
                  backgroundColor: status === "sending" ? "rgba(200,75,49,0.7)" : "#c84b31",
                  color: "#0a0a0a",
                  border: "none",
                  cursor: status === "sending" ? "wait" : "pointer",
                  transition: "background-color 0.2s",
                }}
              >
                {status === "sending" ? "SECURING YOUR SPOT..." : "RESERVE MY SEAT →"}
              </button>
            </div>

            {status === "error" && (
              <p className="text-center pt-2" style={{ fontFamily: "'Inter', sans-serif", fontSize: "13px", color: "#f43f5e" }}>
                Something went wrong. Please try again.
              </p>
            )}
          </form>
        )}
      </div>
    </section>
  )
}
