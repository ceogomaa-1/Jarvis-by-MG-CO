import './globals.css'

export const metadata = {
  title: 'Jarvis by MG&CO',
  description: 'Your personal AI. Learning you every day.',
}

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body style={{ backgroundColor: '#0a0a0a', margin: 0, padding: 0, height: '100vh' }}>
        {children}
      </body>
    </html>
  )
}
