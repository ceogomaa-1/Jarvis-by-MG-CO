// Defense-in-depth for LLM-generated SVG that gets rendered via
// dangerouslySetInnerHTML. The model is trusted-ish (it produces the walkthrough
// for the user's own session), but raw SVG can carry <script>, on*= handlers,
// javascript: URLs, or <foreignObject> HTML — so strip those before rendering.
// Legitimate SVG (shapes, paths, text, styles) passes through untouched.
export function sanitizeSvg(svg) {
  if (typeof svg !== 'string') return ''
  return svg
    .replace(/<script[\s\S]*?<\/script\s*>/gi, '')
    .replace(/<script\b[^>]*>/gi, '')
    .replace(/<foreignObject[\s\S]*?<\/foreignObject\s*>/gi, '')
    .replace(/\son[a-z]+\s*=\s*"[^"]*"/gi, '')
    .replace(/\son[a-z]+\s*=\s*'[^']*'/gi, '')
    .replace(/\son[a-z]+\s*=\s*[^\s>]+/gi, '')
    .replace(/(href|xlink:href)\s*=\s*"\s*javascript:[^"]*"/gi, '$1="#"')
    .replace(/(href|xlink:href)\s*=\s*'\s*javascript:[^']*'/gi, "$1='#'")
}
