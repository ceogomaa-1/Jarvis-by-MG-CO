"use client"

import { useRouter } from "next/navigation"
import { useState } from "react"
import { submitContact } from "@/lib/os1"

const inputStyle = {
  fontFamily: "'Inter', sans-serif",
  fontSize: "15px",
  backgroundColor: "rgba(243,234,217,0.04)",
  border: "1px solid rgba(243,234,217,0.1)",
  color: "#f3ead9",
  width: "100%",
  padding: "12px 16px",
  borderRadius: "10px",
  outline: "none",
} as const

const labelStyle = {
  fontFamily: "'Inter', sans-serif",
  fontSize: "13px",
  color: "rgba(243,234,217,0.5)",
  display: "block",
  marginBottom: "6px",
} as const

export default function ContactPage() {
  const router = useRouter()
  const [name, setName] = useState("")
  const [email, setEmail] = useState("")
  const [company, setCompany] = useState("")
  const [phone, setPhone] = useState("")
  const [message, setMessage] = useState("")
  const [status, setStatus] = useState<"idle" | "sending" | "sent" | "error">("idle")

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim() || !email.trim()) return
    setStatus("sending")
    const res = await submitContact({
      name: name.trim(),
      email: email.trim(),
      company: company.trim(),
      phone: phone.trim(),
      message: message.trim(),
    })
    if (res?.ok) {
      setStatus("sent")
    } else {
      setStatus("error")
    }
  }

  return (
    <main style={{ backgroundColor: "#0a0a0a", minHeight: "100vh", color: "#f3ead9" }}>
      <div style={{ maxWidth: 720, margin: "0 auto", padding: "80px 24px 120px" }}>
        <button
          onClick={() => router.push("/os1")}
          style={{
            background: "none",
            border: "none",
            color: "rgba(243,234,217,0.5)",
            cursor: "pointer",
            fontFamily: "'Inter', sans-serif",
            fontSize: 13,
            marginBottom: 40,
          }}
        >
          ← Back to Rue OS1
        </button>

        <p
          className="font-arcade"
          style={{ fontSize: 9, letterSpacing: "0.4em", color: "rgba(243,234,217,0.35)", marginBottom: 18 }}
        >
          TALK TO SALES
        </p>
        <h1
          style={{
            fontFamily: "'Instrument Serif', Georgia, serif",
            fontSize: "clamp(36px, 5vw, 56px)",
            lineHeight: 1.1,
            marginBottom: 18,
          }}
        >
          Want Rue tailored<br />
          to <span style={{ color: "#c84b31" }}>your business?</span>
        </h1>
        <p
          style={{
            fontFamily: "'Inter', sans-serif",
            fontSize: 16,
            lineHeight: 1.7,
            color: "rgba(243,234,217,0.5)",
            marginBottom: 48,
            maxWidth: 520,
          }}
        >
          Tell us what you're building. We'll design a Rue deployment around your workflows,
          integrations, and team — and get back to you fast.
        </p>

        {status === "sent" ? (
          <div
            style={{
              padding: "56px 32px",
              borderRadius: 16,
              textAlign: "center",
              backgroundColor: "rgba(200,75,49,0.06)",
              border: "1px solid rgba(200,75,49,0.2)",
            }}
          >
            <p style={{ fontFamily: "'Instrument Serif', serif", fontSize: 30, marginBottom: 10 }}>
              Message sent.
            </p>
            <p className="font-arcade" style={{ fontSize: 8, letterSpacing: "0.2em", color: "rgba(243,234,217,0.4)" }}>
              WE&apos;LL BE IN TOUCH SHORTLY
            </p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 18 }}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
              <div>
                <label style={labelStyle}>Name *</label>
                <input style={inputStyle} required value={name} onChange={(e) => setName(e.target.value)} placeholder="Your name" />
              </div>
              <div>
                <label style={labelStyle}>Email *</label>
                <input style={inputStyle} required type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" />
              </div>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
              <div>
                <label style={labelStyle}>Company</label>
                <input style={inputStyle} value={company} onChange={(e) => setCompany(e.target.value)} placeholder="Company name" />
              </div>
              <div>
                <label style={labelStyle}>Phone</label>
                <input style={inputStyle} value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="Optional" />
              </div>
            </div>
            <div>
              <label style={labelStyle}>What do you need Rue to do?</label>
              <textarea
                style={{ ...inputStyle, resize: "none" } as React.CSSProperties}
                rows={5}
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder="Tell us about your business, team size, tools, and what you want to automate…"
              />
            </div>

            <button
              type="submit"
              disabled={status === "sending" || !name.trim() || !email.trim()}
              className="font-arcade"
              style={{
                marginTop: 8,
                padding: "16px",
                borderRadius: 12,
                fontSize: 11,
                letterSpacing: "0.12em",
                backgroundColor: status === "sending" ? "rgba(200,75,49,0.7)" : "#c84b31",
                color: "#0a0a0a",
                border: "none",
                cursor: status === "sending" ? "wait" : "pointer",
              }}
            >
              {status === "sending" ? "SENDING…" : "SEND MESSAGE →"}
            </button>

            {status === "error" && (
              <p style={{ fontFamily: "'Inter', sans-serif", fontSize: 13, color: "#f43f5e", textAlign: "center" }}>
                Something went wrong. Please try again or email us directly.
              </p>
            )}
          </form>
        )}

        {/* Company info */}
        <div
          style={{
            marginTop: 64,
            paddingTop: 40,
            borderTop: "1px solid rgba(243,234,217,0.08)",
            fontFamily: "'Inter', sans-serif",
          }}
        >
          <p style={{ fontSize: 15, color: "#f3ead9", marginBottom: 8, fontWeight: 600 }}>
            MG&CO Technologies Inc.
          </p>
          <p style={{ fontSize: 14, color: "rgba(243,234,217,0.55)", lineHeight: 1.8 }}>
            <a href="mailto:info@mgcotechnologies.com" style={{ color: "#c84b31", textDecoration: "none" }}>
              info@mgcotechnologies.com
            </a>
          </p>
        </div>
      </div>
    </main>
  )
}
