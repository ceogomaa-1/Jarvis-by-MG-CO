'use client'
import { useRouter } from 'next/navigation'
import { Hero } from './Hero'
import { Section2Difference } from './Section2Difference'
import { Section3Voice } from './Section3Voice'
import { Section4Connected } from './Section4Connected'
import { Section5Memory } from './Section5Memory'
import { Section6CTA } from './Section6CTA'
import { Footer } from './Footer'

export function LandingPage() {
  const router = useRouter()

  const handleBegin = () => {
    router.push('/welcome')
  }

  return (
    <main style={{ background: '#0a0a0a', minHeight: '100vh' }}>
      <Hero onBegin={handleBegin} />
      <Section2Difference />
      <Section3Voice />
      <Section4Connected />
      <Section5Memory />
      <Section6CTA />
      <Footer />
    </main>
  )
}
