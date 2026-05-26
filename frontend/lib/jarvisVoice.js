/**
 * JarvisVoice — Whisper STT + Fal CSM 1B TTS pipeline.
 * FAL_KEY never touches the frontend; all Fal calls go through /api/voice/synthesize.
 */

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL || ''

export class JarvisVoice {
  constructor({ userId, onTranscript, onSpeakingStart, onSpeakingEnd, onError, onRecordingStart, onRecordingStop }) {
    this.userId = userId
    this.onTranscript = onTranscript
    this.onSpeakingStart = onSpeakingStart
    this.onSpeakingEnd = onSpeakingEnd
    this.onError = onError
    this.onRecordingStart = onRecordingStart
    this.onRecordingStop = onRecordingStop

    this._mediaRecorder = null
    this._chunks = []
    this._recordStart = 0
    this._currentAudio = null
    this._vad = null
    this._handsFreeActive = false
  }

  // ── Hold-to-talk ────────────────────────────────────────────────────────────

  async startHoldToTalk() {
    if (this._mediaRecorder?.state === 'recording') return
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      this._chunks = []
      this._recordStart = Date.now()
      this._mediaRecorder = new MediaRecorder(stream, { mimeType: this._bestMime() })
      this._mediaRecorder.ondataavailable = (e) => { if (e.data.size > 0) this._chunks.push(e.data) }
      this._mediaRecorder.start()
      this.onRecordingStart?.()
    } catch (err) {
      console.error('JarvisVoice: mic access failed', err)
      this.onError?.('Microphone access denied. Check browser permissions.')
    }
  }

  async stopHoldToTalk(sendCb) {
    if (!this._mediaRecorder || this._mediaRecorder.state !== 'recording') return
    const elapsed = Date.now() - this._recordStart
    if (elapsed < 500) {
      // Too short — accidental tap, discard
      this._stopRecorder()
      return
    }
    const blob = await this._stopRecorderAndGetBlob()
    this.onRecordingStop?.()
    await this._transcribeAndSend(blob, sendCb)
  }

  cancelHoldToTalk() {
    this._stopRecorder()
    this.onRecordingStop?.()
  }

  // ── Hands-free (VAD) ────────────────────────────────────────────────────────

  async startHandsFree(sendCb) {
    this._handsFreeActive = true
    try {
      // Dynamic import — avoids SSR issues with the WASM dependency
      const { MicVAD } = await import('@ricky0123/vad-web')
      this._vad = await MicVAD.new({
        onSpeechStart: () => { if (this._handsFreeActive) this.onRecordingStart?.() },
        onSpeechEnd: async (audio) => {
          if (!this._handsFreeActive) return
          this.onRecordingStop?.()
          const blob = this._float32ToWav(audio, 16000)
          await this._transcribeAndSend(blob, sendCb)
        },
        onVADMisfire: () => {},
      })
      await this._vad.start()
    } catch (err) {
      console.error('JarvisVoice: VAD start failed', err)
      this.onError?.('Could not start hands-free mode.')
      this._handsFreeActive = false
    }
  }

  stopHandsFree() {
    this._handsFreeActive = false
    this._vad?.destroy()
    this._vad = null
    this.stopSpeaking()
  }

  // ── Transcription ───────────────────────────────────────────────────────────

  async _transcribeAndSend(blob, sendCb) {
    try {
      const form = new FormData()
      form.append('audio', blob, 'recording.' + this._ext(blob.type))
      form.append('user_id', this.userId)
      const res = await fetch(`${BACKEND}/api/voice/transcribe`, { method: 'POST', body: form })
      if (!res.ok) throw new Error(`Whisper returned ${res.status}`)
      const { text } = await res.json()
      if (text?.trim()) {
        this.onTranscript?.(text.trim())
        await sendCb?.(text.trim())
      }
    } catch (err) {
      console.error('JarvisVoice: transcribe error', err)
      this.onError?.('Could not transcribe. Try again.')
    }
  }

  // ── TTS playback ────────────────────────────────────────────────────────────

  async speak(text) {
    if (!text?.trim()) return
    this.stopSpeaking()
    try {
      const res = await fetch(`${BACKEND}/api/voice/synthesize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: text.slice(0, 1000), user_id: this.userId }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || `TTS ${res.status}`)
      }
      const { audio_url } = await res.json()
      if (!audio_url) throw new Error('No audio URL returned')
      this._currentAudio = new Audio(audio_url)
      this.onSpeakingStart?.()
      this._currentAudio.onended = () => { this._currentAudio = null; this.onSpeakingEnd?.() }
      this._currentAudio.onerror = () => { this._currentAudio = null; this.onSpeakingEnd?.() }
      await this._currentAudio.play()
    } catch (err) {
      console.error('JarvisVoice: TTS error', err)
      this.onSpeakingEnd?.()
      // Don't surface TTS errors to user — text response is already in chat
    }
  }

  stopSpeaking() {
    if (this._currentAudio) {
      this._currentAudio.pause()
      this._currentAudio.src = ''
      this._currentAudio = null
      this.onSpeakingEnd?.()
    }
  }

  // ── Cleanup ─────────────────────────────────────────────────────────────────

  destroy() {
    this.stopHandsFree()
    this.cancelHoldToTalk()
    this.stopSpeaking()
  }

  // ── Internals ───────────────────────────────────────────────────────────────

  _bestMime() {
    for (const m of ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4']) {
      if (MediaRecorder.isTypeSupported(m)) return m
    }
    return ''
  }

  _ext(mimeType) {
    if (mimeType.includes('ogg')) return 'ogg'
    if (mimeType.includes('mp4')) return 'mp4'
    return 'webm'
  }

  _stopRecorder() {
    if (this._mediaRecorder?.state === 'recording') this._mediaRecorder.stop()
    this._mediaRecorder?.stream?.getTracks().forEach(t => t.stop())
    this._mediaRecorder = null
    this._chunks = []
  }

  _stopRecorderAndGetBlob() {
    return new Promise(resolve => {
      const mr = this._mediaRecorder
      mr.onstop = () => {
        const blob = new Blob(this._chunks, { type: mr.mimeType || 'audio/webm' })
        this._chunks = []
        mr.stream?.getTracks().forEach(t => t.stop())
        this._mediaRecorder = null
        resolve(blob)
      }
      mr.stop()
    })
  }

  _float32ToWav(samples, sampleRate) {
    const buf = new ArrayBuffer(44 + samples.length * 2)
    const v = new DataView(buf)
    const w = (o, s) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)) }
    const n = samples.length
    w(0, 'RIFF'); v.setUint32(4, 36 + n * 2, true); w(8, 'WAVE')
    w(12, 'fmt '); v.setUint32(16, 16, true); v.setUint16(20, 1, true)
    v.setUint16(22, 1, true); v.setUint32(24, sampleRate, true)
    v.setUint32(28, sampleRate * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true)
    w(36, 'data'); v.setUint32(40, n * 2, true)
    const s16 = new Int16Array(buf, 44)
    for (let i = 0; i < n; i++) s16[i] = Math.max(-32768, Math.min(32767, samples[i] * 32767 | 0))
    return new Blob([buf], { type: 'audio/wav' })
  }
}
