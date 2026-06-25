"use client"

import { useEffect, useState } from "react"
import { supabase } from "@/lib/supabase"
import { jarvisUserId, getOS1Status } from "@/lib/os1"
import { setJarvisMode } from "@/lib/userPreferences"

const ENTER_OS1 = "/business/chat"

async function enterOS1(userId: string) {
  // Keep jarvis_mode consistent so /business/chat loads (user may be coming from Personal).
  try {
    await setJarvisMode(userId, "business")
  } catch {}
  window.location.href = ENTER_OS1
}

// The full /os1 landing ALWAYS renders (children) — for logged-out visitors, logged-in users
// without a subscription, everyone. Gating happens only when ENTERING the OS1 app: a logged-in
// user with access is forwarded into /business/chat. We never hide the page and never bounce to
// login, so there is no redirect loop under any path.
export default function OS1Shell({ children }: { children: React.ReactNode }) {
  const [entering, setEntering] = useState(false)   // brief overlay while forwarding into OS1
  const [email, setEmail] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  async function login() {
    if (!supabase) return
    await supabase.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: `${window.location.origin}/auth/callback?next=${encodeURIComponent("/os1")}` },
    })
  }

  async function logout() {
    if (!supabase) return
    await supabase.auth.signOut()
    window.location.href = "/os1"
  }

  useEffect(() => {
    if (!supabase) return
    let cancelled = false

    const params = new URLSearchParams(window.location.search)
    const checkout = params.get("checkout")
    if (checkout === "cancel") {
      setNotice("Checkout canceled — pick a plan whenever you're ready.")
      window.history.replaceState({}, "", "/os1")
    }

    async function resolve() {
      let session = null
      try {
        const r = await supabase.auth.getSession()
        session = r.data.session
      } catch {
        // Auth lookup failed — just show the full site. Never block the page on this.
        return
      }
      if (cancelled) return
      if (!session?.user) {
        setEmail(null)
        return // logged out → full site stays visible
      }
      setEmail(session.user.email || null)
      const userId = jarvisUserId(session.user.id)

      // Returned from a successful checkout → wait for the webhook to flip access, then enter.
      if (checkout === "success") {
        setEntering(true)
        window.history.replaceState({}, "", "/os1")
        for (let i = 0; i < 8; i++) {
          const s = await getOS1Status(userId, session.user.email)
          if (cancelled) return
          if (s?.has_access) {
            await enterOS1(userId)
            return
          }
          await new Promise((r) => setTimeout(r, 1500))
        }
        // Still processing — drop the overlay and let them see the site/pricing.
        setEntering(false)
        setNotice("Your subscription is processing. If OS1 doesn't open shortly, refresh this page.")
        return
      }

      // Logged in: only entitled users (active OR grandfathered) are forwarded into OS1.
      // Everyone else simply stays on the full landing (pricing is in the page).
      const status = await getOS1Status(userId, session.user.email)
      if (cancelled) return
      if (status?.has_access) {
        setEntering(true)
        await enterOS1(userId)
      }
    }

    resolve()
    const { data: sub } = supabase.auth.onAuthStateChange(() => resolve())
    return () => {
      cancelled = true
      sub?.subscription?.unsubscribe()
    }
  }, [])

  return (
    <>
      <AuthBar email={email} onLogin={login} onLogout={logout} />
      {notice && <Notice text={notice} onClose={() => setNotice(null)} />}
      {entering && <Splash text="Entering Jarvis OS1…" />}
      {/* Full OS1 landing — always rendered. */}
      <div style={entering ? { display: "none" } : undefined}>{children}</div>
    </>
  )
}

function AuthBar({
  email,
  onLogin,
  onLogout,
}: {
  email: string | null
  onLogin: () => void
  onLogout: () => void
}) {
  return (
    <div
      style={{
        position: "fixed",
        top: 18,
        right: 20,
        zIndex: 60,
        display: "flex",
        alignItems: "center",
        gap: 10,
        fontFamily: "'Inter', sans-serif",
      }}
    >
      {email ? (
        <>
          <span style={{ fontSize: 12, color: "rgba(243,234,217,0.5)" }}>{email}</span>
          <button onClick={onLogout} style={btn(false)}>Sign out</button>
        </>
      ) : (
        <>
          <button onClick={onLogin} style={btn(false)}>Log in</button>
          <button onClick={onLogin} style={btn(true)}>Sign up</button>
        </>
      )}
    </div>
  )
}

function btn(primary: boolean): React.CSSProperties {
  return {
    fontSize: 13,
    letterSpacing: "0.02em",
    padding: "7px 16px",
    borderRadius: 8,
    cursor: "pointer",
    border: primary ? "none" : "1px solid rgba(243,234,217,0.18)",
    background: primary ? "#c84b31" : "transparent",
    color: primary ? "#0a0a0a" : "rgba(243,234,217,0.85)",
    fontWeight: primary ? 600 : 400,
    transition: "all 0.2s",
  }
}

function Splash({ text }: { text: string }) {
  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 50,
        background: "#0a0a0a",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 18,
      }}
    >
      <div
        style={{
          fontFamily: "'Instrument Serif', Georgia, serif",
          fontSize: "1.8rem",
          letterSpacing: "0.4em",
          paddingLeft: "0.4em",
          color: "#f3ead9",
        }}
      >
        JARVIS OS1
      </div>
      {text && (
        <div style={{ fontFamily: "'Inter', sans-serif", fontSize: 13, color: "rgba(243,234,217,0.5)" }}>
          {text}
        </div>
      )}
    </div>
  )
}

function Notice({ text, onClose }: { text: string; onClose: () => void }) {
  return (
    <div
      style={{
        position: "fixed",
        top: 64,
        left: "50%",
        transform: "translateX(-50%)",
        zIndex: 60,
        maxWidth: 520,
        padding: "12px 18px",
        borderRadius: 10,
        background: "rgba(200,75,49,0.1)",
        border: "1px solid rgba(200,75,49,0.3)",
        color: "#f3ead9",
        fontFamily: "'Inter', sans-serif",
        fontSize: 13,
        display: "flex",
        gap: 14,
        alignItems: "center",
      }}
    >
      <span>{text}</span>
      <button onClick={onClose} style={{ background: "none", border: "none", color: "rgba(243,234,217,0.6)", cursor: "pointer", fontSize: 16 }}>
        ×
      </button>
    </div>
  )
}
