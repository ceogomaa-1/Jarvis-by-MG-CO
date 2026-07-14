'use client'

import React, { useEffect, useRef, useState } from 'react'
import { ChevronRight } from 'lucide-react'

// ---------------------------------------------------------------------------
// Rue thinking loader — animated SVG path draw + shimmer text.
// Port of 21st.dev "animated-loading-svg-text-shimmer", with the squiggle
// replaced by a hand-traced Rue logo mark (the sphere + S-swirl), and colors
// mapped to the Rue warm palette (--ink cream / --accent coral glow).
// ---------------------------------------------------------------------------

// The Rue mark as one compound stroke: outer sphere, then the swirl that
// divides it — top lobe bows left, bottom lobe bows right, meeting at center.
const RUE_LOGO_PATH =
  'M12 3 A9 9 0 0 0 12 21 A9 9 0 0 0 12 3 ' +
  'M12 3 A4.5 4.5 0 0 0 12 12 A4.5 4.5 0 0 1 12 21'

let cachedPathLength = 0
let stylesInjected = false

const RUE_LOADER_KEYFRAMES = `
  @keyframes rueDrawStroke {
    0% {
      stroke-dashoffset: var(--rue-path-length);
      animation-timing-function: ease-in-out;
    }
    50% {
      stroke-dashoffset: 0;
      animation-timing-function: ease-in-out;
    }
    100% {
      stroke-dashoffset: calc(var(--rue-path-length) * -1);
    }
  }
  @keyframes rueTextShimmer {
    0% { background-position: -100% center; }
    100% { background-position: 100% center; }
  }
`

function injectKeyframes() {
  if (typeof window === 'undefined' || stylesInjected) return
  stylesInjected = true
  const style = document.createElement('style')
  style.innerHTML = RUE_LOADER_KEYFRAMES
  document.head.appendChild(style)
}

export const RueLoader = React.forwardRef(function RueLoader(
  { size = 20, strokeWidth = 1.7, style, ...props },
  ref,
) {
  const pathRef = useRef(null)
  const [pathLength, setPathLength] = useState(cachedPathLength)

  useEffect(() => {
    injectKeyframes()
    if (!cachedPathLength && pathRef.current) {
      cachedPathLength = pathRef.current.getTotalLength()
      setPathLength(cachedPathLength)
    }
  }, [])

  const isReady = pathLength > 0

  return (
    <svg
      ref={ref}
      role="status"
      aria-label="Rue is thinking"
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      style={{
        color: 'var(--ink, #f3ead9)',
        filter: 'drop-shadow(0 0 5px rgba(255,144,114,0.45))',
        flexShrink: 0,
        ...style,
      }}
      {...props}
    >
      <path
        ref={pathRef}
        d={RUE_LOGO_PATH}
        stroke="currentColor"
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        style={{
          opacity: isReady ? 1 : 0,
          transition: 'opacity 300ms ease',
          ...(isReady
            ? {
                strokeDasharray: pathLength,
                '--rue-path-length': pathLength,
                animation: 'rueDrawStroke 2.6s infinite',
              }
            : {}),
        }}
      />
    </svg>
  )
})

export function RueLoadingShimmer({ text = 'thinking', className, style }) {
  useEffect(() => {
    injectKeyframes()
  }, [])

  return (
    <div
      className={className}
      style={{ display: 'flex', alignItems: 'center', gap: 10, ...style }}
    >
      <RueLoader size={20} strokeWidth={1.7} />
      <span
        style={{
          fontFamily: 'var(--sans)',
          fontSize: 13,
          fontWeight: 500,
          letterSpacing: '0.05em',
          backgroundImage:
            'linear-gradient(90deg, rgba(243,234,217,0.38) 0%, rgba(243,234,217,0.38) 40%, #fff6e6 50%, rgba(243,234,217,0.38) 60%, rgba(243,234,217,0.38) 100%)',
          backgroundSize: '200% auto',
          WebkitBackgroundClip: 'text',
          backgroundClip: 'text',
          color: 'transparent',
          WebkitTextFillColor: 'transparent',
          animation: 'rueTextShimmer 2s ease-in-out infinite',
        }}
      >
        {text}
      </span>
      <ChevronRight
        size={14}
        strokeWidth={2}
        style={{ color: 'rgba(243,234,217,0.28)', flexShrink: 0 }}
      />
    </div>
  )
}
