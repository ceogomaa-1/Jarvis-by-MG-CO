import { Conversation } from '@11labs/client'

export class VoiceManager {
  constructor(onSpeakingStart, onSpeakingEnd, onTranscript, onError) {
    this.conversation = null
    this.onSpeakingStart = onSpeakingStart
    this.onSpeakingEnd = onSpeakingEnd
    this.onTranscript = onTranscript
    this.onError = onError
    this.isConnected = false
  }

  async connect(signedUrl, systemPrompt) {
    try {
      // Unlock audio context first
      const AudioContext = window.AudioContext || window.webkitAudioContext
      if (AudioContext) {
        const ctx = new AudioContext()
        await ctx.resume()
      }

      this.conversation = await Conversation.startSession({
        signedUrl: signedUrl,
        overrides: {
          agent: {
            prompt: {
              prompt: systemPrompt,
            },
          },
          tts: {
            voiceId: 'Sarah',
          },
        },
        onConnect: () => {
          this.isConnected = true
          console.log('ElevenLabs connected successfully')
        },
        onDisconnect: () => {
          this.isConnected = false
          console.log('ElevenLabs disconnected')
          this.onSpeakingEnd?.()
        },
        onError: (error) => {
          console.error('ElevenLabs error:', error)
          this.onError?.(error)
        },
        onModeChange: (modeInfo) => {
          console.log('Mode change:', JSON.stringify(modeInfo))
          const mode = modeInfo?.mode || modeInfo
          if (mode === 'speaking') {
            this.onSpeakingStart?.()
          } else {
            this.onSpeakingEnd?.()
          }
        },
        onMessage: (msg) => {
          console.log('ElevenLabs message:', JSON.stringify(msg))
          const source = msg?.source || msg?.role
          const message = msg?.message || msg?.text || msg?.content
          if (message && message.trim()) {
            if (source === 'ai' || source === 'assistant') {
              this.onTranscript?.('jarvis', message)
            } else if (source === 'user') {
              this.onTranscript?.('user', message)
            }
          }
        },
      })

      console.log('Session started:', this.conversation)

    } catch (err) {
      console.error('ElevenLabs connection error:', err)
      this.onError?.(err)
      throw err
    }
  }

  async disconnect() {
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
