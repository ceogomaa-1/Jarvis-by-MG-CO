"use client"

import Image from "next/image"
import { RaycastAnimatedBackground } from "@/components/ui/raycast-animated-background"

export default function OS1HeroHeader() {
  return (
    <section
      className="relative w-full overflow-hidden"
      style={{ height: "100dvh", minHeight: "600px" }}
    >
      {/* Animated background — pinned full bleed */}
      <div className="absolute inset-0 z-0">
        <RaycastAnimatedBackground className="w-full h-full" />
      </div>

      {/* Dark overlay for text readability */}
      <div
        className="absolute inset-0 z-10"
        style={{
          background:
            "linear-gradient(to bottom, rgba(10,10,10,0.35) 0%, rgba(10,10,10,0.15) 50%, rgba(10,10,10,0.65) 100%)",
        }}
      />

      {/* Logo + Title, centered */}
      <div
        className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-6"
        style={{ pointerEvents: "none" }}
      >
        <div
          className="relative"
          style={{
            width: "72px",
            height: "72px",
            filter: "drop-shadow(0 0 24px rgba(200,75,49,0.5))",
          }}
        >
          <Image
            src="/jarvis-logo-mono.png"
            alt="Jarvis OS1 Logo"
            fill
            style={{ objectFit: "contain" }}
            priority
          />
        </div>

        <h1
          style={{
            fontFamily: "'Press Start 2P', monospace",
            fontSize: "clamp(20px, 4vw, 48px)",
            color: "#f3ead9",
            letterSpacing: "0.08em",
            lineHeight: 1.3,
            textAlign: "center",
            textShadow: "0 0 40px rgba(200,75,49,0.4), 0 2px 8px rgba(0,0,0,0.8)",
            margin: 0,
          }}
        >
          JARVIS OS1
        </h1>

        <p
          style={{
            fontFamily: "'Press Start 2P', monospace",
            fontSize: "clamp(7px, 1vw, 10px)",
            color: "rgba(243,234,217,0.45)",
            letterSpacing: "0.3em",
            textAlign: "center",
            margin: 0,
          }}
        >
          AUTONOMOUS BUSINESS OPERATOR
        </p>
      </div>

      {/* Scroll indicator */}
      <div
        className="absolute bottom-8 left-1/2 z-20 flex flex-col items-center gap-2"
        style={{ transform: "translateX(-50%)" }}
      >
        <p
          style={{
            fontFamily: "'Press Start 2P', monospace",
            fontSize: "7px",
            color: "rgba(243,234,217,0.3)",
            letterSpacing: "0.35em",
          }}
        >
          SCROLL
        </p>
        <div
          className="w-px"
          style={{
            height: "40px",
            background: "linear-gradient(to bottom, rgba(243,234,217,0.3), transparent)",
            animation: "scrollPulse 2s ease-in-out infinite",
          }}
        />
      </div>
    </section>
  )
}
