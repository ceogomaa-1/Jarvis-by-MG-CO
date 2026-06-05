"use client"

import { useEffect, useRef } from "react"

let sharedObserver: IntersectionObserver | null = null
const observedElements = new Set<Element>()

function getSharedObserver(): IntersectionObserver {
  if (!sharedObserver) {
    sharedObserver = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            const el = entry.target as HTMLElement
            const targets = el.querySelectorAll(".os1-fade-up")
            targets.forEach((target) => target.classList.add("os1-visible"))
            if (el.classList.contains("os1-fade-up")) {
              el.classList.add("os1-visible")
            }
            sharedObserver?.unobserve(el)
            observedElements.delete(el)
          }
        })
      },
      { threshold: 0.1, rootMargin: "0px 0px -40px 0px" }
    )
  }
  return sharedObserver
}

export function useScrollReveal() {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const observer = getSharedObserver()
    observer.observe(el)
    observedElements.add(el)
    return () => {
      observer.unobserve(el)
      observedElements.delete(el)
    }
  }, [])

  return ref
}
