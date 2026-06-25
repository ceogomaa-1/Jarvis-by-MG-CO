"use client"

import { useEffect, useRef, useState } from "react"
import { useRouter } from "next/navigation"
import { Pricing2, type PricingPlan } from "@/components/ui/pricing-cards"
import { supabase } from "@/lib/supabase"
import { jarvisUserId, getOS1Status, startCheckout } from "@/lib/os1"
import { setJarvisMode } from "@/lib/userPreferences"

const PLANS: PricingPlan[] = [
  {
    id: "pro",
    name: "Jarvis OS1 Pro",
    description: "Your AI operator, fully armed.",
    monthlyPrice: "$49",
    yearlyPrice: "$490",
    yearlyNote: "2 months free",
    priceSuffix: "/mo",
    action: "checkout",
    cta: "Start 7-day trial",
    features: [
      { text: "Jarvis chat — personality + voice" },
      { text: "Autonomous Jarvis sessions (capped)" },
      { text: "Baseline usage · rolling ~5h window" },
      { text: "Train & feed Jarvis your knowledge" },
      { text: "9 industry bibles baked in" },
      { text: "MCP Creation 1.0 — connect any app" },
      { text: "“Show Me How” walkthroughs" },
      { text: "Basic CRM (no white-label)" },
      { text: "Buffer social — up to 2 platforms" },
    ],
  },
  {
    id: "emperor",
    name: "Jarvis OS1 Emperor",
    description: "Maximum power. White-labeled. Unlimited.",
    monthlyPrice: "$199",
    yearlyPrice: "$1,990",
    yearlyNote: "2 months free",
    priceSuffix: "/mo",
    action: "checkout",
    cta: "Start 7-day trial",
    highlighted: true,
    prevName: "Pro",
    features: [
      { text: "5× usage capacity" },
      { text: "Unlimited Buffer social platforms" },
      { text: "Fully customizable, white-labeled CRM" },
      { text: "Jarvis Leads — rule-based scraping + metered lookups" },
      { text: "Fully customizable UI · moving-blocks view" },
      { text: "Brand customization" },
    ],
  },
  {
    id: "tailored",
    name: "Tailored",
    description: "Jarvis built around your business.",
    monthlyPrice: "Custom",
    yearlyPrice: "Custom",
    action: "contact",
    cta: "Talk to Sales",
    prevName: "Emperor",
    features: [
      { text: "Custom workflows & integrations" },
      { text: "Dedicated onboarding & support" },
      { text: "Volume & enterprise pricing" },
    ],
  },
]

export default function OS1Pricing() {
  const router = useRouter()
  const [busyId, setBusyId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const resumedRef = useRef(false)

  async function goCheckout(plan: PricingPlan, interval: "month" | "year") {
    setError(null)
    if (!supabase) return
    const { data: { session } } = await supabase.auth.getSession()
    if (!session?.user) {
      // Not logged in → remember intent, then sign up / log in (same Supabase as Personal).
      try {
        localStorage.setItem("os1_intent", JSON.stringify({ plan: plan.id, interval }))
      } catch {}
      await supabase.auth.signInWithOAuth({
        provider: "google",
        options: { redirectTo: `${window.location.origin}/auth/callback?next=${encodeURIComponent("/os1")}` },
      })
      return
    }
    setBusyId(plan.id)
    const userId = jarvisUserId(session.user.id)
    const email = session.user.email || ""
    // Already-entitled users shouldn't be charged — bounce them straight into OS1.
    const status = await getOS1Status(userId, email)
    if (status?.has_access) {
      try { await setJarvisMode(userId, "business") } catch {}
      window.location.href = "/business/chat"
      return
    }
    const res = await startCheckout({ userId, email, plan: plan.id, interval, trial: true })
    if (res?.ok && res.url) {
      window.location.href = res.url
    } else {
      setBusyId(null)
      setError(res?.error || "Could not start checkout. Please try again.")
    }
  }

  function onSelect(plan: PricingPlan, interval: "month" | "year") {
    if (plan.action === "contact") {
      router.push("/contact")
      return
    }
    goCheckout(plan, interval)
  }

  // Resume checkout after returning from Google login.
  useEffect(() => {
    if (resumedRef.current || !supabase) return
    let raw: string | null = null
    try {
      raw = localStorage.getItem("os1_intent")
    } catch {}
    if (!raw) return
    resumedRef.current = true
    try {
      localStorage.removeItem("os1_intent")
    } catch {}
    let intent: { plan: string; interval: "month" | "year" }
    try {
      intent = JSON.parse(raw)
    } catch {
      return
    }
    const plan = PLANS.find((p) => p.id === intent.plan)
    if (plan) {
      supabase.auth.getSession().then(({ data: { session } }) => {
        if (session?.user) goCheckout(plan, intent.interval)
      })
    }
  }, [])

  return (
    <div id="pricing">
      <Pricing2
        heading="Choose your Jarvis"
        description="One operator. Three altitudes. Cancel anytime — 7-day trial, card required."
        plans={PLANS}
        busyId={busyId}
        onSelect={onSelect}
      />
      <div className="bg-zinc-950 pb-20 text-center">
        {error && (
          <p className="mb-6 text-sm text-rose-400">{error}</p>
        )}
        <button
          onClick={() => router.push("/contact")}
          className="text-zinc-400 underline-offset-4 transition-colors hover:text-zinc-100 hover:underline"
          style={{ fontFamily: "'Inter', sans-serif", fontSize: 15 }}
        >
          Want Jarvis tailored to your business? →
        </button>
      </div>
    </div>
  )
}
