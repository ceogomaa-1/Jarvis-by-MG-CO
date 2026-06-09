// Patterns that strongly indicate a Creation request (checked against first line for long messages)
const CREATION_TRIGGERS = [
  /\b(build|generate|create|design|draft|produce|write|make|launch|put together)\b.{0,40}\b(campaign|landing page|landing-page|website|web\s*site|web\s*page|webpage|site|funnel|email sequence|drip|sms sequence|cold email|ad set|ads?|creative|copy|report|analysis|audit|deck|presentation|proposal|pitch|one[- ]?pager|brochure|menu|flyer|signage|poster|post|carousel|content calendar|brand|persona|playbook|sop|standard operating procedure)\b/i,
  /^\s*(build|generate|create|design|draft|produce|write|make)\s+(me\s+|us\s+)?(a|an|the|some)\s+/i,
  /\brun (a|an|the) (competitor|market|swot|customer|brand) (analysis|audit|scan|research)\b/i,
  /\bspin up\b/i,
  /\bship (me|us) (a|an|the)\b/i,
  /\bput together\b/i,
]

// Patterns that BLOCK creation routing — matched at start of message
const CREATION_BLOCKLIST_START = [
  /^\s*(what|which|why|when|where|who|tell me|explain|should i|should we)\b/i,
  /\bhow do i\b/i,
  /\bhow to\b/i,
  /\bshow me how\b/i,
  /\bwalk me through\b/i,
  /\bstep[- ]by[- ]step\b/i,
]

// Patterns that BLOCK creation routing — matched anywhere in the message.
// These catch memory/ingest intents where the user is sharing reference material,
// not asking Jarvis to create something new.
const INGEST_BLOCKLIST = [
  /\b(remember|memorize|save (this|it)|keep (this|it)|store (this|it)|take note)\b/i,
  /\b(for your (memory|reference|records|knowledge))\b/i,
  /\b(bury (this|it)|file (this|it)|log (this|it))\b/i,
  /\bhere'?s (the|our|my) (bible|info|knowledge|details|company|background|context)\b/i,
  /\b(knowledge base|master (document|guide|playbook)|table of contents)\b/i,
  /\b(fyi[,:]|note this|learn this|just (sharing|sending|passing (along|this|on)))\b/i,
]

// Signatures of pasted reference documents — indicate long pastes, not creation commands
const PASTE_SIGNATURES = [
  /^#+ /m,       // markdown H1–H6 at line start
  /\|[-:]+\|/,   // markdown table separator row
  /^---\s*$/m,   // markdown horizontal rule on its own line
]

function _firstLine(text) {
  return text.split('\n')[0].slice(0, 120)
}

export function detectCreation(message) {
  if (!message || !message.trim()) return false
  const text = message.trim()

  // 1. Ingest/memory blocklist — overrides everything; matched anywhere in the message
  if (INGEST_BLOCKLIST.some(p => p.test(text))) return false

  // 2. Question-style blocklist — matched from start
  if (CREATION_BLOCKLIST_START.some(p => p.test(text))) return false

  // 3. Long message / paste guard:
  //    If the message is long (>600 chars or >6 line-breaks) it is likely pasted reference
  //    material. Only treat it as a creation request when an explicit trigger verb appears
  //    on the very first line (user intent is front-loaded in real commands).
  const lineCount = (text.match(/\n/g) || []).length
  if (text.length > 600 || lineCount > 6) {
    const firstLine = _firstLine(text)
    if (!CREATION_TRIGGERS.some(p => p.test(firstLine))) return false
    // Even with a first-line trigger, block if it looks like a pasted reference doc
    if (PASTE_SIGNATURES.some(p => p.test(text))) return false
    return true
  }

  // 4. Standard short-message check: trigger anywhere in the text
  return CREATION_TRIGGERS.some(p => p.test(text))
}
