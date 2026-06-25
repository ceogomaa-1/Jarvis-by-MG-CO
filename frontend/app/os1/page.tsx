import OS1HeroHeader from "@/components/os1/OS1HeroHeader"
import OS1OperatorSection from "@/components/os1/OS1OperatorSection"
import OS1OperatorNightSection from "@/components/os1/OS1OperatorNightSection"
import OS1MemorySection from "@/components/os1/OS1MemorySection"
import OS1ConnectorsSection from "@/components/os1/OS1ConnectorsSection"
import OS1SafetySection from "@/components/os1/OS1SafetySection"
import OS1Pricing from "@/components/os1/OS1Pricing"
import OS1CTASection from "@/components/os1/OS1CTASection"
import OS1Footer from "@/components/os1/OS1Footer"
import OS1Shell from "@/components/os1/OS1Shell"

export const metadata = {
  title: "Jarvis OS1 — Autonomous Business Operator",
  description: "Your AI-powered fractional COO. Spawns agents. Runs overnight. Remembers everything.",
}

export default function OS1Page() {
  // OS1Shell gates everything: existing/grandfathered/active users go straight into OS1,
  // authenticated-but-unsubscribed users see the pricing screen, and logged-out visitors
  // see the marketing page below (with pricing + Sign up / Login).
  return (
    <main style={{ backgroundColor: "#0a0a0a", minHeight: "100vh" }}>
      <OS1Shell>
        <OS1HeroHeader />
        <OS1OperatorSection />
        <OS1OperatorNightSection />
        <OS1MemorySection />
        <OS1ConnectorsSection />
        <OS1SafetySection />
        <OS1Pricing />
        <OS1CTASection />
        <OS1Footer />
      </OS1Shell>
    </main>
  )
}
