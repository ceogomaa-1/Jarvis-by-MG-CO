'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { supabase } from '../../lib/supabase'

export default function PersonalPage() {
  const router = useRouter()

  useEffect(() => {
    if (!supabase) {
      router.replace('/personal/login')
      return
    }
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session?.user) {
        router.replace('/')
      } else {
        router.replace('/personal/login')
      }
    }).catch(() => router.replace('/personal/login'))
  }, [router])

  return (
    <div style={{ background: '#0a0a0a', height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ fontFamily: 'Georgia, serif', fontSize: '1.6rem', letterSpacing: '0.5em', paddingLeft: '0.5em', color: '#f3ead9' }}>
        RUE
      </div>
    </div>
  )
}
