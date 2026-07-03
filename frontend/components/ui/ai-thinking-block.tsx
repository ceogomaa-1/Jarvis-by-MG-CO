"use client"

import { useEffect, useMemo, useRef } from "react"

import { Card } from "@/components/ui/card"
import { Loader } from "@/components/ui/loader"
import { cn } from "@/lib/utils"

type AIThinkingBlockProps = {
  label?: string
  status?: string | null
  activity?: string[]
  mode?: "build" | "edit" | "deploy"
  className?: string
}

const MODE_ACTIVITY = {
  build: [
    "Reading the brief and locking the target brand",
    "Mapping the page structure and conversion path",
    "Shaping the visual direction and typography",
    "Writing specific copy for each section",
    "Building responsive interactions and motion",
    "Checking accessibility and reduced-motion behavior",
    "Inspecting the output for client-brand leakage",
    "Validating the final artifact before it can ship",
  ],
  edit: [
    "Reading the requested change against the saved page",
    "Locating the smallest unique code region to patch",
    "Preserving every unrelated section and interaction",
    "Applying exact replacements to the existing HTML",
    "Rechecking responsive behavior and accessibility",
    "Scanning for accidental branding or prompt leakage",
    "Saving the revised preview and deployable file",
  ],
  deploy: [
    "Loading the latest saved and validated artifact",
    "Verifying the connected publishing workspace",
    "Preparing the production deployment payload",
    "Uploading the immutable website revision",
    "Waiting for Vercel build validation",
    "Resolving the production URL",
  ],
}
const EMPTY_ACTIVITY: string[] = []

function cleanProgress(value: string) {
  return value
    .replace(/\s*\(\d+s(?:\s+elapsed)?(?:,\s*[^)]*)?\)\s*$/i, "")
    .trim()
}

export default function AIThinkingBlock({
  label = "Building your website",
  status,
  activity = EMPTY_ACTIVITY,
  mode = "build",
  className,
}: AIThinkingBlockProps) {
  const contentRef = useRef<HTMLDivElement>(null)

  const lines = useMemo(() => {
    const candidates = [status || "", ...activity, ...MODE_ACTIVITY[mode]]
      .map(cleanProgress)
      .filter(Boolean)
    return candidates.filter((line, index) => candidates.indexOf(line) === index)
  }, [activity, mode, status])

  useEffect(() => {
    const content = contentRef.current
    if (!content) return
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return
    const interval = window.setInterval(() => {
      const maxScroll = Math.max(content.scrollHeight - content.clientHeight, 0)
      content.scrollTop = maxScroll ? (content.scrollTop + 0.6) % maxScroll : 0
    }, 24)
    return () => window.clearInterval(interval)
  }, [lines])

  return (
    <div className={cn("flex w-full max-w-2xl flex-col py-2", className)}>
      <div className="mb-3 flex items-center gap-2.5">
        <span className="flex h-7 w-7 items-center justify-center rounded-full border border-primary/20 bg-primary/10 shadow-[0_0_24px_rgba(207,138,91,0.14)]">
          <Loader size="sm" className="text-[#cf8a5b]" />
        </span>
        <p className="ai-thinking-shimmer bg-[length:220%_100%] bg-clip-text text-sm font-medium text-transparent">
          {label}
        </p>
        <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 motion-safe:animate-pulse" />
      </div>

      <Card className="relative h-[164px] overflow-hidden rounded-xl border-white/10 bg-[#12171f] p-0 shadow-[0_18px_55px_rgba(0,0,0,0.24)]">
        <div className="pointer-events-none absolute inset-x-0 top-0 z-10 h-16 bg-gradient-to-b from-[#12171f] via-[#12171f]/90 to-transparent" />
        <div className="pointer-events-none absolute inset-x-0 bottom-0 z-10 h-16 bg-gradient-to-t from-[#12171f] via-[#12171f]/90 to-transparent" />
        <div
          ref={contentRef}
          className="h-full overflow-hidden px-5 py-6"
          aria-live="polite"
          aria-label={status || label}
        >
          <div className="space-y-3 pb-8 pt-2">
            {lines.concat(lines.slice(0, 4)).map((line, index) => (
              <div
                key={`${line}-${index}`}
                className={cn(
                  "flex items-start gap-3 text-[12px] leading-relaxed",
                  index === 0 ? "text-white/90" : "text-white/42",
                )}
              >
                <span
                  className={cn(
                    "mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full",
                    index === 0 ? "bg-[#cf8a5b] shadow-[0_0_10px_rgba(207,138,91,0.7)]" : "bg-white/20",
                  )}
                />
                <span>{line}</span>
              </div>
            ))}
          </div>
        </div>
      </Card>

      <style jsx>{`
        .ai-thinking-shimmer {
          background-image: linear-gradient(
            110deg,
            rgba(236, 230, 217, 0.32) 25%,
            rgba(255, 255, 255, 0.96) 48%,
            rgba(207, 138, 91, 0.92) 56%,
            rgba(236, 230, 217, 0.32) 78%
          );
          animation: ai-thinking-shimmer 4.8s linear infinite;
        }

        @keyframes ai-thinking-shimmer {
          from {
            background-position: 200% 0;
          }
          to {
            background-position: -200% 0;
          }
        }

        @media (prefers-reduced-motion: reduce) {
          .ai-thinking-shimmer {
            animation: none;
            color: rgba(255, 255, 255, 0.82);
          }
        }
      `}</style>
    </div>
  )
}
