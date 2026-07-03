'use client'
import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { supabase } from '../../../lib/supabase'
import { completeBusinessOnboarding, getBusinessUser } from '../../../lib/userPreferences'
import { useFontPref } from '../../../lib/fontPref'
import OS1Cinematic from '../../../components/onboarding/OS1Cinematic'
import OS1Questions from '../../../components/onboarding/OS1Questions'
import TetrisLoader from '../../../components/ui/TetrisLoader'

export default function BusinessOnboardingPage() {
  const router = useRouter()
  const [phase, setPhase] = useState(null) // 'cinematic' | 'questions'
  const [session, setSession] = useState(null)
  const [pendingAnswers, setPendingAnswers] = useState(null)
  const [onboardError, setOnboardError] = useState(false)

  useFontPref(session?.user?.id ? 'user_' + session.user.id.replace(/-/g, '') : null)

  useEffect(() => {
    if (!supabase) { setPhase('cinematic'); return }
    supabase.auth.getSession().then(async ({ data: { session } }) => {
      setSession(session)
      const params = new URLSearchParams(window.location.search)
      const resumeAtQuestions = params.get('step') === 'questions' && !!session?.user
      if (resumeAtQuestions) window.history.replaceState({}, '', '/business/onboarding')

      // Reverse guard: a user who already has a business profile should never
      // see onboarding again — bounce straight to chat so nobody re-onboards
      // by accident.
      if (session?.user) {
        const uid = 'user_' + session.user.id.replace(/-/g, '')
        const businessUser = await getBusinessUser(uid)
        if (businessUser.exists === true) {
          router.replace('/business/chat')
          return
        }
      }

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

  const attemptComplete = async (answers) => {
    if (!session?.user) {
      router.push('/business/chat')
      return
    }
    setOnboardError(false)
    const uid = 'user_' + session.user.id.replace(/-/g, '')
    const result = await completeBusinessOnboarding({
      userId: uid,
      email: session.user.email,
      name: answers.name,
      industry: answers.industry,
      customIndustry: answers.industry === 'Other' ? answers.customIndustry : null,
      companyName: answers.companyName,
      mission: answers.mission,
    })
    if (result.ok) {
      // Loop breaker: chat page's onboarding guard checks this first and skips
      // its redirect-to-onboarding while a fresh profile may not have
      // propagated to its read yet.
      sessionStorage.setItem('jarvis_onboarded', '1')
      router.push('/business/chat')
    } else {
      setOnboardError(true)
    }
  }

  const handleQuestionsComplete = async (answers) => {
    setPendingAnswers(answers)
    await attemptComplete(answers)
  }

  if (!phase) {
    return (
      <div style={{ height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#0b0a09' }}>
        <TetrisLoader size="md" speed="normal" showLoadingText={true} loadingText="Starting Jarvis..." />
      </div>
    )
  }

  if (phase === 'cinematic') {
    return <OS1Cinematic onComplete={handleCinematicComplete} />
  }

  return (
    <>
      <OS1Questions onComplete={handleQuestionsComplete} />
      {onboardError && (
        <div style={{
          position: 'fixed', inset: 0, zIndex: 200, background: 'rgba(19,19,19,0.92)',
          display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
          gap: 24, padding: 24, textAlign: 'center',
        }}>
          <p className="font-pixel" style={{ color: '#ece6d9', fontSize: 15, maxWidth: 420, lineHeight: 1.6 }}>
            Couldn&apos;t fire up your workspace. Your answers are safe — let&apos;s try again.
          </p>
          <button
            onClick={() => attemptComplete(pendingAnswers)}
            className="font-pixel"
            style={{
              background: 'var(--os1-blue)', border: 'none', borderRadius: 999,
              padding: '10px 28px', color: '#fff', cursor: 'pointer', fontSize: 14,
            }}
          >
            Retry →
          </button>
        </div>
      )}
    </>
  )
}
