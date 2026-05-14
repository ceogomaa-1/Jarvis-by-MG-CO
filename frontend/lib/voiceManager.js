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
    console.log('Connecting to ElevenLabs with URL:', signedUrl.slice(0, 50))

    // Unlock browser autoplay before connecting
    const AudioContext = window.AudioContext || window.webkitAudioContext
    const audioCtx = new AudioContext()
    if (audioCtx.state === 'suspended') {
      await audioCtx.resume()
    }
    const buffer = audioCtx.createBuffer(1, 1, 22050)
    const source = audioCtx.createBufferSource()
    source.buffer = buffer
    source.connect(audioCtx.destination)
    source.start()

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

        onModeChange: (modeEvent) => {
          console.log('ElevenLabs mode:', JSON.stringify(modeEvent))
          const mode = modeEvent?.mode ?? modeEvent
          if (mode === 'speaking') {
            this.onSpeakingStart?.()
          } else {
            this.onSpeakingEnd?.()
          }
        },

        onMessage: (msg) => {
          console.log('ElevenLabs message:', JSON.stringify(msg))
          const message = msg?.message
          const source = msg?.source
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
