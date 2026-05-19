import { Conversation } from '@11labs/client'

export class VoiceManager {
  constructor(onSpeakingStart, onSpeakingEnd, onTranscript, onError, onMemoryUpdate, onFlushTranscript) {
    this.conversation = null
    this.onSpeakingStart = onSpeakingStart
    this.onSpeakingEnd = onSpeakingEnd
    this.onTranscript = onTranscript
    this.onError = onError
    this.onMemoryUpdate = onMemoryUpdate
    this.onFlushTranscript = onFlushTranscript
    this.isConnected = false
    this._didManualDisconnect = false
    this._reconnectTimeout = null
  }

  async connect(signedUrl, systemPrompt, userId) {
    this._didManualDisconnect = false
    console.log('VoiceManager.connect() called')
    console.log('signedUrl present:', !!signedUrl, signedUrl ? `length: ${signedUrl.length}` : '')
    console.log('systemPrompt length:', systemPrompt?.length ?? 0)
    try {
      // Unlock audio context first
      const AudioContext = window.AudioContext || window.webkitAudioContext
      if (AudioContext) {
        const ctx = new AudioContext()
        console.log('AudioContext state before resume:', ctx.state)
        await ctx.resume()
        console.log('AudioContext state after resume:', ctx.state)
      }

      console.log('Calling Conversation.startSession()...')
      this.conversation = await Conversation.startSession({
        signedUrl: signedUrl,
        overrides: {
          agent: {
            prompt: { prompt: systemPrompt },
          },
        },
        dynamicVariables: {
          user_id: userId,
        },
        onConnect: () => {
          this.isConnected = true
          console.log('ElevenLabs connected successfully')
        },
        onDisconnect: () => {
          this.isConnected = false
          console.log('ElevenLabs disconnected')
          this.onSpeakingEnd?.()
          this.onFlushTranscript?.()
          if (!this._didManualDisconnect) {
            this._reconnectTimeout = setTimeout(() => {
              console.log('Auto-reconnect: signaling parent...')
              this.onError?.('reconnecting')
            }, 2000)
          }
        },
        onError: (error) => {
          console.error('ElevenLabs error:', error)
          this.onError?.(error)
        },
        onModeChange: (modeInfo) => {
          const mode = modeInfo?.mode || modeInfo
          if (mode === 'speaking') {
            this.onSpeakingStart?.()
          } else {
            this.onSpeakingEnd?.()
          }
        },
        onMessage: (msg) => {
          console.log('RAW ElevenLabs message:', JSON.stringify(msg))
          const type = msg?.type

          // Format 1: transcript event
          if (type === 'transcript') {
            const role = msg?.role
            const text = msg?.transcript || msg?.message || msg?.text
            if (text?.trim()) {
              if (role === 'user') {
                this.onTranscript?.('user', text)
                this.onMemoryUpdate?.({ role: 'user', content: text })
              } else if (role === 'assistant' || role === 'agent') {
                this.onTranscript?.('jarvis', text)
                this.onMemoryUpdate?.({ role: 'assistant', content: text })
              }
            }
            return
          }

          // Format 2: agent_response event
          if (type === 'agent_response') {
            const text = msg?.agent_response || msg?.message || msg?.text
            if (text?.trim()) {
              this.onTranscript?.('jarvis', text)
              this.onMemoryUpdate?.({ role: 'assistant', content: text })
            }
            return
          }

          // Format 3: user_transcript event
          if (type === 'user_transcript') {
            const text = msg?.user_transcript || msg?.message || msg?.text
            if (text?.trim()) {
              this.onTranscript?.('user', text)
              this.onMemoryUpdate?.({ role: 'user', content: text })
            }
            return
          }

          // Format 4: legacy source-based format
          const source = msg?.source || msg?.role
          const message = msg?.message || msg?.text || msg?.content
          if (message?.trim()) {
            if (source === 'ai' || source === 'assistant') {
              this.onTranscript?.('jarvis', message)
              this.onMemoryUpdate?.({ role: 'assistant', content: message })
            } else if (source === 'user') {
              this.onTranscript?.('user', message)
              this.onMemoryUpdate?.({ role: 'user', content: message })
            }
          }
        },
      })
      console.log('Session started:', this.conversation)
    } catch (err) {
      console.error('ElevenLabs connection error:', err)
      console.error('Error type:', err?.constructor?.name)
      console.error('Error message:', err?.message)
      this.onError?.(err)
      throw err
    }
  }

  async disconnect() {
    this._didManualDisconnect = true
    clearTimeout(this._reconnectTimeout)
    if (this.conversation) {
      await this.conversation.endSession()
      this.conversation = null
    }
    this.isConnected = false
  }

  isMuted() {
    return this.conversation?.isMuted() ?? false
  }

  setMuted(muted) {
    this.conversation?.setMicMuted(muted)
  }
}
