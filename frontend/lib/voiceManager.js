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
      this.conversation = await Conversation.startSession({
        signedUrl,

        overrides: {
          agent: {
            prompt: { prompt: systemPrompt },
            firstMessage: '',
          },
        },

        onConnect: () => {
          this.isConnected = true
        },

        onDisconnect: () => {
          this.isConnected = false
        },

        onError: (error) => {
          console.error('ElevenLabs error:', error)
          this.onError?.(error)
        },

        onModeChange: ({ mode }) => {
          if (mode === 'speaking') {
            this.onSpeakingStart?.()
          } else {
            this.onSpeakingEnd?.()
          }
        },

        onMessage: ({ message, source }) => {
          if (!message?.trim()) return
          if (source === 'ai') {
            this.onTranscript?.('jarvis', message)
          } else if (source === 'user') {
            this.onTranscript?.('user', message)
          }
        },
      })
    } catch (err) {
      console.error('Failed to connect to ElevenLabs:', err)
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
