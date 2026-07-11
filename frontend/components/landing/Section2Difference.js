'use client'
import { useRouter } from 'next/navigation'
import { TextScramble } from '@/components/ui/text-scramble'

export function Section2Difference() {
  const router = useRouter()

  return (
    <section
      style={{
        position: 'relative',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '96px 24px',
        backgroundColor: '#0a0a0a',
      }}
    >
      {/* Subtle top separator */}
      <div style={{
        position: 'absolute',
        top: 0,
        left: '50%',
        transform: 'translateX(-50%)',
        width: 1,
        height: 64,
        background: 'linear-gradient(to bottom, rgba(243,234,217,0.15), transparent)',
      }} />

      <p style={{
        marginBottom: 32,
        textAlign: 'center',
        opacity: 0.4,
        fontFamily: "var(--font-arcade), 'Press Start 2P', monospace",
        fontSize: 9,
        letterSpacing: '0.4em',
        color: '#f3ead9',
      }}>
        HOVER TO DECODE
      </p>

      <TextScramble
        text="RUE OS1"
        className="text-center"
        onClick={() => router.push('/os1')}
      />

      <p style={{
        marginTop: 40,
        opacity: 0.2,
        textAlign: 'center',
        fontFamily: "var(--font-arcade), 'Press Start 2P', monospace",
        fontSize: 8,
        letterSpacing: '0.25em',
        color: '#f3ead9',
      }}>
        CLICK TO ENTER
      </p>

      {/* Subtle bottom separator */}
      <div style={{
        position: 'absolute',
        bottom: 0,
        left: '50%',
        transform: 'translateX(-50%)',
        width: 1,
        height: 64,
        background: 'linear-gradient(to top, rgba(243,234,217,0.15), transparent)',
      }} />
    </section>
  )
}
