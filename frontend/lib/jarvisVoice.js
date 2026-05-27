/**
 * JarvisVoice — VAD-gated Whisper STT + Cartesia Sonic TTS.
 * Single-tap to start/stop. Full-duplex via browser echo cancellation.
 * Streaming PCM audio via Web Audio API — first sound in ~200ms.
 * All API calls go through our backend — no API keys in the browser.
 */

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL || ''

// ── StreamingAudioPlayer — Web Audio API PCM streaming ───────────────────────
// Receives raw PCM float32 LE at 22050 Hz from the backend and schedules
// chunks on a single AudioContext timeline so playback is gapless.

class StreamingAudioPlayer {
  constructor() {
    this._ctx = null
    this._nextPlayTime = 0
    this._carry = null        // leftover bytes that don't align to 4-byte float boundary
    this._queue = []          // pending {url, body} to stream
    this._active = false
    this._sources = []        // active AudioBufferSourceNodes (for stop())
    this.onStart = null       // fires when first audio chunk is scheduled
    this.onEnd = null         // fires when all queued audio finishes playing
    this._started = false
  }

  // ── AudioContext — created on user gesture to satisfy autoplay policy ────

  _ctx_create() {
    if (!this._ctx || this._ctx.state === 'closed') {
      this._ctx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 22050 })
      this._nextPlayTime = 0
      this._started = false
    }
    return this._ctx
  }

  async resume() {
    const ctx = this._ctx_create()
    if (ctx.state === 'suspended') await ctx.resume()
  }

  // ── Queue management ────────────────────────────────────────────────────

  enqueue(url, body) {
    this._queue.push({ url, body })
    if (!this._active) this._drain()
  }

  _drain() {
    this._active = true
    this._runDrain().catch(err => {
      console.error('StreamingAudioPlayer: drain error', err)
      this._active = false
      this.onEnd?.()
    })
  }

  async _runDrain() {
    while (this._queue.length > 0) {
      const { url, body } = this._queue.shift()
      await this._streamOne(url, body)
    }
    this._active = false
    // Schedule onEnd to fire after the last scheduled chunk finishes playing
    const ctx = this._ctx
    if (ctx && this._nextPlayTime > ctx.currentTime) {
      const delayMs = (this._nextPlayTime - ctx.currentTime) * 1000 + 150
      setTimeout(() => this.onEnd?.(), delayMs)
    } else {
      this.onEnd?.()
    }
  }

  // ── Core streaming ──────────────────────────────────────────────────────

  async _streamOne(url, body) {
    const ctx = this._ctx_create()
    if (ctx.state === 'suspended') await ctx.resume()
    this._carry = null

    let res
    try {
      res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
    } catch (err) {
      console.error('StreamingAudioPlayer: fetch error', err)
      return
    }
    if (!res.ok) {
      console.error('StreamingAudioPlayer: TTS stream', res.status)
      return
    }

    const reader = res.body.getReader()
    while (true) {
      let done, value
      try {
        ;({ done, value } = await reader.read())
      } catch {
        break
      }
      if (done) break
      this._scheduleBytes(value)
    }
  }

  _scheduleBytes(incoming) {
    // Merge with carry-over from previous chunk (PCM floats are 4 bytes each)
    let bytes = incoming
    if (this._carry && this._carry.byteLength > 0) {
      const merged = new Uint8Array(this._carry.byteLength + incoming.byteLength)
      merged.set(new Uint8Array(this._carry), 0)
      merged.set(incoming, this._carry.byteLength)
      bytes = merged
      this._carry = null
    }

    // Trim to float32 boundary
    const remainder = bytes.byteLength % 4
    if (remainder !== 0) {
      this._carry = bytes.slice(bytes.byteLength - remainder)
      bytes = bytes.slice(0, bytes.byteLength - remainder)
    }
    if (bytes.byteLength === 0) return

    const floats = new Float32Array(bytes.buffer, bytes.byteOffset, bytes.byteLength / 4)
    this._scheduleChunk(floats)
  }

  _scheduleChunk(floats) {
    const ctx = this._ctx
    if (!ctx) return

    const buf = ctx.createBuffer(1, floats.length, 22050)
    buf.copyToChannel(floats, 0)

    const src = ctx.createBufferSource()
    src.buffer = buf
    src.connect(ctx.destination)

    // Chain immediately after the previous chunk
    const playAt = Math.max(this._nextPlayTime, ctx.currentTime + 0.02)
    src.start(playAt)
    this._nextPlayTime = playAt + buf.duration
    this._sources.push(src)

    if (!this._started) {
      this._started = true
      this.onStart?.()
    }
  }

  // ── Interruption ────────────────────────────────────────────────────────

  stop() {
    this._queue = []
    this._carry = null
    this._active = false
    this._started = false
    for (const src of this._sources) {
      try { src.stop() } catch {}
    }
    this._sources = []
    if (this._ctx && this._ctx.state !== 'closed') {
      this._ctx.close().catch(() => {})
    }
    this._ctx = null
    this._nextPlayTime = 0
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
    this._lastSpeakStart = 0   // timestamp when Jarvis last started speaking

    this._audioPlayer = new StreamingAudioPlayer()
    this._audioPlayer.onStart = () => this.onSpeakingStart?.()
    this._audioPlayer.onEnd = () => this.onSpeakingEnd?.()
  }

  // ── AudioContext unlock (call during user gesture) ──────────────────────

  async resumeAudio() {
    await this._audioPlayer.resume()
  }

  // ── Hands-free (VAD) ────────────────────────────────────────────────────

  async startHandsFree(sendCb) {
    this._handsFreeActive = true
    try {
      // Get mic with echo cancellation — lets browser subtract Jarvis's
      // speaker output from the mic signal in real time (like Google Meet)
      const micStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          channelCount: 1,
        },
      })

      const { MicVAD } = await import('@ricky0123/vad-web')
      this._vad = await MicVAD.new({
        stream: micStream,

        modelURL: '/silero_vad_legacy.onnx',
        workletURL: '/vad.worklet.bundle.min.js',
        ortConfig: (ort) => { ort.env.wasm.wasmPaths = '/' },

        positiveSpeechThreshold: 0.9,
        negativeSpeechThreshold: 0.75,
        minSpeechFrames: 8,
        preSpeechPadFrames: 4,

        onSpeechStart: () => {
          if (!this._handsFreeActive) return
          // If Jarvis just started speaking, ignore VAD for 500ms — it might
          // be speaker bleed that the browser AEC hasn't cancelled yet
          if (Date.now() - this._lastSpeakStart < 500) {
            console.log('VAD: ignoring speech-start (Jarvis just started, possible echo)')
            return
          }
          // Real user speech detected — interrupt Jarvis
          console.log('VAD: user speaking, interrupting Jarvis')
          this._audioPlayer.stop()
          this.onSpeakingEnd?.()
        },

        onSpeechEnd: async (audio) => {
          if (!this._handsFreeActive) return
          const blob = this._float32ToWav(audio, 16000)
          await this._transcribeAndSend(blob, sendCb)
        },

        onVADMisfire: () => { console.log('VAD: misfire (too short)') },
      })

      await this._vad.start()
      console.log('VAD: started (full-duplex, echo cancellation on)')
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
    this._audioPlayer.stop()
    this.onSpeakingEnd?.()
    console.log('VAD: stopped')
  }

  // ── Transcription ───────────────────────────────────────────────────────

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

  // ── TTS playback — streaming PCM via Web Audio API ───────────────────────

  speak(text) {
    if (!text?.trim()) return
    this._lastSpeakStart = Date.now()
    this._audioPlayer.enqueue(
      `${BACKEND}/api/voice/synthesize-stream`,
      { text: text.slice(0, 1500), user_id: this.userId || '' }
    )
  }

  stopSpeaking() {
    this._audioPlayer.stop()
    this.onSpeakingEnd?.()
  }

  // ── Cleanup ──────────────────────────────────────────────────────────────

  destroy() {
    this.stopHandsFree()
    this.stopSpeaking()
  }

  // ── Internals ────────────────────────────────────────────────────────────

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
