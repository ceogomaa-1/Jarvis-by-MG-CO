// Tracks the "active build context" — the most recently created/edited
// ElevenLabs agent in this conversation — so it can be passed to the backend
// intent classifier (/api/business/classify-intent). That single call decides
// whether a message is an edit to this agent, a walkthrough, or a new build.

// Matches ElevenLabs agent IDs (e.g. agent_6601kv3jx6x3fh58hh145h5x3hgt)
const AGENT_ID_REGEX = /\bagent_[a-zA-Z0-9]{10,}\b/

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
