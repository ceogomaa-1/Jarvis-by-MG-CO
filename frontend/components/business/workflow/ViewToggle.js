'use client'
import { useRouter, usePathname } from 'next/navigation'
import { MessageSquare, Workflow } from 'lucide-react'

export default function ViewToggle() {
  const router = useRouter()
  const pathname = usePathname()
  const isWorkflow = pathname === '/business/workflow'

  return (
    <button
      onClick={() => router.push(isWorkflow ? '/business/chat' : '/business/workflow')}
      title={isWorkflow ? 'Go to Chat' : 'Go to Workflow'}
      style={{
        position: 'fixed', top: 68, left: 20, zIndex: 50,
        width: 48, height: 48, borderRadius: '50%',
        background: 'rgba(15,15,18,0.65)',
        backdropFilter: 'blur(20px) saturate(180%)',
        WebkitBackdropFilter: 'blur(20px) saturate(180%)',
        border: '1px solid rgba(244,244,242,0.12)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        cursor: 'pointer', outline: 'none',
        animation: 'viewTogglePulse 2s ease-in-out infinite',
      }}
    >
      <style>{`
        @keyframes viewTogglePulse {
          0%,100% { box-shadow: 0 0 0 0 rgba(255,46,81,0.4); }
          50%      { box-shadow: 0 0 0 12px rgba(255,46,81,0); }
        }
      `}</style>
      {isWorkflow
        ? <MessageSquare size={18} color="#f4f4f2" />
        : <Workflow size={18} color="#f4f4f2" />
      }
    </button>
  )
}
