export const metadata = {
  title: 'Jarvis for Business',
  description: 'AI-powered business tools by MG&CO Technologies',
}

export default function BusinessLayout({ children }) {
  return (
    <div style={{ minHeight: '100vh', background: '#0a0908', color: '#f3ead9' }}>
      {children}
    </div>
  )
}
