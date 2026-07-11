import OS1HeroHeader from "@/components/os1/OS1HeroHeader"
import OS1OperatorSection from "@/components/os1/OS1OperatorSection"
import OS1OperatorNightSection from "@/components/os1/OS1OperatorNightSection"
import OS1MemorySection from "@/components/os1/OS1MemorySection"
import OS1ConnectorsSection from "@/components/os1/OS1ConnectorsSection"
import OS1SafetySection from "@/components/os1/OS1SafetySection"
import OS1HermesBody from "@/components/os1/OS1HermesBody"
import OS1Shell from "@/components/os1/OS1Shell"

export const metadata = {
  title: "Rue OS1 — Autonomous Business Operator",
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
        {/* New Hermes / ASCII body — intro, what-is + compare, why, REAL pricing engine, marquee, MG&CO signoff */}
        <OS1HermesBody />
      </OS1Shell>
    </main>
  )
}
