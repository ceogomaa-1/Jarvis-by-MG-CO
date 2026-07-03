// Pure canvas drawing + hit-testing helpers for MindCanvas. Kept separate so
// the render loop body stays readable.
import { colorForCategory, GOLD, QUEUE_BLUE } from './colors'
import { getCanvasFontStack } from '../../../lib/fontPref'

export const SPAWN_DURATION = 700
export const REMOVE_DURATION = 450
export const LIGHT_DURATION = 1500

export function hashSeed(id) {
  let h = 0
  const s = String(id)
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0
  return (h % 1000) / 1000 * Math.PI * 2
}

export function pointToSegmentDist(px, py, x1, y1, x2, y2) {
  const dx = x2 - x1
  const dy = y2 - y1
  const lenSq = dx * dx + dy * dy
  let t = lenSq ? ((px - x1) * dx + (py - y1) * dy) / lenSq : 0
  t = Math.max(0, Math.min(1, t))
  const cx = x1 + t * dx
  const cy = y1 + t * dy
  return Math.hypot(px - cx, py - cy)
}

function arcGeometry(a, b) {
  const mx = (a.x + b.x) / 2
  const my = (a.y + b.y) / 2
  const dx = b.x - a.x
  const dy = b.y - a.y
  const len = Math.hypot(dx, dy) || 1
  const nx = -dy / len
  const ny = dx / len
  return { mx, my, nx, ny, len }
}

export function drawEdge(ctx, link, w2s, dimmed) {
  const a = w2s(link.source.x, link.source.y)
  const b = w2s(link.target.x, link.target.y)
  const { mx, my, nx, ny, len } = arcGeometry(a, b)
  const bow = Math.min(20, len * 0.08)
  const cx = mx + nx * bow
  const cy = my + ny * bow

  ctx.save()
  ctx.globalAlpha = (dimmed ? 0.04 : 1) * Math.max(0.06, Math.min(0.5, link.weight ?? 0.3))
  ctx.strokeStyle = '#ece6d9'
  ctx.lineWidth = 1
  ctx.beginPath()
  ctx.moveTo(a.x, a.y)
  ctx.quadraticCurveTo(cx, cy, b.x, b.y)
  ctx.stroke()
  ctx.restore()
}

export function drawSynapseArc(ctx, arc, w2s, t, opts = {}) {
  const a = w2s(arc.a.x, arc.a.y)
  const b = w2s(arc.b.x, arc.b.y)
  const { mx, my, nx, ny, len } = arcGeometry(a, b)
  const bow = Math.min(60, len * 0.18)
  const cx = mx + nx * bow
  const cy = my + ny * bow

  ctx.save()
  ctx.strokeStyle = GOLD
  ctx.lineWidth = opts.focused ? 2.5 : 1.5
  ctx.globalAlpha = opts.dimmed ? 0.08 : 0.6
  ctx.shadowBlur = opts.focused ? 16 : 8
  ctx.shadowColor = GOLD
  ctx.setLineDash([6, 5])
  ctx.lineDashOffset = -t * 18
  ctx.beginPath()
  ctx.moveTo(a.x, a.y)
  ctx.quadraticCurveTo(cx, cy, b.x, b.y)
  ctx.stroke()
  ctx.restore()
}

export function drawNode(ctx, node, w2s, zoom, t, opts = {}) {
  const seed = hashSeed(node.id)
  const driftX = Math.sin(t * 0.4 + seed) * 3
  const driftY = Math.cos(t * 0.33 + seed * 1.3) * 3

  const now = performance.now()
  let scale = 1
  let alpha = opts.dimmed ? 0.15 : 1

  if (node.spawnedAt) {
    const elapsed = now - node.spawnedAt
    if (elapsed < SPAWN_DURATION) {
      const p = elapsed / SPAWN_DURATION
      scale = p
      ctx.save()
    } else {
      node.spawnedAt = null
    }
  }
  if (node.removingAt) {
    const elapsed = now - node.removingAt
    const p = Math.min(1, elapsed / REMOVE_DURATION)
    scale = 1 + p * 1.6
    alpha *= Math.max(0, 1 - p)
  }

  const { x, y } = w2s(node.x + driftX, node.y + driftY)
  const baseSize = (4 + (node.strength || 0) * 16) * zoom * scale
  const color = colorForCategory(node.mind_category)

  let glow = 6 + (node.strength || 0) * 14
  if (node.mind_category === 'risk') {
    glow += Math.sin(t * 3 + seed) * 6
  }
  if (node.litUntil && now < node.litUntil) {
    const remain = (node.litUntil - now) / LIGHT_DURATION
    glow += 16 * remain
    alpha = Math.min(1, alpha + 0.4 * remain)
  }
  if (opts.hovered || opts.focused) glow += 8

  ctx.save()
  ctx.globalAlpha = Math.max(0, alpha)
  ctx.shadowBlur = Math.max(0, glow) * zoom
  ctx.shadowColor = color
  ctx.fillStyle = color
  ctx.fillRect(x - baseSize / 2, y - baseSize / 2, baseSize, baseSize)
  if (opts.focused) {
    ctx.lineWidth = 1.5
    ctx.strokeStyle = '#ffffff'
    ctx.globalAlpha = Math.max(0, alpha) * 0.8
    ctx.strokeRect(x - baseSize / 2 - 4, y - baseSize / 2 - 4, baseSize + 8, baseSize + 8)
  }
  ctx.restore()
}

export function drawGapNode(ctx, gap, w2s, zoom, t, opts = {}) {
  const { x, y } = w2s(gap.x, gap.y)
  const size = 14 * zoom
  const color = colorForCategory(gap.mind_category)
  const pulse = 0.35 + Math.sin(t * 2 + hashSeed(gap.id)) * 0.2

  ctx.save()
  ctx.globalAlpha = (opts.dimmed ? 0.06 : 1) * Math.max(0.1, pulse)
  ctx.strokeStyle = color
  ctx.lineWidth = opts.focused || opts.hovered ? 2 : 1
  ctx.setLineDash([4, 3])
  ctx.strokeRect(x - size / 2, y - size / 2, size, size)
  ctx.restore()
}

export function drawQueueNode(ctx, q, w2s, zoom, t, opts = {}) {
  const { x, y } = w2s(q.x, q.y)
  const size = 12 * zoom
  const pulse = 1 + Math.sin(t * 2.4 + hashSeed(q.id)) * 0.08

  ctx.save()
  ctx.globalAlpha = opts.dimmed ? 0.1 : 1
  ctx.translate(x, y)
  ctx.rotate(Math.PI / 4)
  ctx.fillStyle = QUEUE_BLUE
  ctx.shadowBlur = (opts.focused ? 18 : 10) * zoom
  ctx.shadowColor = QUEUE_BLUE
  const s = size * pulse
  ctx.fillRect(-s / 2, -s / 2, s, s)
  ctx.restore()

  if (zoom > 0.4) {
    const time = q.created_at
      ? new Date(q.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      : ''
    ctx.save()
    ctx.globalAlpha = opts.dimmed ? 0.1 : 0.85
    ctx.fillStyle = QUEUE_BLUE
    ctx.font = `10px ${getCanvasFontStack()}`
    ctx.textAlign = 'center'
    ctx.fillText(`born ${time} ⚡`, x, y - size - 4)
    ctx.restore()
  }
}

export function drawBlob(ctx, blob, w2s, zoom, opts = {}) {
  const { x, y } = w2s(blob.x, blob.y)
  const size = (10 + Math.sqrt(blob.count) * 6 + (blob.strength || 0) * 10) * zoom
  const color = colorForCategory(blob.mind_category)

  ctx.save()
  ctx.globalAlpha = opts.dimmed ? 0.08 : 0.55
  ctx.shadowBlur = 12 * zoom
  ctx.shadowColor = color
  ctx.fillStyle = color
  ctx.fillRect(x - size / 2, y - size / 2, size, size)
  ctx.restore()

  if (zoom > 0.3 && blob.count > 1) {
    ctx.save()
    ctx.globalAlpha = opts.dimmed ? 0.1 : 0.8
    ctx.fillStyle = '#0b0a09'
    ctx.font = `${Math.max(9, 10 * zoom)}px ${getCanvasFontStack()}`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText(String(blob.count), x, y + 1)
    ctx.restore()
  }
}

// Hit-tests in screen space against memory nodes, gap nodes, queue nodes and
// golden synapse arcs. Returns the closest hit (with `type` set) or null.
export function hitTest(st, sx, sy) {
  const w2s = st.worldToScreen
  let best = null
  let bestDist = Infinity

  const consider = (item, screenHalfSize, px, py) => {
    const dx = sx - px
    const dy = sy - py
    const r = screenHalfSize + 8
    if (Math.abs(dx) <= r && Math.abs(dy) <= r) {
      const d = Math.hypot(dx, dy)
      if (d < bestDist) { bestDist = d; best = item }
    }
  }

  if (!st.lodBlobs || st.zoom >= 0.55) {
    for (const node of st.nodes) {
      const p = w2s(node.x, node.y)
      consider(node, ((4 + (node.strength || 0) * 16) * st.zoom) / 2, p.x, p.y)
    }
  }
  for (const gap of st.gapNodes) {
    const p = w2s(gap.x, gap.y)
    consider(gap, (14 * st.zoom) / 2, p.x, p.y)
  }
  for (const q of st.queueNodes) {
    const p = w2s(q.x, q.y)
    consider(q, (12 * st.zoom) / 2, p.x, p.y)
  }

  for (const arc of st.synapseArcs) {
    const a = w2s(arc.a.x, arc.a.y)
    const b = w2s(arc.b.x, arc.b.y)
    const { mx, my, nx, ny, len } = arcGeometry(a, b)
    const bow = Math.min(60, len * 0.18)
    const cx = mx + nx * bow
    const cy = my + ny * bow

    let minD = Infinity
    let prev = a
    for (let i = 1; i <= 10; i++) {
      const tt = i / 10
      const omt = 1 - tt
      const px = omt * omt * a.x + 2 * omt * tt * cx + tt * tt * b.x
      const py = omt * omt * a.y + 2 * omt * tt * cy + tt * tt * b.y
      const d = pointToSegmentDist(sx, sy, prev.x, prev.y, px, py)
      if (d < minD) minD = d
      prev = { x: px, y: py }
    }
    if (minD < 10 && minD < bestDist) {
      bestDist = minD
      best = { type: 'synapse', ...arc.synapse, _a: arc.a, _b: arc.b }
    }
  }

  return best
}
