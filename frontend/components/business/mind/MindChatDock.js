'use client'

import { useRef, useState, useCallback } from 'react'
import { PromptInputBox } from '@/components/ui/ai-prompt-box'

import { BACKEND } from '@/lib/backend'

// Docked bottom-center chat input for The Mind. Streams the same
// /business/chat/stream endpoint as ChatCanvas, but only surfaces
// memory_used/memory_born thought-trace events back to MindCanvas —
// no transcript is rendered here.
export default function MindChatDock({ userId, onMemoryUsed, onMemoryBorn }) {
  const [loading, setLoading] = useState(false)
  const [status, setStatus] = useState(null)
  const convIdRef = useRef(null)
  const historyRef = useRef([])
  const statusTimerRef = useRef(null)

  const flashStatus = useCallback((text, ms) => {
    setStatus(text)
    if (statusTimerRef.current) clearTimeout(statusTimerRef.current)
    if (ms) statusTimerRef.current = setTimeout(() => setStatus(null), ms)
  }, [])

  const handleSend = useCallback(async (message) => {
    if (!message.trim() || loading || !userId) return
    setLoading(true)
    flashStatus('Thinking...')

    const history = historyRef.current
    let acc = ''

    try {
      const res = await fetch(`${BACKEND}/api/business/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message,
          user_id: userId,
          conversation_history: history,
          conversation_id: convIdRef.current,
          attachments: [],
        }),
      })
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buf = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const lines = buf.split('\n')
        buf = lines.pop() ?? ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const raw = line.slice(6)
          if (raw === '[DONE]') break
          try {
            const chunk = JSON.parse(raw)
            if (typeof chunk === 'object' && chunk !== null) {
              if (chunk.type === 'conv_id' && chunk.value) {
                convIdRef.current = convIdRef.current || chunk.value
              } else if (chunk.type === 'memory_used' && chunk.ids) {
                onMemoryUsed?.(chunk.ids)
                flashStatus('Recalling memories...', 2000)
              } else if (chunk.type === 'memory_born' && chunk.memories) {
                onMemoryBorn?.(chunk.memories)
                flashStatus('New memory formed', 2500)
              }
              continue
            }
            if (typeof chunk === 'string') {
              acc += chunk
              setStatus(null)
            }
          } catch { /* ignore malformed chunks */ }
        }
      }
    } catch {
      flashStatus('Something went wrong', 3000)
    }

    if (acc) {
      historyRef.current = [
        ...history,
        { role: 'user', content: message },
        { role: 'assistant', content: acc },
      ].slice(-20)
    }
    setLoading(false)
  }, [userId, loading, onMemoryUsed, onMemoryBorn, flashStatus])

  return (
    <div style={{
      position: 'absolute', bottom: 16, left: '50%', transform: 'translateX(-50%)',
      width: 'min(600px, calc(100% - 48px))', zIndex: 30,
      display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8,
    }}>
      {status && (
        <div style={{
          fontFamily: 'var(--pixel)', fontSize: 9, letterSpacing: '0.2em',
          color: '#2d7ff9', textTransform: 'uppercase',
          textShadow: '0 0 8px rgba(45,127,249,0.6)',
        }}>
          {status}
        </div>
      )}
      <div style={{ width: '100%' }}>
        <PromptInputBox
          onSend={(message) => handleSend(message)}
          isLoading={loading}
          placeholder="Ask Jarvis about your Mind..."
          enableVoice={false}
          enableUpload={false}
          showViewToggle={false}
        />
      </div>
    </div>
  )
}
