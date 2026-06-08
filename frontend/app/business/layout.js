'use client'
import { AnimatePresence } from 'framer-motion'
import { usePathname } from 'next/navigation'
import ArcadeToggle from '../../components/business/workflow/ArcadeToggle'

export default function BusinessLayout({ children }) {
  const pathname = usePathname()
  const isChat = pathname === '/business/chat'
  return (
    <div style={{ minHeight: '100vh', background: isChat ? '#242424' : '#0a0908', color: '#f3ead9' }}>
      {!isChat && <ArcadeToggle />}
      <AnimatePresence mode="wait">
        <div key={pathname}>
          {children}
        </div>
      </AnimatePresence>
    </div>
  )
}
