// Informational questions — checked first, these NEVER trigger walkthrough
const BLOCKLIST = [
  /^what (is|are|was|were|does|do|can|should|would|will|the)\b/i,
  /^which (is|are|was|were|should|would|one|type|kind|option)\b/i,
  /^why (is|are|does|do|would|should|did|can)\b/i,
  /^when (is|are|does|do|should|would|did|can|to)\b/i,
  /^where (is|are|can|should|do|would)\b/i,
  /^who (is|are|was|were|can|should)\b/i,
  /^tell me (about|what|why|when|the difference|more)\b/i,
  /^explain\b/i,
  /^(what|which).+(better|best|recommend|suggest|difference|vs|versus|prefer|choose|pick)\b/i,
  /^should (i|we|you)\b/i,
]

// Walkthrough triggers — "how to X" and explicit procedural requests
const TRIGGERS = [
  /\bhow to\b/i,
  /\bhow do i\b/i,
  /\bhow can i\b/i,
  /^show me how\b/i,
  /^walk me through\b/i,
  /^teach me how\b/i,
  /^can you (show|walk|teach) me\b/i,
  /\bstep[- ]by[- ]step\b/i,
  /\bsteps? (to|for)\b/i,
]

export function detectShowMeHow(message) {
  const trimmed = message.trim()
  if (BLOCKLIST.some(p => p.test(trimmed))) return false
  return TRIGGERS.some(p => p.test(trimmed))
}
