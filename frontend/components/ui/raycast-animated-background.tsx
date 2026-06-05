"use client"

import { cn } from "@/lib/utils"
import { useState, useEffect, useRef } from "react"
import dynamic from "next/dynamic"

const UnicornScene = dynamic(() => import("unicornstudio-react"), {
  ssr: false,
  loading: () => null,
})

interface RaycastAnimatedBackgroundProps {
  className?: string
}

export const RaycastAnimatedBackground = ({ className }: RaycastAnimatedBackgroundProps) => {
  const [shouldLoad, setShouldLoad] = useState(false)
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 })
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setShouldLoad(true)
          observer.disconnect()
        }
      },
      { threshold: 0.01 }
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    const updateSize = () => setDimensions({ width: window.innerWidth, height: window.innerHeight })
    updateSize()
    window.addEventListener("resize", updateSize)
    return () => window.removeEventListener("resize", updateSize)
  }, [])

  return (
    <div ref={containerRef} className={cn("w-full h-full", className)}>
      {shouldLoad && dimensions.width > 0 ? (
        <UnicornScene
          production={true}
          projectId="cbmTT38A0CcuYxeiyj5H"
          width={dimensions.width}
          height={dimensions.height}
        />
      ) : (
        <div
          className="w-full h-full"
          style={{
            background: "radial-gradient(ellipse at center, rgba(200,75,49,0.08) 0%, #0a0a0a 70%)",
          }}
        />
      )}
    </div>
  )
}
