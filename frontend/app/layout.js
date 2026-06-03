import { Instrument_Serif, Inter } from 'next/font/google'
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

export const metadata = {
  title: 'Jarvis — Your Personal AI',
  description: 'The first AI that actually gets to know you. Built by MG&CO Technologies.',
}

export default function RootLayout({ children }) {
  return (
    <html lang="en" className={`${instrumentSerif.variable} ${inter.variable}`}>
      <body style={{ backgroundColor: '#0a0908', margin: 0, padding: 0, height: '100vh' }}>
        {children}
        <AgentationProvider />
      </body>
    </html>
  )
}
