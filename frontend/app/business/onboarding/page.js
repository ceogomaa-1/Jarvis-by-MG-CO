'use client'
import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { supabase } from '../../../lib/supabase'
import { completeBusinessOnboarding } from '../../../lib/userPreferences'
import OS1Cinematic from '../../../components/onboarding/OS1Cinematic'
import OS1Questions from '../../../components/onboarding/OS1Questions'
import TetrisLoader from '../../../components/ui/TetrisLoader'

export default function BusinessOnboardingPage() {
  const router = useRouter()
  const [phase, setPhase] = useState(null) // 'cinematic' | 'questions'
  const [session, setSession] = useState(null)

  useEffect(() => {
    if (!supabase) { setPhase('cinematic'); return }
    supabase.auth.getSession().then(({ data: { session } }) => {
      setSession(session)
      const params = new URLSearchParams(window.location.search)
      const resumeAtQuestions = params.get('step') === 'questions' && !!session?.user
      if (resumeAtQuestions) window.history.replaceState({}, '', '/business/onboarding')
      setPhase(resumeAtQuestions ? 'questions' : 'cinematic')
    }).catch(() => setPhase('cinematic'))
  }, [])

  const handleCinematicComplete = async () => {
    if (session?.user) {
      setPhase('questions')
      return
    }
    if (supabase) {
      await supabase.auth.signInWithOAuth({
        provider: 'google',
        options: { redirectTo: `${window.location.origin}/business/onboarding?step=questions` },
      })
    }
  }

  const handleQuestionsComplete = async (answers) => {
    if (session?.user) {
      const uid = 'user_' + session.user.id.replace(/-/g, '')
      await completeBusinessOnboarding({
        userId: uid,
        email: session.user.email,
        name: answers.name,
        industry: answers.industry,
        customIndustry: answers.industry === 'Other' ? answers.customIndustry : null,
        companyName: answers.companyName,
        mission: answers.mission,
      })
    }
    router.push('/business/chat')
  }

  if (!phase) {
    return (
      <div style={{ height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#131313' }}>
        <TetrisLoader size="md" speed="normal" showLoadingText={true} loadingText="Starting Jarvis..." />
      </div>
    )
  }

  if (phase === 'cinematic') {
    return <OS1Cinematic onComplete={handleCinematicComplete} />
  }

  return <OS1Questions onComplete={handleQuestionsComplete} />
}
