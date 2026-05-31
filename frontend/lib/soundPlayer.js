const SOUNDS = {
  transition: '/sounds/transition.wav',
  voiceActivate: '/sounds/voice-activate.wav',
  proactive: '/sounds/proactive.wav',
}

const _cache = {}

export function preloadSounds() {
  if (typeof window === 'undefined') return
  for (const [key, src] of Object.entries(SOUNDS)) {
    const audio = new Audio(src)
    audio.preload = 'auto'
    _cache[key] = audio
  }
}

export function playSound(key) {
  if (typeof window === 'undefined') return
  try {
    const cached = _cache[key]
    if (cached) {
      cached.currentTime = 0
      cached.play().catch(() => {})
    } else {
      const src = SOUNDS[key]
      if (!src) return
      const audio = new Audio(src)
      _cache[key] = audio
      audio.play().catch(() => {})
    }
  } catch {}
}
