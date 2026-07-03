"use client"

interface UsageInfo {
  used: number
  limit: number
  remaining: number
  is_admin: boolean
  resets_in: string
}

interface UsageCounterProps {
  usage: UsageInfo | null
}

export default function UsageCounter({ usage }: UsageCounterProps) {
  if (!usage || usage.is_admin || usage.limit === -1) return null

  const percentage = (usage.used / usage.limit) * 100
  const isLow = usage.remaining <= 3
  const isOut = usage.remaining === 0

  return (
    <div
      className="flex items-center gap-2 px-3 py-1.5 rounded-lg"
      style={{
        backgroundColor: isOut ? "rgba(244,63,94,0.1)" : "rgba(236,230,217,0.04)",
        border: `1px solid ${isOut ? "rgba(244,63,94,0.2)" : isLow ? "rgba(207,138,91,0.2)" : "rgba(236,230,217,0.06)"}`,
      }}
    >
      <div
        className="relative overflow-hidden rounded-full"
        style={{ width: "40px", height: "4px", backgroundColor: "rgba(236,230,217,0.1)" }}
      >
        <div
          className="absolute left-0 top-0 h-full rounded-full transition-all duration-500"
          style={{
            width: `${Math.min(percentage, 100)}%`,
            backgroundColor: isOut ? "#f43f5e" : isLow ? "#cf8a5b" : "rgba(236,230,217,0.4)",
          }}
        />
      </div>
      <span
        className="font-pixel"
        style={{
          fontSize: "6px",
          letterSpacing: "0.1em",
          color: isOut ? "#f43f5e" : isLow ? "#cf8a5b" : "rgba(236,230,217,0.35)",
        }}
      >
        {isOut ? `NEXT SLOT IN ${usage.resets_in || "~90 MIN"}` : `${usage.remaining} LEFT`}
      </span>
    </div>
  )
}
