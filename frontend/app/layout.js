import { Instrument_Serif, Inter, Press_Start_2P, Pixelify_Sans, Fredoka, Fraunces, JetBrains_Mono, Hanken_Grotesk } from 'next/font/google'
import './globals.css'
import AgentationProvider from '../components/dev/AgentationProvider'
import AuthTokenBridge from '../components/auth/AuthTokenBridge'

const instrumentSerif = Instrument_Serif({
  weight: ['400'],
  style: ['normal', 'italic'],
  subsets: ['latin'],
  variable: '--font-serif',
  display: 'swap',
})

const inter = Inter({
  weight: ['300', '400', '500', '600', '700', '900'],
  subsets: ['latin'],
  variable: '--font-sans',
  display: 'swap',
})

// Welcome (Rue Personal) body fonts — Fraunces (serif display), JetBrains Mono (labels),
// Hanken Grotesk (sans). Scoped via CSS variables; used by components/landing/WelcomeBody.js.
const fraunces = Fraunces({
  weight: ['400', '500'],
  style: ['normal', 'italic'],
  subsets: ['latin'],
  variable: '--font-fraunces',
  display: 'swap',
})

const jetbrainsMono = JetBrains_Mono({
  weight: ['400', '500'],
  subsets: ['latin'],
  variable: '--font-jetbrains',
  display: 'swap',
})

const hankenGrotesk = Hanken_Grotesk({
  weight: ['400', '500', '600', '700'],
  subsets: ['latin'],
  variable: '--font-hanken',
  display: 'swap',
})

const pressStart = Press_Start_2P({
  weight: ['400'],
  subsets: ['latin'],
  variable: '--font-arcade',
  display: 'swap',
})

const pixelify = Pixelify_Sans({
  weight: ['400', '500', '600', '700'],
  subsets: ['latin'],
  variable: '--font-pixel',
  display: 'swap',
})

const fredoka = Fredoka({
  weight: ['400', '500', '600', '700'],
  subsets: ['latin'],
  variable: '--font-display-round',
  display: 'swap',
})

export const metadata = {
  title: 'Rue — Your Personal AI',
  description: 'The first AI that actually gets to know you. Built by MG&CO Technologies.',
  icons: {
    icon: [
      { url: '/favicon.ico', sizes: 'any' },
      { url: '/favicon.png', type: 'image/png' },
    ],
    apple: [{ url: '/apple-icon.png', sizes: '180x180', type: 'image/png' }],
  },
  appleWebApp: {
    capable: true,
    statusBarStyle: 'black-translucent',
    title: 'Rue',
  },
}

export const viewport = {
  themeColor: '#0a0908',
}

export default function RootLayout({ children }) {
  return (
    <html lang="en" className={`bg-background ${instrumentSerif.variable} ${inter.variable} ${pressStart.variable} ${pixelify.variable} ${fredoka.variable} ${fraunces.variable} ${jetbrainsMono.variable} ${hankenGrotesk.variable}`}>
      <body style={{ backgroundColor: '#0a0908', margin: 0, padding: 0, height: '100vh' }}>
        {children}
        <AuthTokenBridge />
        <AgentationProvider />
      </body>
    </html>
  )
}
