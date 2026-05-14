export class VoiceManager {
  constructor(onSpeakingStart, onSpeakingEnd, onTranscript) {
    this.pc = null
    this.dc = null
    this.audioEl = null
    this.isConnected = false
    this.onSpeakingStart = onSpeakingStart
    this.onSpeakingEnd = onSpeakingEnd
    this.onTranscript = onTranscript
    this._speaking = false
  }

  async connect(clientSecret) {
    this.pc = new RTCPeerConnection()

    // Audio output — Jarvis speaking
    this.audioEl = document.createElement('audio')
    this.audioEl.autoplay = true
    document.body.appendChild(this.audioEl)
    this.pc.ontrack = (e) => {
      this.audioEl.srcObject = e.streams[0]
    }

    // Microphone input
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    stream.getTracks().forEach(track => this.pc.addTrack(track, stream))

    // Data channel for control events
    this.dc = this.pc.createDataChannel('oai-events')
    this.dc.onmessage = (e) => {
      try { this._handleEvent(JSON.parse(e.data)) } catch {}
    }

    // SDP offer → OpenAI → SDP answer
    const offer = await this.pc.createOffer()
    await this.pc.setLocalDescription(offer)

    const response = await fetch(
      'https://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-12-17',
      {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${clientSecret}`,
          'Content-Type': 'application/sdp',
        },
        body: offer.sdp,
      }
    )

    if (!response.ok) {
      const txt = await response.text()
      throw new Error(`OpenAI WebRTC: ${response.status} ${txt}`)
    }

    const answerSdp = await response.text()
    await this.pc.setRemoteDescription({ type: 'answer', sdp: answerSdp })
    this.isConnected = true
  }

  _handleEvent(event) {
    switch (event.type) {
      case 'response.created':
        if (!this._speaking) {
          this._speaking = true
          this.onSpeakingStart?.()
        }
        break

      case 'response.done':
        if (this._speaking) {
          this._speaking = false
          this.onSpeakingEnd?.()
        }
        // Full Jarvis transcript via output items
        if (event.response?.output) {
          for (const item of event.response.output) {
            if (item.type === 'message' && item.role === 'assistant') {
              const text = item.content
                ?.filter(c => c.type === 'audio' && c.transcript)
                .map(c => c.transcript)
                .join(' ')
              if (text?.trim()) this.onTranscript?.('jarvis', text.trim())
            }
          }
        }
        break

      case 'response.audio_transcript.done':
        // Backup: if response.done didn't catch the transcript
        if (event.transcript?.trim()) {
          this.onTranscript?.('jarvis', event.transcript.trim())
        }
        break

      case 'conversation.item.input_audio_transcription.completed':
        if (event.transcript?.trim()) {
          this.onTranscript?.('user', event.transcript.trim())
        }
        break

      default:
        break
    }
  }

  disconnect() {
    // Release microphone
    if (this.pc) {
      this.pc.getSenders().forEach(s => s.track?.stop())
    }
    this.dc?.close()
    this.pc?.close()
    if (this.audioEl) {
      this.audioEl.srcObject = null
      this.audioEl.remove()
    }
    this.pc = null
    this.dc = null
    this.audioEl = null
    this.isConnected = false
    this._speaking = false
  }
}
