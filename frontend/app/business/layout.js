'use client'
import { AnimatePresence } from 'framer-motion'
import { usePathname } from 'next/navigation'
import ArcadeToggle from '../../components/business/workflow/ArcadeToggle'

export default function BusinessLayout({ children }) {
  const pathname = usePathname()
  // The chat page now owns its own Chat View | Canvas View pill inside the
  // input bar — the legacy top-center toggle is redundant there.
  const hideArcadeToggle = pathname === '/business/chat'
  return (
    <div style={{ minHeight: '100vh', background: '#0b0a09', color: '#ece6d9' }}>
      {!hideArcadeToggle && <ArcadeToggle />}
      <AnimatePresence mode="wait">
        <div key={pathname}>
          {children}
        </div>
      </AnimatePresence>
    </div>
  )
}
