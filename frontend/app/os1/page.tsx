import OS1HeroHeader from "@/components/os1/OS1HeroHeader"
import OS1OperatorSection from "@/components/os1/OS1OperatorSection"
import OS1OperatorNightSection from "@/components/os1/OS1OperatorNightSection"
import OS1MemorySection from "@/components/os1/OS1MemorySection"
import OS1ConnectorsSection from "@/components/os1/OS1ConnectorsSection"
import OS1SafetySection from "@/components/os1/OS1SafetySection"
import OS1PricingSection from "@/components/os1/OS1PricingSection"
import OS1CTASection from "@/components/os1/OS1CTASection"

export const metadata = {
  title: "Jarvis OS1 — Autonomous Business Operator",
  description: "Your AI-powered fractional COO. Remembers. Anticipates. Acts.",
}

export default function OS1Page() {
  return (
    <main style={{ backgroundColor: "#0a0a0a", minHeight: "100vh" }}>
      <OS1HeroHeader />
      <OS1OperatorSection />
      <OS1OperatorNightSection />
      <OS1MemorySection />
      <OS1ConnectorsSection />
      <OS1SafetySection />
      <OS1PricingSection />
      <OS1CTASection />
    </main>
  )
}
