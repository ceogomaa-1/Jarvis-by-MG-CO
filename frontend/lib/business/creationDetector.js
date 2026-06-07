// Patterns that strongly indicate a Creation request
const CREATION_TRIGGERS = [
  /\b(build|generate|create|design|draft|produce|write|make|launch|put together)\b.{0,40}\b(campaign|landing page|landing-page|website|web\s*site|web\s*page|webpage|site|funnel|email sequence|drip|sms sequence|cold email|ad set|ads?|creative|copy|report|analysis|audit|deck|presentation|proposal|pitch|one[- ]?pager|brochure|menu|flyer|signage|poster|post|carousel|content calendar|brand|persona|playbook|sop|standard operating procedure)\b/i,
  /^\s*(build|generate|create|design|draft|produce|write|make)\s+(me\s+|us\s+)?(a|an|the|some)\s+/i,
  /\brun (a|an|the) (competitor|market|swot|customer|brand) (analysis|audit|scan|research)\b/i,
  /\bspin up\b/i,
  /\bship (me|us) (a|an|the)\b/i,
  /\bput together\b/i,
]

// Patterns that BLOCK creation routing
const CREATION_BLOCKLIST = [
  /^\s*(what|which|why|when|where|who|tell me|explain|should i|should we)\b/i,
  /\bhow do i\b/i,
  /\bhow to\b/i,
  /\bshow me how\b/i,
  /\bwalk me through\b/i,
  /\bstep[- ]by[- ]step\b/i,
]

export function detectCreation(message) {
  if (!message || !message.trim()) return false
  const text = message.trim()
  if (CREATION_BLOCKLIST.some(p => p.test(text))) return false
  return CREATION_TRIGGERS.some(p => p.test(text))
}
