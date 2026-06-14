// Detects "edit the [ElevenLabs] agent we just built" requests, so they route
// to the regular chat/stream tool-calling flow (update_agent) instead of
// being misrouted to Show-Me-How or the Creation canvas.

// Phrases that signal "change something about an existing thing", not
// "build/explain something new".
const MODIFICATION_TRIGGERS = [
  /\b(adjust|change|update|tweak|edit|fix|shorten|lengthen|rewrite|reword|simplify|refine|polish)\b/i,
  /\bmak(e|ing) (it|that|this|the|him|her)\b/i,
  /\b(sound|talk|speak)s?\s+(more|less|like)\b/i,
  /\bremember to\b/i,
  /\b(greeting|first message|opening line|system prompt|the prompt|the voice|the tone|the persona|the script)\b/i,
]

// If the message is clearly about a NEW/separate agent, it's not an edit to
// the active one — let the creation/show-me-how detectors run normally.
const NEW_AGENT_OVERRIDE = /\b(new|another|second|additional|a different|separate)\s+(agent|assistant|receptionist|voice agent|number|location)\b/i

// Matches ElevenLabs agent IDs (e.g. agent_6601kv3jx6x3fh58hh145h5x3hgt)
const AGENT_ID_REGEX = /\bagent_[a-zA-Z0-9]{10,}\b/

export function isAgentModificationRequest(message) {
  const text = (message || '').trim()
  if (!text) return false
  if (NEW_AGENT_OVERRIDE.test(text)) return false
  return MODIFICATION_TRIGGERS.some(p => p.test(text))
}

// Returns the most recently created/edited ElevenLabs agent_id from the
// conversation — the "active build context" — or null if none yet.
export function findActiveAgentId(messages) {
  const recent = [...(messages || [])].reverse()
  for (const m of recent) {
    if (m.agent_id) return m.agent_id
    if (m.role === 'assistant' && typeof m.content === 'string') {
      const match = m.content.match(AGENT_ID_REGEX)
      if (match) return match[0]
    }
  }
  return null
}
