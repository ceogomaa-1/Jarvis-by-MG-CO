/**
 * JarvisVoice — VAD-gated Whisper STT + Cartesia Sonic TTS.
 * Single-tap to start/stop. No hold-to-talk.
 * All API calls go through our backend — no API keys in the browser.
 */

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL || ''

// ── AudioQueue — prevents AbortError from overlapping plays ──────────────────

class AudioQueue {
  constructor() {
    this._queue = []
    this._current = null
    this._playing = false
    this.onStart = null
    this.onEnd = null
  }

  add(objectUrl) {
    this._queue.push(objectUrl)
    if (!this._playing) this._playNext()
  }

  _playNext() {
    if (this._queue.length === 0) {
      this._playing = false
      this.onEnd?.()
      return
    }
    this._playing = true
    const url = this._queue.shift()
    if (this._queue.length === 0) this.onStart?.()  // fire once per batch
    const audio = new Audio(url)
    this._current = audio
    audio.play().catch((err) => {
      if (err.name !== 'AbortError') console.error('AudioQueue: play error', err)
      URL.revokeObjectURL(url)
      this._playNext()
    })
    audio.onended = () => {
      URL.revokeObjectURL(url)
      this._playNext()
    }
    audio.onerror = () => {
      URL.revokeObjectURL(url)
      this._playNext()
    }
  }

  stop() {
    this._queue.forEach(url => URL.revokeObjectURL(url))
    this._queue = []
    if (this._current) {
      this._current.pause()
      this._current.src = ''
      this._current = null
    }
    this._playing = false
  }
}

// ── JarvisVoice ───────────────────────────────────────────────────────────────

export class JarvisVoice {
  constructor({ userId, onSpeakingStart, onSpeakingEnd, onError }) {
    this.userId = userId
    this.onSpeakingStart = onSpeakingStart
    this.onSpeakingEnd = onSpeakingEnd
    this.onError = onError

    this._vad = null
    this._handsFreeActive = false
    this._audioQueue = new AudioQueue()
    this._audioQueue.onStart = () => this.onSpeakingStart?.()
    this._audioQueue.onEnd = () => this.onSpeakingEnd?.()
  }

  // ── Hands-free (VAD) ────────────────────────────────────────────────────────

  async startHandsFree(sendCb) {
    this._handsFreeActive = true
    try {
      const { MicVAD } = await import('@ricky0123/vad-web')
      this._vad = await MicVAD.new({
        // Point to public/-served files copied by scripts/copy-vad-assets.js
        modelURL: '/silero_vad_legacy.onnx',
        workletURL: '/vad.worklet.bundle.min.js',
        ortConfig: (ort) => { ort.env.wasm.wasmPaths = '/' },

        // Stricter thresholds — reduces false triggers and silence send
        positiveSpeechThreshold: 0.9,
        negativeSpeechThreshold: 0.75,
        minSpeechFrames: 8,        // ~250ms of confirmed speech before triggering
        preSpeechPadFrames: 4,

        onSpeechStart: () => {
          if (this._handsFreeActive) console.log('VAD: speech start')
        },
        onSpeechEnd: async (audio) => {
          if (!this._handsFreeActive) return
          const blob = this._float32ToWav(audio, 16000)
          await this._transcribeAndSend(blob, sendCb)
        },
        onVADMisfire: () => { console.log('VAD: misfire (too short)') },
      })
      await this._vad.start()
      console.log('VAD: started')
    } catch (err) {
      console.error('JarvisVoice: VAD start failed', err)
      this.onError?.('Could not start voice. Check mic permissions.')
      this._handsFreeActive = false
      throw err
    }
  }

  stopHandsFree() {
    this._handsFreeActive = false
    this._vad?.destroy()
    this._vad = null
    this._audioQueue.stop()
    this.onSpeakingEnd?.()
    console.log('VAD: stopped')
  }

  // ── Transcription ───────────────────────────────────────────────────────────

  async _transcribeAndSend(blob, sendCb) {
    try {
      const form = new FormData()
      form.append('audio', blob, 'recording.wav')
      form.append('user_id', this.userId || '')
      const res = await fetch(`${BACKEND}/api/voice/transcribe`, { method: 'POST', body: form })
      if (!res.ok) throw new Error(`STT ${res.status}`)
      const data = await res.json()
      if (data.skipped || !data.text?.trim()) return
      console.log('STT:', data.text)
      await sendCb?.(data.text.trim())
    } catch (err) {
      console.error('JarvisVoice: transcribe error', err)
    }
  }

  // ── TTS playback ─────────────────────────────────────────────────────────────
  // Backend returns raw MP3 bytes. We blob-URL them so Audio can play.

  async speak(text) {
    if (!text?.trim()) return
    try {
      const res = await fetch(`${BACKEND}/api/voice/synthesize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: text.slice(0, 1500), user_id: this.userId || '' }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || `TTS ${res.status}`)
      }
      const audioBlob = await res.blob()
      const objectUrl = URL.createObjectURL(audioBlob)
      this._audioQueue.add(objectUrl)
    } catch (err) {
      console.error('JarvisVoice: TTS error', err)
      // Don't surface — text is already in chat
    }
  }

  stopSpeaking() {
    this._audioQueue.stop()
    this.onSpeakingEnd?.()
  }

  // ── Cleanup ──────────────────────────────────────────────────────────────────

  destroy() {
    this.stopHandsFree()
    this.stopSpeaking()
  }

  // ── Internals ────────────────────────────────────────────────────────────────

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
