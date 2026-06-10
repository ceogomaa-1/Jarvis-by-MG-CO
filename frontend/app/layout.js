import { Instrument_Serif, Inter, Press_Start_2P, Pixelify_Sans } from 'next/font/google'
import './globals.css'
import AgentationProvider from '../components/dev/AgentationProvider'

const instrumentSerif = Instrument_Serif({
  weight: ['400'],
  style: ['normal', 'italic'],
  subsets: ['latin'],
  variable: '--font-serif',
  display: 'swap',
})

const inter = Inter({
  weight: ['300', '400', '500', '600', '700'],
  subsets: ['latin'],
  variable: '--font-sans',
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

export const metadata = {
  title: 'Jarvis — Your Personal AI',
  description: 'The first AI that actually gets to know you. Built by MG&CO Technologies.',
  icons: {
    icon: [
      { url: '/favicon.ico', sizes: 'any' },
      { url: '/favicon.png', type: 'image/png' },
    ],
    apple: [{ url: '/apple-icon.png', sizes: '180x180', type: 'image/png' }],
  },
}

export default function RootLayout({ children }) {
  return (
    <html lang="en" className={`${instrumentSerif.variable} ${inter.variable} ${pressStart.variable} ${pixelify.variable}`}>
      <body style={{ backgroundColor: '#0a0908', margin: 0, padding: 0, height: '100vh' }}>
        {children}
        <AgentationProvider />
      </body>
    </html>
  )
}
