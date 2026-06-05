"use client"

import { cn } from "@/lib/utils"
import { useState, useEffect } from "react"
import dynamic from "next/dynamic"

const UnicornScene = dynamic(() => import("unicornstudio-react"), {
  ssr: false,
  loading: () => (
    <div
      className="w-full h-full"
      style={{ backgroundColor: "#0a0a0a" }}
    />
  ),
})

export const useWindowSize = () => {
  const [windowSize, setWindowSize] = useState({ width: 0, height: 0 })

  useEffect(() => {
    const handleResize = () => {
      setWindowSize({ width: window.innerWidth, height: window.innerHeight })
    }
    handleResize()
    window.addEventListener("resize", handleResize)
    return () => window.removeEventListener("resize", handleResize)
  }, [])

  return windowSize
}

interface RaycastAnimatedBackgroundProps {
  className?: string
}

export const RaycastAnimatedBackground = ({ className }: RaycastAnimatedBackgroundProps) => {
  const { width, height } = useWindowSize()

  if (width === 0) {
    return (
      <div
        className={cn("w-full h-full", className)}
        style={{ backgroundColor: "#0a0a0a" }}
      />
    )
  }

  return (
    <div className={cn("flex flex-col items-center w-full h-full", className)}>
      <UnicornScene
        production={true}
        projectId="cbmTT38A0CcuYxeiyj5H"
        width={width}
        height={height}
      />
    </div>
  )
}
