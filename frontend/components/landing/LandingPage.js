'use client'
import { useRouter } from 'next/navigation'
import { Hero } from './Hero'

function PlaceholderSection({ label }) {
  return (
    <section
      style={{
        minHeight: '60vh',
        background: '#0a0a0a',
        color: 'rgba(243,234,217,0.3)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontFamily: 'system-ui, sans-serif',
        fontSize: 12,
        letterSpacing: '0.3em',
        textTransform: 'uppercase',
        borderTop: '1px solid rgba(243,234,217,0.04)',
      }}
    >
      [ {label} — coming in Phase 2 ]
    </section>
  )
}

export function LandingPage() {
  const router = useRouter()

  const handleBegin = () => {
    router.push('/welcome')
  }

  return (
    <main style={{ background: '#0a0a0a', minHeight: '100vh' }}>
      <Hero onBegin={handleBegin} />
      <PlaceholderSection label="Section 2: The Difference" />
      <PlaceholderSection label="Section 3: Voice First" />
      <PlaceholderSection label="Section 4: Connected" />
      <PlaceholderSection label="Section 5: Memory" />
      <PlaceholderSection label="Section 6: Final CTA" />
    </main>
  )
}
