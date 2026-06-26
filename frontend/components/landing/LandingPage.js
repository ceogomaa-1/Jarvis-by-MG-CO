'use client'
import { useRouter } from 'next/navigation'
import { Hero } from './Hero'
import { WelcomeBody } from './WelcomeBody'

// /welcome — painterly hero (unchanged) on top, redesigned Jarvis Personal body below.
export function LandingPage() {
  const router = useRouter()

  const handleBegin = () => {
    router.push('/welcome/start')
  }

  return (
    <main style={{ background: '#F1EEE6', minHeight: '100vh' }}>
      <Hero onBegin={handleBegin} />
      <WelcomeBody onBegin={handleBegin} />
    </main>
  )
}
