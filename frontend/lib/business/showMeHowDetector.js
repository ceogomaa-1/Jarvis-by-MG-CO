// Explicit procedural/how-to requests → trigger walkthrough
const WALKTHROUGH_PATTERNS = [
  /^show me how to\b/i,
  /^walk me through\b/i,
  /^how do i\b/i,
  /^how can i\b/i,
  /^teach me how to\b/i,
  /^can you show me how to\b/i,
  /^can you walk me through\b/i,
  /\bstep[- ]by[- ]step\b/i,
  /^(give me the |show me the |what are the )?steps (to|for)\b/i,
  /^(guide me|help me) (through|with how to)\b/i,
]

// Informational questions → do NOT trigger walkthrough, route to chat
const INFORMATIONAL_PATTERNS = [
  /^what (is|are|was|were|does|do|can|should|would|will|the)\b/i,
  /^which (is|are|was|were|should|would|one|type|kind|option)\b/i,
  /^why (is|are|does|do|would|should|did|can)\b/i,
  /^when (is|are|does|do|should|would|did|can|to)\b/i,
  /^where (is|are|can|should|do|would)\b/i,
  /^who (is|are|was|were|can|should)\b/i,
  /^tell me (about|what|why|when|how much|the difference|more)\b/i,
  /^explain\b/i,
  /^(what|which).+(better|best|recommend|suggest|difference|vs|versus|prefer|choose|pick)\b/i,
  /^(should|would|could|can|will|do|does|is|are|was|were|have|has|did)\b/i,
]

export function detectShowMeHow(message) {
  const trimmed = message.trim()

  // Block informational questions first
  if (INFORMATIONAL_PATTERNS.some(p => p.test(trimmed))) return false

  // Then check for clear procedural triggers
  return WALKTHROUGH_PATTERNS.some(p => p.test(trimmed))
}
