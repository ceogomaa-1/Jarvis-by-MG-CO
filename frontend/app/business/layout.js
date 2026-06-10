'use client'
import { AnimatePresence } from 'framer-motion'
import { usePathname } from 'next/navigation'
import ArcadeToggle from '../../components/business/workflow/ArcadeToggle'

export default function BusinessLayout({ children }) {
  const pathname = usePathname()
  return (
    <div style={{ minHeight: '100vh', background: '#131313', color: '#e8e8e8' }}>
      <ArcadeToggle />
      <AnimatePresence mode="wait">
        <div key={pathname}>
          {children}
        </div>
      </AnimatePresence>
    </div>
  )
}
