import './globals.css'

export const metadata = {
  title: 'Jarvis — Your Personal AI',
  description: 'The first AI that actually gets to know you. Built by MG&CO Technologies.',
}

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body style={{ backgroundColor: '#0a0908', margin: 0, padding: 0, height: '100vh' }}>
        {children}
      </body>
    </html>
  )
}
