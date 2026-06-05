import OS1HeroHeader from "@/components/os1/OS1HeroHeader"

export const metadata = {
  title: "Jarvis OS1 — Autonomous Business Operator",
  description: "Your AI-powered fractional COO. Remembers. Anticipates. Acts.",
}

export default function OS1Page() {
  return (
    <main style={{ backgroundColor: "#0a0a0a", minHeight: "100vh" }}>
      <OS1HeroHeader />

      {/* Placeholder for Batch 34 sections */}
      <section
        style={{
          backgroundColor: "#0a0a0a",
          minHeight: "60vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <p
          style={{
            fontFamily: "'Press Start 2P', monospace",
            fontSize: "9px",
            color: "rgba(243,234,217,0.2)",
            letterSpacing: "0.3em",
          }}
        >
          MORE COMING SOON
        </p>
      </section>
    </main>
  )
}
