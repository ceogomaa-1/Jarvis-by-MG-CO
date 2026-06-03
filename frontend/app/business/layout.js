'use client'
import { AnimatePresence } from 'framer-motion'
import { usePathname } from 'next/navigation'

export default function BusinessLayout({ children }) {
  const pathname = usePathname()
  return (
    <div style={{ minHeight: '100vh', background: '#0a0908', color: '#f3ead9' }}>
      <AnimatePresence mode="wait">
        <div key={pathname}>
          {children}
        </div>
      </AnimatePresence>
    </div>
  )
}
