const PATTERNS = [
  /^show me how to\b/i,
  /^how do i\b/i,
  /^how can i\b/i,
  /^walk me through\b/i,
  /^teach me how to\b/i,
  /^can you show me how/i,
  /^can you walk me through/i,
  /\bhow to\b.{3,}/i,
]

export function detectShowMeHow(message) {
  return PATTERNS.some(p => p.test(message.trim()))
}
