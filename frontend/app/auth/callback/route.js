import { createServerClient } from '@supabase/ssr'
import { cookies } from 'next/headers'
import { NextResponse } from 'next/server'

export async function GET(request) {
  const { searchParams, origin, hostname } = new URL(request.url)
  const code = searchParams.get('code')
  const rawNext = searchParams.get('next') ?? '/'
  // Guard against open redirect — next must be a relative path
  const next = rawNext.startsWith('/') ? rawNext : '/'

  // Match the browser client: write the auth cookie domain-wide in production so the session
  // exchanged here is valid across apex + www. Localhost / preview deploys stay host-only.
  const cookieDomain = hostname.endsWith('jarvismgco.com') ? '.jarvismgco.com' : undefined

  if (code) {
    const cookieStore = cookies()
    const supabase = createServerClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL,
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
      {
        cookies: {
          getAll() {
            return cookieStore.getAll()
          },
          setAll(cookiesToSet) {
            try {
              cookiesToSet.forEach(({ name, value, options }) =>
                cookieStore.set(name, value, cookieDomain ? { ...options, domain: cookieDomain } : options)
              )
            } catch {}
          },
        },
      }
    )

    const { error } = await supabase.auth.exchangeCodeForSession(code)
    if (!error) {
      const redirectUrl = new URL(`${origin}${next}`)
      for (const [key, value] of searchParams.entries()) {
        if (key !== 'code' && key !== 'next') {
          redirectUrl.searchParams.set(key, value)
        }
      }
      return NextResponse.redirect(redirectUrl.toString())
    }
    console.error('Auth callback error:', error)
  }

  // Exchange failed (or no code). Send the user back to the app they were entering —
  // OS1/business flows must NEVER dead-end on the Personal login page: that page
  // restarts OAuth with next=/?onboard=personal and manufactures the OS1 login loop.
  // /os1 always renders with its own login button, so it's a safe recovery surface.
  if (next.startsWith('/os1') || next.startsWith('/business')) {
    return NextResponse.redirect(`${origin}/os1?auth_error=1`)
  }
  return NextResponse.redirect(`${origin}/login?error=auth_failed`)
}
